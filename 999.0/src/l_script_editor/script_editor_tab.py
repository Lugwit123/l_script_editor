# -*- coding: utf-8 -*-
"""
脚本编辑器标签页 - l_script_editor

完整的 Python 脚本编辑器 Widget，可嵌入任何 QTabWidget。

功能：
- Python 代码编辑（语法高亮 + 行号 + 自动补全）
- 执行选中代码或全部代码（Ctrl+Enter）
- 执行外部 .py 文件
- 多代码 Tab 管理（新建/关闭/重命名）
- 会话自动保存/恢复
- Ctrl+滚轮缩放
- 智能清空代码（保留 import 语句）
- 调试模式开关 / 快捷转换开关
"""

from __future__ import annotations

import codecs
import io
import os
import sys
import traceback
from typing import Optional, Dict, List

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QShortcut, QKeySequence, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import Lugwit_Module as LM

lprint = LM.lprint

from .code_editor import CodeEditorWithCompletion
from .python_highlighter import PythonHighlighter
from .session_manager import SessionManager


class ScriptEditorTab(QWidget):
    """可嵌入 QTabWidget 的脚本编辑器标签页。

    Parameters
    ----------
    parent : QWidget, optional
        父 Widget。
    main_window : QWidget, optional
        主窗口对象，会注入到代码执行环境中，并在关闭时自动保存会话。
    session_file : str, optional
        会话文件路径。默认在 ``@baselibs/l_script_editor/config/session.json``。
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        main_window: Optional[QWidget] = None,
        session_file: Optional[str] = None,
    ):
        super().__init__(parent)
        self._main_window = main_window
        self._tab_counter = 0
        self._injected_vars: Dict[str, object] = {}

        # 会话管理器
        if session_file is None:
            session_file = os.path.join(os.path.dirname(__file__), 'config', 'session.json')
        self._session_manager = SessionManager(session_file)

        # 构建 UI
        self._setup_ui()
        self._setup_connections()
        self._setup_shortcuts()

        # 恢复会话或创建初始 Tab
        if not self._session_manager.restore_session(self.code_tab_widget, self._create_new_tab):
            self._create_initial_tab()

        # 注册主窗口关闭钩子（自动保存会话）
        if main_window:
            self._install_close_hook(main_window)

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(3)

        # ---------- 工具栏 ----------
        toolbar_widget = QWidget(self)
        toolbar_layout = QVBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(3)

        # 第一行：主要操作
        row1 = QHBoxLayout()
        row1.setSpacing(5)

        self.run_btn = QPushButton("执行 (Ctrl+Enter)")
        self.run_btn.setMaximumWidth(150)
        self.run_btn.setToolTip("执行选中的代码或全部代码")
        row1.addWidget(self.run_btn)

        self.clear_output_btn = QPushButton("清空输出")
        self.clear_output_btn.setMaximumWidth(100)
        row1.addWidget(self.clear_output_btn)

        self.clear_code_btn = QPushButton("清空代码")
        self.clear_code_btn.setMaximumWidth(100)
        row1.addWidget(self.clear_code_btn)

        self.execute_file_btn = QPushButton("执行文件...")
        self.execute_file_btn.setMaximumWidth(120)
        self.execute_file_btn.setToolTip("选择并执行 Python 文件")
        row1.addWidget(self.execute_file_btn)

        row1.addSpacing(10)

        self.show_code_checkbox = QCheckBox("显示源码")
        self.show_code_checkbox.setToolTip("是否在输出窗口显示执行的源代码")
        row1.addWidget(self.show_code_checkbox)

        self.auto_clear_output_checkbox = QCheckBox("执行时清空输出")
        self.auto_clear_output_checkbox.setToolTip("执行代码前自动清空输出窗口")
        self.auto_clear_output_checkbox.setChecked(True)
        row1.addWidget(self.auto_clear_output_checkbox)

        self.debug_mode_checkbox = QCheckBox("调试模式")
        self.debug_mode_checkbox.setToolTip("启用补全调试日志")
        row1.addWidget(self.debug_mode_checkbox)

        self.shortcuts_enabled_checkbox = QCheckBox("快捷转换")
        self.shortcuts_enabled_checkbox.setToolTip("启用快捷转换（lp->lprint 等）")
        self.shortcuts_enabled_checkbox.setChecked(True)
        row1.addWidget(self.shortcuts_enabled_checkbox)

        row1.addStretch(1)

        hint_label = QLabel("提示：可使用 import 导入需要的模块")
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        row1.addWidget(hint_label)

        toolbar_layout.addLayout(row1)

        # 第二行：Tab 管理
        row2 = QHBoxLayout()
        row2.setSpacing(5)

        self.new_tab_btn = QPushButton("+ 新建")
        self.new_tab_btn.setMaximumWidth(80)
        self.new_tab_btn.setMaximumHeight(25)
        self.new_tab_btn.setToolTip("新建代码 Tab (Ctrl+N)")
        row2.addWidget(self.new_tab_btn)

        self.close_tab_btn = QPushButton("关闭")
        self.close_tab_btn.setMaximumWidth(80)
        self.close_tab_btn.setMaximumHeight(25)
        self.close_tab_btn.setToolTip("关闭当前 Tab (Ctrl+W)")
        row2.addWidget(self.close_tab_btn)

        self.rename_tab_btn = QPushButton("重命名")
        self.rename_tab_btn.setMaximumWidth(80)
        self.rename_tab_btn.setMaximumHeight(25)
        self.rename_tab_btn.setToolTip("重命名当前 Tab")
        row2.addWidget(self.rename_tab_btn)

        row2.addStretch(1)

        toolbar_layout.addLayout(row2)

        root_layout.addWidget(toolbar_widget)

        # ---------- 上下分割器 ----------
        self.splitter = QSplitter(Qt.Vertical, self)

        # --- 上半部分：代码编辑 Tab ---
        code_container = QWidget()
        code_layout = QVBoxLayout(code_container)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)

        self.code_tab_widget = QTabWidget()
        self.code_tab_widget.setTabsClosable(True)
        self.code_tab_widget.setMovable(True)
        code_layout.addWidget(self.code_tab_widget)

        self.splitter.addWidget(code_container)

        # --- 下半部分：输出区域 ---
        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(2)

        output_label = QLabel("输出:")
        output_label.setStyleSheet("font-weight: bold; color: #CCCCCC;")
        output_label.setMaximumHeight(20)
        output_layout.addWidget(output_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet("""QTextEdit {
    background-color: #2b2b2b;
    color: #f0f0f0;
    border: 1px solid #555;
    font-family: Consolas, Monaco, 'Courier New', monospace;
    font-size: 10pt;
}""")
        output_layout.addWidget(self.output_text)

        self.splitter.addWidget(output_container)

        # 初始比例 6:4
        self.splitter.setSizes([400, 250])

        root_layout.addWidget(self.splitter, stretch=1)

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _setup_connections(self) -> None:
        self.run_btn.clicked.connect(self.execute_code)
        self.clear_output_btn.clicked.connect(self.clear_output)
        self.clear_code_btn.clicked.connect(self.clear_code)
        self.execute_file_btn.clicked.connect(self._execute_file_dialog)
        self.new_tab_btn.clicked.connect(lambda: self._create_new_tab())
        self.close_tab_btn.clicked.connect(self._close_current_tab)
        self.rename_tab_btn.clicked.connect(self._rename_current_tab)
        self.code_tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)

        # 调试模式开关
        self.debug_mode_checkbox.stateChanged.connect(self._on_debug_mode_changed)
        # 快捷转换开关
        self.shortcuts_enabled_checkbox.stateChanged.connect(self._on_shortcuts_enabled_changed)

    def _setup_shortcuts(self) -> None:
        """设置快捷键"""
        try:
            parent_for_shortcut = self._main_window or self

            new_tab_shortcut = QShortcut(QKeySequence('Ctrl+N'), parent_for_shortcut)
            new_tab_shortcut.activated.connect(lambda: self._create_new_tab())

            close_tab_shortcut = QShortcut(QKeySequence('Ctrl+W'), parent_for_shortcut)
            close_tab_shortcut.activated.connect(self._close_current_tab)
        except Exception as e:
            lprint(f"[脚本编辑器] 快捷键设置失败: {e}")

    # ------------------------------------------------------------------
    # 主窗口关闭钩子
    # ------------------------------------------------------------------

    def _install_close_hook(self, main_window) -> None:
        """安装主窗口关闭钩子，自动保存会话"""
        original_close_event = getattr(main_window, 'closeEvent', None)

        def wrapped_close_event(event):
            try:
                lprint("[会话管理] 正在保存会话状态...")
                self._session_manager.save_session(self.code_tab_widget)
                lprint("[会话管理] 脚本编辑器会话保存完成")
            except Exception as e:
                lprint(f"[会话管理] 保存会话失败: {str(e)}")

            if original_close_event:
                try:
                    original_close_event(event)
                except Exception as e:
                    lprint(f"[会话管理] 调用主窗口closeEvent失败: {str(e)}")
                    event.accept()
            else:
                event.accept()

        main_window.closeEvent = wrapped_close_event

    # ==================================================================
    # Tab 管理
    # ==================================================================

    def _create_initial_tab(self) -> None:
        self._create_new_tab(with_example=True)

    def _create_new_tab(
        self,
        tab_name: Optional[str] = None,
        with_example: bool = False,
    ) -> Optional[CodeEditorWithCompletion]:
        self._tab_counter += 1
        if not tab_name:
            tab_name = f"代码 {self._tab_counter}"

        # 使用支持代码补全和行号的编辑器
        code_editor = CodeEditorWithCompletion()
        # 设置等宽字体（不使用 stylesheet 固定字号，以支持 Ctrl+滚轮缩放）
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        code_editor.setFont(font)
        code_editor.setStyleSheet("""QPlainTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #404040;
    selection-background-color: #264f78;
}""")
        code_editor.setPlaceholderText(
            "在此输入 Python 代码...\n\n"
            "# 可用变量:\n"
            "#   main_window  - 主窗口对象\n"
            "#   self         - 当前脚本编辑器组件"
        )

        # 语法高亮
        try:
            highlighter = PythonHighlighter(code_editor.document())
            code_editor.setProperty("highlighter", highlighter)
        except Exception as e:
            lprint(f"[脚本编辑器] 语法高亮初始化失败: {e}")

        # 应用调试模式和快捷转换设置
        code_editor.debug_mode = self.debug_mode_checkbox.isChecked()
        code_editor.enable_shortcuts = self.shortcuts_enabled_checkbox.isChecked()

        if with_example:
            example = (
                "# 脚本编辑器\n"
                "# 可直接使用以下变量:\n"
                "#   main_window  - 主窗口对象\n"
                "\n"
                "print('Hello from Script Editor!')\n"
            )
            code_editor.setPlainText(example)
        else:
            code_editor.setPlainText("")

        # 光标移到末尾
        cursor = code_editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        code_editor.setTextCursor(cursor)

        index = self.code_tab_widget.addTab(code_editor, tab_name)
        self.code_tab_widget.setCurrentIndex(index)

        lprint(f"[脚本编辑器] 创建新Tab: {tab_name}")
        return code_editor

    def _get_current_editor(self) -> Optional[CodeEditorWithCompletion]:
        return self.code_tab_widget.currentWidget()

    def _close_current_tab(self) -> None:
        if self.code_tab_widget.count() <= 1:
            lprint("[脚本编辑器] 至少需要保留一个 Tab")
            return
        idx = self.code_tab_widget.currentIndex()
        self.code_tab_widget.removeTab(idx)

    def _on_tab_close_requested(self, index: int) -> None:
        if self.code_tab_widget.count() <= 1:
            lprint("[脚本编辑器] 至少需要保留一个 Tab")
            return
        self.code_tab_widget.removeTab(index)

    def _rename_current_tab(self) -> None:
        idx = self.code_tab_widget.currentIndex()
        if idx < 0:
            return
        old_name = self.code_tab_widget.tabText(idx)
        new_name, ok = QInputDialog.getText(self, "重命名 Tab", "新名称:", text=old_name)
        if ok and new_name.strip():
            self.code_tab_widget.setTabText(idx, new_name.strip())


    # ==================================================================
    # 调试/快捷转换开关
    # ==================================================================

    def _on_debug_mode_changed(self, state):
        is_checked = state == QtCore.Qt.CheckState.Checked.value
        lprint(f"[脚本编辑器] 调试模式: {'启用' if is_checked else '禁用'}")
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if isinstance(editor, CodeEditorWithCompletion):
                editor.debug_mode = is_checked

    def _on_shortcuts_enabled_changed(self, state):
        is_checked = state == QtCore.Qt.CheckState.Checked.value
        lprint(f"[脚本编辑器] 快捷转换: {'启用' if is_checked else '禁用'}")
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if isinstance(editor, CodeEditorWithCompletion):
                editor.enable_shortcuts = is_checked

    # ==================================================================
    # 代码执行
    # ==================================================================

    def execute_code(self) -> None:
        """执行当前编辑器中选中的代码或全部代码。"""
        code_editor = self._get_current_editor()
        if not code_editor or not self.output_text:
            lprint("[脚本编辑器] 编辑器组件未找到")
            return

        try:
            # 自动清空输出
            if self.auto_clear_output_checkbox.isChecked():
                self._clear_output_silent()

            # 获取代码
            cursor = code_editor.textCursor()
            if cursor.hasSelection():
                code = cursor.selectedText()
            else:
                code = code_editor.toPlainText()

            if not code.strip():
                self._append_output("⚠️ 没有代码可执行")
                return

            # Qt 段落分隔符替换
            code = code.replace("\u2028", "\n").replace("\u2029", "\n")

            show_source = self.show_code_checkbox.isChecked()
            if show_source:
                self._append_output(">>> 执行代码:")
                self._append_output(code)
                self._append_output("--- 输出结果 ---")

            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            local_vars = {
                "self": self,
                "print": self._custom_print,
            }

            # 注入主窗口
            if self._main_window is not None:
                local_vars["main_window"] = self._main_window

            # 注入自定义变量
            local_vars.update(self._injected_vars)

            try:
                sys.stdout = stdout_buffer
                sys.stderr = stderr_buffer
                exec(code, globals(), local_vars)
                stdout_content = stdout_buffer.getvalue()
                stderr_content = stderr_buffer.getvalue()
                if stdout_content:
                    self._append_output(stdout_content.rstrip())
                if stderr_content:
                    self._append_output("🔴 错误:", "error")
                    self._append_output(stderr_content.rstrip(), "error")
            except Exception:
                error_msg = traceback.format_exc()
                self._append_output("❌ 执行出错:", "error")
                self._append_output(error_msg, "error")
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            self._append_output("=" * 50)

        except Exception as exc:
            self._append_output(f"❌ 脚本编辑器内部错误: {exc}", "error")

    def _execute_file_dialog(self) -> None:
        """弹出文件对话框选择并执行 .py 文件。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 Python 文件", "", "Python 文件 (*.py);;所有文件 (*.*)"
        )
        if file_path:
            self._execute_python_file(file_path)

    def _execute_python_file(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            self._append_output(f"❌ 文件不存在: {file_path}", "error")
            return
        if not file_path.lower().endswith(".py"):
            self._append_output("❌ 只能执行 Python 文件 (.py)", "error")
            return

        show_source = self.show_code_checkbox.isChecked()
        self._append_output(f"🚀 执行文件: {file_path}")
        if show_source:
            self._append_output("=" * 50)

        try:
            with codecs.open(file_path, "r", encoding="utf-8") as fh:
                code_content = fh.read()
        except UnicodeDecodeError:
            try:
                with codecs.open(file_path, "r", encoding="gb18030") as fh:
                    code_content = fh.read()
            except UnicodeDecodeError:
                with open(file_path, "r") as fh:
                    code_content = fh.read()

        if show_source:
            lines = code_content.split("\n")
            preview = lines[:10]
            if len(lines) > 10:
                preview.append(f"... (共 {len(lines)} 行代码)")
            self._append_output("\n".join(preview))
            self._append_output("=" * 50)

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_path = sys.path[:]
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        try:
            sys.stdout = stdout_buffer
            sys.stderr = stderr_buffer

            file_dir = os.path.dirname(os.path.abspath(file_path))
            if file_dir not in sys.path:
                sys.path.insert(0, file_dir)

            global_vars = {
                '__file__': file_path,
                '__name__': '__main__',
                'self': self,
                'print': self._custom_print,
            }
            if self._main_window is not None:
                global_vars['main_window'] = self._main_window
            global_vars.update(self._injected_vars)

            exec(compile(code_content, file_path, "exec"), global_vars)
            stdout_content = stdout_buffer.getvalue()
            stderr_content = stderr_buffer.getvalue()
            if stdout_content:
                self._append_output(stdout_content.rstrip())
            if stderr_content:
                self._append_output("🔴 错误:", "error")
                self._append_output(stderr_content.rstrip(), "error")
        except Exception:
            error_msg = traceback.format_exc()
            self._append_output("❌ 执行出错:", "error")
            self._append_output(error_msg, "error")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.path[:] = old_path

        self._append_output("=" * 50)

    # ==================================================================
    # 智能清空代码
    # ==================================================================

    def clear_code(self) -> None:
        """清空代码（保留 import 语句）"""
        editor = self._get_current_editor()
        if not editor:
            return

        try:
            reply = QMessageBox.question(
                self._main_window or self,
                "确认清空",
                "确定要清空当前Tab的代码吗？\n\n注意：将保留 import 语句",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._smart_clear_code(editor)
                self._append_output("📝 当前Tab代码已清空（已保留 import 语句）")
        except Exception:
            self._smart_clear_code(editor)
            self._append_output("📝 当前Tab代码已清空（已保留 import 语句）")

    def _smart_clear_code(self, editor: CodeEditorWithCompletion) -> None:
        """智能清空代码，保留 import 语句"""
        try:
            current_code = editor.toPlainText()
            preserved_imports = []

            for line in current_code.split('\n'):
                stripped = line.strip()
                if (stripped.startswith('import ') or
                        stripped.startswith('from ') or
                        'lprint' in stripped and 'import' in stripped):
                    preserved_imports.append(line)

            if preserved_imports:
                new_code = '\n'.join(preserved_imports) + '\n\n'
                editor.setPlainText(new_code)
            else:
                editor.setPlainText("")

            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            editor.setTextCursor(cursor)

        except Exception as e:
            lprint(f"[清空代码] 智能清空失败: {e}")
            editor.setPlainText("")

    # ==================================================================
    # 输出管理
    # ==================================================================

    def _custom_print(self, *args, **kwargs) -> None:
        output = " ".join(str(arg) for arg in args)
        self._append_output(output)

    def _append_output(self, text: str, style: str = "normal") -> None:
        if not self.output_text:
            return
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        if style == "error":
            fmt.setForeground(QColor("#ff6b6b"))
        else:
            fmt.setForeground(QColor("#f0f0f0"))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")
        self.output_text.ensureCursorVisible()

    def clear_output(self) -> None:
        if self.output_text:
            self.output_text.clear()
            self._append_output("📋 输出已清空")

    def _clear_output_silent(self) -> None:
        if self.output_text:
            self.output_text.clear()

    # ==================================================================
    # 公共 API（供调用方定制）
    # ==================================================================

    def set_api_tree(self, api_tree: dict) -> None:
        """注入自定义 API 树给所有编辑器的补全器。

        Parameters
        ----------
        api_tree : dict
            形如 ``{"module_name": ["attr1", "attr2"], ...}`` 的字典。
        """
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if isinstance(editor, CodeEditorWithCompletion):
                editor.completer.set_api_tree(api_tree)

    def add_custom_completions(self, items: list) -> None:
        """添加自定义补全项到所有编辑器。"""
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if isinstance(editor, CodeEditorWithCompletion):
                editor.completer.set_custom_completions(items)

    def set_session_file(self, path: str) -> None:
        """更改会话文件路径。"""
        self._session_manager = SessionManager(path)

    def inject_variables(self, var_dict: dict) -> None:
        """注入变量到代码执行环境。

        Parameters
        ----------
        var_dict : dict
            变量名到值的映射，如 ``{"data_center": dc_obj}``。
        """
        self._injected_vars.update(var_dict)
