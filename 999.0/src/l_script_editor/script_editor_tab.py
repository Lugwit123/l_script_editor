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

import abc
import codecs
import collections
import copy
import datetime
import functools
import glob
import hashlib
import importlib
import io
import itertools
import json
import math
import os
import pathlib
import pprint
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import typing
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Sequence, Callable
from importlib import reload

from PySide6 import QtCore, QtGui, QtUiTools
from PySide6.QtGui import QShortcut, QKeySequence, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import Lugwit_Module as LM
import l_qt_wgt_lib

from .code_editor import CodeEditorWithCompletion
from .python_highlighter import PythonHighlighter
from .session_manager import SessionManager

lprint = LM.lprint

# 脚本执行环境预注入的常用模块，用户脚本无需手动 import 即可使用
_BUILTIN_IMPORTS: Dict[str, object] = {
    'os': os,
    'sys': sys,
    're': re,
    'io': io,
    'json': json,
    'math': math,
    'time': time,
    'glob': glob,
    'copy': copy,
    'abc': abc,
    'shutil': shutil,
    'codecs': codecs,
    'datetime': datetime,
    'tempfile': tempfile,
    'subprocess': subprocess,
    'traceback': traceback,
    'pathlib': pathlib,
    'itertools': itertools,
    'functools': functools,
    'collections': collections,
    'textwrap': textwrap,
    'hashlib': hashlib,
    'pprint': pprint,
    'importlib': importlib,
    'typing': typing,
    'l_qt_wgt_lib': l_qt_wgt_lib,
}

print("\n\n@@@@@@@@@@@@@@@@@@@@@@@@@@@我真的被重载了\n\n")

@dataclass
class TraceOptions:
    """追踪参数配置。"""
    enabled: bool = False
    timeout: int = 30
    trace_depth: int = 5
    auto_stop: bool = True
    auto_result: bool = True
    trace_threads: bool = False
    multiprocess: bool = False
    trace_skip_function_names: Optional[Sequence[str]] = None
    trace_skip_path_substrings: Optional[Sequence[str]] = None
    trace_use_profile: bool = False
    trace_path_id_limit: int = 100
    trace_linear_include_line_events: bool = False
    clear_log: bool = False


try:
    from l_qt_wgt_lib.smart_widget.code_editor import CodeEditorWidget, LogCodeHighlighter
except ImportError:
    CodeEditorWidget = None  # type: ignore
    LogCodeHighlighter = None  # type: ignore


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
    tab_widget : QTabWidget, optional
        宿主 QTabWidget 引用，传入后重载按钮可完全内部实现。
    tab_name : str
        在宿主 QTabWidget 中显示的标签名，默认 ``"脚本编辑器"``。
    save_directory : str, optional
        代码保存目录，重载时自动继承，无需外部恢复。
    after_reload_hook : Callable[[ScriptEditorTab], None], optional
        重载完成后的回调，接收新实例作为参数。预留接口，不传则不调用。
    init_code : str, optional
        新建 Tab 时自动填入的初始化代码（如常用 import 语句）。
        为空字符串或 None 时行为与原来一致（空白 Tab）。
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        main_window: Optional[QWidget] = None,
        session_file: Optional[str] = None,
        tab_widget: Optional[QTabWidget] = None,
        tab_name: str = "脚本编辑器",
        save_directory: Optional[str] = None,
        after_reload_hook: Optional[Callable] = None,
        init_code: str = "",
    ):
        super().__init__(parent)
        self._main_window = main_window
        self._tab_widget = tab_widget  # 宿主 QTabWidget 引用
        self._tab_display_name = tab_name
        self._tab_counter = 0
        self._injected_vars: Dict[str, object] = {}
        self._save_directory: Optional[str] = save_directory  # 代码保存目录
        self._trace_options = TraceOptions()  # 追踪参数配置
        self._after_reload_hook = after_reload_hook  # 重载后回调（预留接口）
        self._init_code: str = init_code  # 新建 Tab 时的初始化代码

        # 会话管理器
        if session_file is None:
            session_file = os.path.join(os.path.dirname(__file__), 'config', 'session.json')
        self._session_file = session_file
        self._session_manager = SessionManager(session_file)

        # 构造时即初始化保存目录
        if save_directory:
            os.makedirs(save_directory, exist_ok=True)
            lprint(f"[代码保存] 保存目录已设置: {save_directory}")

        # 构建 UI
        self._setup_ui()
        self._setup_connections()
        self._setup_shortcuts()

        # 恢复会话或创建初始 Tab
        if not self._session_manager.restore_session(self.code_tab_widget, self._create_new_tab):
            self._create_initial_tab()

    # ==================================================================
    # UI 构建
    # ==================================================================

    _UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'script_editor_tab.ui')
    _HISTORY_UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history_dialog.ui')

    def _setup_ui(self) -> None:
        """从 .ui 文件加载界面布局。"""
        loader = QtUiTools.QUiLoader()
        ui_file = QtCore.QFile(self._UI_FILE)
        if not ui_file.open(QtCore.QFile.ReadOnly):
            raise FileNotFoundError(f"无法打开 UI 文件: {self._UI_FILE}")
        try:
            ui_widget = loader.load(ui_file, self)
        finally:
            ui_file.close()

        if ui_widget is None:
            raise RuntimeError(f"QUiLoader 加载 UI 文件失败: {self._UI_FILE}")

        # 将加载的布局嵌入当前 Widget
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(ui_widget)

        # 查找子控件引用（按 objectName）
        self.run_btn                  = self._find("run_btn")
        self.clear_output_btn         = self._find("clear_output_btn")
        self.clear_code_btn           = self._find("clear_code_btn")
        self.execute_file_btn         = self._find("execute_file_btn")
        self.show_code_checkbox       = self._find("show_code_checkbox")
        self.auto_clear_output_checkbox = self._find("auto_clear_output_checkbox")
        self.debug_mode_checkbox      = self._find("debug_mode_checkbox")
        self.trace_execution_checkbox = self._find("trace_execution_checkbox")
        self.shortcuts_enabled_checkbox = self._find("shortcuts_enabled_checkbox")
        self.new_tab_btn              = self._find("new_tab_btn")
        self.close_tab_btn            = self._find("close_tab_btn")
        self.rename_tab_btn           = self._find("rename_tab_btn")
        self.history_btn              = self._find("history_btn")
        self.favorites_btn            = self._find("favorites_btn")
        self.reload_btn               = self._find("reload_btn")
        self.save_btn                 = self._find("save_btn")
        self.code_tab_widget          = self._find("code_tab_widget")
        self.splitter                 = self._find("splitter")

        # 用 CodeEditorWidget 替换占位的 QPlainTextEdit
        self.output_text = self._replace_with_code_editor_output("output_text")

        # 初始分割比例 6:4
        self.splitter.setSizes([400, 250])

    def _find(self, name: str):
        """按 objectName 查找子控件。"""
        w = self.findChild(QWidget, name)
        if w is None:
            raise RuntimeError(f"UI 中未找到控件: {name}")
        return w

    def _replace_with_code_editor_output(self, name: str):
        """将 UI 中的 QPlainTextEdit 占位替换为 CodeEditorWidget（带行号 + 模式切换）。"""
        placeholder = self._find(name)

        if CodeEditorWidget is not None:
            output = CodeEditorWidget()
            output.setReadOnly(True)
            output.setFont(QFont("Consolas", 10))
            output.set_highlighter(LogCodeHighlighter)
        else:
            output = QPlainTextEdit()
            output.setReadOnly(True)
            output.setFont(QFont("Consolas", 10))
        output.setObjectName(name)
        output.setStyleSheet(
            "background-color: #2b2b2b; color: #f0f0f0; "
            "border: 1px solid #555;"
        )

        parent = placeholder.parentWidget()
        layout = parent.layout() if parent else None
        if layout is not None:
            layout.replaceWidget(placeholder, output)
        placeholder.deleteLater()
        return output

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
        self.history_btn.clicked.connect(self._show_history_dialog)
        self.favorites_btn.clicked.connect(self._show_favorites_dialog)
        self.save_btn.clicked.connect(lambda: self.save_all_tabs())
        self.reload_btn.clicked.connect(self._on_reload_clicked)
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

            save_shortcut = QShortcut(QKeySequence('Ctrl+S'), parent_for_shortcut)
            save_shortcut.activated.connect(lambda: self.save_all_tabs())
        except Exception as e:
            lprint(f"[脚本编辑器] 快捷键设置失败: {e}")

    # ==================================================================
    # Tab 管理
    # ==================================================================

    def _create_initial_tab(self) -> None:
        # 有自定义 init_code 时优先使用，否则使用默认示例
        self._create_new_tab(with_example=not self._init_code)

    def _create_new_tab(
        self,
        tab_name: Optional[str] = None,
        with_example: bool = False,
    ) -> Optional[CodeEditorWithCompletion]:
        self._tab_counter += 1
        if not tab_name:
            tab_name = f"code_{self._tab_counter}"

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
        elif self._init_code:
            # 填入自定义初始化代码
            code_editor.setPlainText(self._init_code)
            # 光标移到末尾，方便用户直接追加代码
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

    def _has_unsaved_code(self, index: int) -> bool:
        """判断指定 Tab 是否有非空代码（视为未保存内容）。"""
        editor = self.code_tab_widget.widget(index)
        if editor and hasattr(editor, 'toPlainText'):
            return bool(editor.toPlainText().strip())
        return False

    def _close_current_tab(self) -> None:
        if self.code_tab_widget.count() <= 1:
            lprint("[脚本编辑器] 至少需要保留一个 Tab")
            return
        idx = self.code_tab_widget.currentIndex()
        if self._has_unsaved_code(idx):
            tab_name = self.code_tab_widget.tabText(idx) or f"Tab {idx + 1}"
            reply = QMessageBox.question(
                self._main_window or self,
                "确认关闭",
                f"Tab \"{tab_name}\" 中有未保存的代码，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.code_tab_widget.removeTab(idx)

    def _on_tab_close_requested(self, index: int) -> None:
        if self.code_tab_widget.count() <= 1:
            lprint("[脚本编辑器] 至少需要保留一个 Tab")
            return
        if self._has_unsaved_code(index):
            tab_name = self.code_tab_widget.tabText(index) or f"Tab {index + 1}"
            reply = QMessageBox.question(
                self._main_window or self,
                "确认关闭",
                f"Tab \"{tab_name}\" 中有未保存的代码，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
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

    _TEMP_DIR = os.path.join(tempfile.gettempdir(), 'l_script_editor')

    def _write_temp_module(self, code: str, tab_name: str = "script") -> str:
        """将代码写入临时 .py 文件，返回文件路径。

        文件名格式: ``temp_{safe_name}_{timestamp}.py``（仅保留 ASCII 字符）
        目录不存在时自动创建。
        """
        os.makedirs(self._TEMP_DIR, exist_ok=True)
        # 只保留 ASCII 字母/数字/下划线，其余替换为 _，连续 _ 合并
        safe_name = re.sub(r'[^A-Za-z0-9_]+', '_', tab_name).strip('_')
        if not safe_name:
            safe_name = 'tab'
        ts = int(time.time() * 1000) % 100000000
        temp_path = os.path.join(self._TEMP_DIR, f"temp_{safe_name}_{ts}.py")
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return temp_path

    def _write_trace_runner(self, user_code_path: str, trace_stem: str) -> str:
        """写入追踪运行器文件，返回文件路径。

        运行器在 ``<module>`` 中调用 ``trace_start`` → exec 用户代码 → ``trace_stop``，
        用户代码与运行器共享命名空间（无 importlib 帧开销，lprint 等变量可用）。
        """
        os.makedirs(self._TEMP_DIR, exist_ok=True)
        ts = int(time.time() * 1000) % 100000000
        runner_path = os.path.join(self._TEMP_DIR, f"trace_{trace_stem}_{ts}.py")
        _opts = self._trace_options
        runner_code = (
            "lprint.trace_stop()\n"
            "lprint.trace_log_enable = True\n"
            "lprint.trace_start(\n"
            f"    timeout={_opts.timeout!r},\n"
            f"    trace_depth={_opts.trace_depth!r},\n"
            "    auto_result=True,\n"
            f"    trace_threads={_opts.trace_threads!r},\n"
            f"    multiprocess={_opts.multiprocess!r},\n"
            f"    trace_skip_function_names={_opts.trace_skip_function_names!r},\n"
            f"    trace_skip_path_substrings={_opts.trace_skip_path_substrings!r},\n"
            f"    trace_use_profile={_opts.trace_use_profile!r},\n"
            f"    trace_path_id_limit={_opts.trace_path_id_limit!r},\n"
            f"    trace_linear_include_line_events={_opts.trace_linear_include_line_events!r},\n"
            f"    clear_log={_opts.clear_log!r},\n"
            f"    trace_log_stem={trace_stem!r},\n"
            ")\n"
            "try:\n"
            f"    exec(compile(open({user_code_path!r}, encoding='utf-8').read(), {user_code_path!r}, 'exec'))\n"
            "finally:\n"
            "    lprint.trace_stop()\n"
            "    lprint.trace_log_enable = False\n"
        )
        with open(runner_path, 'w', encoding='utf-8') as f:
            f.write(runner_code)
        return runner_path

    def _build_exec_globals(self, file_path: str = "") -> dict:
        """构建代码执行的命名空间（合并到 globals 副本）。

        显式注入 ``_BUILTIN_IMPORTS`` 中的常用标准库模块和 ``l_qt_wgt_lib``，
        用户脚本无需手动 import 即可使用这些模块。
        """
        exec_globals = dict(globals())
        # 显式注入常用模块（不依赖模块级 globals 的偶然性）
        exec_globals.update(_BUILTIN_IMPORTS)
        exec_globals.update({
            '__name__': '__main__',
            'self': self,
            'print': self._custom_print,
            'lprint': lprint,
            'reload': reload
        })
        if file_path:
            exec_globals['__file__'] = file_path
        if self._main_window is not None:
            exec_globals['main_window'] = self._main_window
        exec_globals.update(self._injected_vars)
        return exec_globals

    def _collect_trace_options_from_main_window(self) -> TraceOptions:
        """从主界面的 UI 控件中读取追踪设置参数。"""
        ui = getattr(self._main_window, 'ui', None)
        if ui is None:
            return TraceOptions()

        # 默认值
        timeout_default = 30
        depth_default = 5
        path_id_limit_default = 100

        # 读取控件值
        timeout_spin = getattr(ui, "traceTimeoutSpinBox", None)
        depth_spin = getattr(ui, "traceDepthSpinBox", None)
        path_limit_spin = getattr(ui, "tracePathIdLimitSpinBox", None)
        profile_checkbox = getattr(ui, "traceUseProfileCheckBox", None)
        linear_line_checkbox = getattr(ui, "traceLinearIncludeLineEventsCheckBox", None)
        stop_on_slot_finished_checkbox = getattr(ui, "traceStopOnSlotFinishedCheckBox", None)
        threads_checkbox = getattr(ui, "traceThreadsCheckBox", None)
        auto_result_checkbox = getattr(ui, "traceAutoResultCheckBox", None)
        return TraceOptions(
            enabled=False,  # 主界面无总开关，默认不启用，由用户手动勾选追踪复选框
            timeout=int(timeout_spin.value()) if timeout_spin is not None else timeout_default,
            trace_depth=int(depth_spin.value()) if depth_spin is not None else depth_default,
            auto_stop=bool(stop_on_slot_finished_checkbox.isChecked()) if stop_on_slot_finished_checkbox is not None else False,
            trace_use_profile=bool(profile_checkbox.isChecked()) if profile_checkbox is not None else False,
            trace_path_id_limit=int(path_limit_spin.value()) if path_limit_spin is not None else path_id_limit_default,
            trace_linear_include_line_events=bool(linear_line_checkbox.isChecked()) if linear_line_checkbox is not None else False,
            trace_threads=bool(threads_checkbox.isChecked()) if threads_checkbox is not None else False,
            auto_result=bool(auto_result_checkbox.isChecked()) if auto_result_checkbox is not None else True,
        )

    def execute_code(self) -> None:
        """执行当前编辑器中选中的代码或全部代码。"""
        code_editor = self._get_current_editor()
        if not code_editor or not self.output_text:
            lprint("[脚本编辑器] 编辑器组件未找到")
            return

        # 从主界面读取追踪设置
        if self._main_window is not None:
            try:
                trace_options = self._collect_trace_options_from_main_window()
                self.trace_options = trace_options
            except Exception:
                pass  # 主界面无追踪设置控件时忽略

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

            # Qt 段落分隔符替换 + 清除 null bytes
            code = code.replace("\u2028", "\n").replace("\u2029", "\n")
            code = code.replace("\x00", "")  # Qt toPlainText 可能引入 null bytes，导致 compile 失败

            show_source = self.show_code_checkbox.isChecked()
            if show_source:
                self._append_output(">>> 执行代码:", preserve_whitespace=True)
                self._append_output(code, preserve_whitespace=True)
                self._append_output("--- 输出结果 ---")

            # 写入临时模块文件，用 compile + exec 执行
            tab_name = ""
            idx = self.code_tab_widget.currentIndex()
            if idx >= 0:
                tab_name = self.code_tab_widget.tabText(idx) or "script"
            temp_path = self._write_temp_module(code, tab_name)

            # 追踪模式：使用 lprint.trace_start/trace_stop 直接追踪
            trace_enabled = self.trace_execution_checkbox.isChecked()
            if trace_enabled:
                self._append_output(" 追踪已启用")
                self.trace_execution_checkbox.setChecked(False)
                lprint.trace_log_enable = True

            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            exec_globals = self._build_exec_globals(temp_path)

            try:
                sys.stdout = stdout_buffer
                sys.stderr = stderr_buffer

                if trace_enabled:
                    # 用独立的追踪运行器包裹用户代码执行
                    # trace_start/trace_stop 在 runner 的 <module> 中调用，与编辑器调用栈隔离
                    _trace_stem = re.sub(r'[^A-Za-z0-9_]+', '_', tab_name).strip('_') or 'script'
                    _trace_stem = "trace_" + _trace_stem
                    _runner_path = self._write_trace_runner(temp_path, _trace_stem)
                    _runner_globals = self._build_exec_globals(_runner_path)
                    _runner_code = open(_runner_path, 'r', encoding='utf-8').read()
                    try:
                        exec(compile(_runner_code, _runner_path, 'exec'), _runner_globals)
                    except Exception:
                        try:
                            lprint.trace_stop()
                        except Exception:
                            pass
                else:
                    compiled = compile(code, temp_path, "exec")
                    exec(compiled, exec_globals)
                stdout_content = stdout_buffer.getvalue()
                stderr_content = stderr_buffer.getvalue()
                if stdout_content:
                    for line in stdout_content.splitlines():
                        self._append_output(line)
                if stderr_content:
                    self._append_output(" 错误:", "error")
                    for line in stderr_content.splitlines():
                        self._append_output(line, "error")
            except Exception:
                error_msg = traceback.format_exc()
                self._append_output(" 执行出错:", "error")
                for line in error_msg.splitlines():
                    self._append_output(line, "error")
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
            self._append_output(f" 文件不存在: {file_path}", "error")
            return
        if not file_path.lower().endswith(".py"):
            self._append_output(" 只能执行 Python 文件 (.py)", "error")
            return
    
        # 从主界面读取追踪设置
        if self._main_window is not None:
            try:
                trace_options = self._collect_trace_options_from_main_window()
                self.trace_options = trace_options
            except Exception:
                pass  # 主界面无追踪设置控件时忽略
    
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

            # 追踪模式：执行前启用，执行后关闭
            trace_enabled = self.trace_execution_checkbox.isChecked()
            if trace_enabled:
                self._append_output("🔍 追踪已启用")
                self.trace_execution_checkbox.setChecked(False)

            exec_globals = self._build_exec_globals(file_path)

            if trace_enabled:
                _trace_stem = "trace_" + os.path.splitext(os.path.basename(file_path))[0]
                _runner_path = self._write_trace_runner(file_path, _trace_stem)
                _runner_globals = self._build_exec_globals(_runner_path)
                _runner_code = open(_runner_path, 'r', encoding='utf-8').read()
                try:
                    exec(compile(_runner_code, _runner_path, 'exec'), _runner_globals)
                except Exception:
                    try:
                        lprint.trace_stop()
                    except Exception:
                        pass
            else:
                exec(compile(code_content, file_path, "exec"), exec_globals)
            
            stdout_content = stdout_buffer.getvalue()
            stderr_content = stderr_buffer.getvalue()
            if stdout_content:
                for line in stdout_content.splitlines():
                    self._append_output(line)
            if stderr_content:
                self._append_output(" 错误:", "error")
                for line in stderr_content.splitlines():
                    self._append_output(line, "error")
        except Exception:
            error_msg = traceback.format_exc()
            self._append_output("❌ 执行出错:", "error")
            for line in error_msg.splitlines():
                self._append_output(line, "error")
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

    def _append_output(self, text: str, style: str = "normal", preserve_whitespace: bool = False) -> None:
        if not self.output_text:
            return
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))
        # 保留缩进：将普通空格替换为 &nbsp;（HTML 会合并连续空格）
        if preserve_whitespace:
            escaped = escaped.replace(" ", "&nbsp;")
            escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        color = "#ff6b6b" if style == "error" else "#f0f0f0"
        # 不指定 font-size，让内容继承 widget 字体大小（支持 Ctrl+滚轮缩放）
        html = (f'<span style="color:{color}; '
                f'font-family:Consolas,monospace;">'
                f'{escaped}</span>')
        # CodeEditorWidget 内部是 QPlainTextEdit，通过 editor() 访问
        editor = self.output_text.editor() if hasattr(self.output_text, 'editor') else self.output_text
        editor.appendHtml(html)

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

    def add_function_signature(self, func_name: str, signature: str) -> None:
        """注册函数签名提示（输入 ``(`` 后显示参数 tooltip）。

        Parameters
        ----------
        func_name : str
            函数名称，如 ``"lprint"``。
        signature : str
            签名提示文本，支持多行。
        """
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if isinstance(editor, CodeEditorWithCompletion):
                editor.completer.add_signature(func_name, signature)

    @property
    def trace_options(self) -> TraceOptions:
        """获取追踪参数。"""
        return self._trace_options

    @trace_options.setter
    def trace_options(self, options: TraceOptions) -> None:
        """设置追踪参数（不影响用户已手动勾选的追踪复选框状态）。"""
        self._trace_options = options
        self._trace_options.enabled = self.trace_execution_checkbox.isChecked()

    def set_session_file(self, path: str) -> None:
        """更改会话文件路径。"""
        self._session_manager = SessionManager(path)

    def set_init_code(self, code: str) -> None:
        """设置新建 Tab 时自动填入的初始化代码。

        后续通过按钮或快捷键新建的 Tab 将以此代码作为初始内容。
        不影响已有的 Tab。

        Parameters
        ----------
        code : str
            初始化代码文本，传空字符串可清除。
        """
        self._init_code = code
        lprint(f"[脚本编辑器] 初始化代码已更新 ({len(code)} 字符)")

    def get_init_code(self) -> str:
        """返回当前设置的新建 Tab 初始化代码。"""
        return self._init_code

    def inject_variables(self, var_dict: dict) -> None:
        """注入变量到代码执行环境。

        Parameters
        ----------
        var_dict : dict
            变量名到值的映射，如 ``{"data_center": dc_obj}``。
        """
        self._injected_vars.update(var_dict)

    # ==================================================================
    # 历史版本管理
    # ==================================================================

    _HISTORY_DIR = os.path.expanduser("~/.Lugwit/config/.history")
    _FAVORITES_DIR = os.path.expanduser("~/.Lugwit/config/.favorites")

    def _get_history_dir(self) -> str:
        """返回历史版本根目录路径，不存在则创建。"""
        os.makedirs(self._HISTORY_DIR, exist_ok=True)
        return self._HISTORY_DIR

    def _safe_tab_name(self, tab_name: str) -> str:
        """将 tab 名称转为安全的文件夹/文件名（替换特殊字符）。"""
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in tab_name) or "tab"

    def _save_history_version(self, tab_name: str, code: str) -> str:
        """保存一个历史版本文件。

        Parameters
        ----------
        tab_name : str
            Tab 名称。
        code : str
            代码内容。

        Returns
        -------
        str
            保存的文件路径。
        """
        history_dir = self._get_history_dir()
        safe_name = self._safe_tab_name(tab_name)
        tab_dir = os.path.join(history_dir, safe_name)
        os.makedirs(tab_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.py"
        file_path = os.path.join(tab_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        lprint(f"[历史版本] 已保存: {file_path}")
        return file_path

    def _list_history_versions(self, tab_name: str) -> List[Dict]:
        """列出某 tab 的所有历史版本（按时间倒序）。

        Parameters
        ----------
        tab_name : str
            Tab 名称。

        Returns
        -------
        List[Dict]
            每项包含 path, filename, timestamp, size 键。
        """
        history_dir = self._get_history_dir()
        safe_name = self._safe_tab_name(tab_name)
        tab_dir = os.path.join(history_dir, safe_name)
        if not os.path.isdir(tab_dir):
            return []
        results = []
        for fpath in glob.glob(os.path.join(tab_dir, f"{safe_name}_*.py")):
            fname = os.path.basename(fpath)
            try:
                # 文件名格式: {safe_name}_{YYYYMMDD_HHMMSS}.py
                ts_part = fname[len(safe_name) + 1:-3]  # 去掉前缀和 .py
                results.append({
                    "path": fpath,
                    "filename": fname,
                    "timestamp": ts_part,
                    "size": os.path.getsize(fpath),
                })
            except Exception:
                pass
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results

    def _get_latest_version(self, tab_name: str) -> Optional[str]:
        """获取某 tab 最新版本的历史文件路径。

        Parameters
        ----------
        tab_name : str
            Tab 名称。

        Returns
        -------
        Optional[str]
            最新文件路径，无历史记录时返回 None。
        """
        versions = self._list_history_versions(tab_name)
        return versions[0]["path"] if versions else None

    def _restore_history_version(self, file_path: str) -> bool:
        """读取历史文件内容并覆盖到当前编辑器。

        Parameters
        ----------
        file_path : str
            历史文件路径。

        Returns
        -------
        bool
            恢复是否成功。
        """
        editor = self._get_current_editor()
        if editor is None:
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            editor.setPlainText(code)
            lprint(f"[历史版本] 已恢复: {file_path}")
            return True
        except Exception as e:
            lprint(f"[历史版本] 恢复失败: {e}")
            return False

    def _cleanup_old_versions(self, tab_name: str, max_versions: int = 50) -> None:
        """清理超出数量的旧历史版本（保留最新 max_versions 个）。

        Parameters
        ----------
        tab_name : str
            Tab 名称。
        max_versions : int
            最大保留版本数。
        """
        versions = self._list_history_versions(tab_name)
        if len(versions) <= max_versions:
            return
        for item in versions[max_versions:]:
            try:
                os.remove(item["path"])
                lprint(f"[历史版本] 已清理旧版本: {item['filename']}")
            except Exception:
                pass

    def _cleanup_duplicate_versions(self, tab_name: str) -> int:
        """清理同一 tab 下内容重复的历史文件（保留最新的一份）。

        Parameters
        ----------
        tab_name : str
            Tab 名称。

        Returns
        -------
        int
            删除的重复文件数量。
        """
        versions = self._list_history_versions(tab_name)
        lprint(f"[清理重复] tab={tab_name!r}, 找到 {len(versions)} 个历史文件")
        if len(versions) <= 1:
            return 0

        # 按时间倒序遍历，用内容本身做去重 key
        seen_contents: dict = {}  # content -> version dict (保留最新的)
        duplicates = []
        for v in versions:
            try:
                with open(v["path"], "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                lprint(f"[清理重复] 读取失败 {v['filename']}: {e}")
                continue
            if content in seen_contents:
                duplicates.append(v)
            else:
                seen_contents[content] = v

        lprint(f"[清理重复] 发现 {len(duplicates)} 个重复文件")
        removed = 0
        for dup in duplicates:
            try:
                os.remove(dup["path"])
                lprint(f"[清理重复] 已删除: {dup['filename']}")
                removed += 1
            except Exception as e:
                lprint(f"[清理重复] 删除失败 {dup['filename']}: {e}")
        return removed

    def _show_history_dialog(self) -> None:
        """显示历史版本管理对话框，支持覆盖当前Tab或新建Tab。"""
        # 获取所有有历史记录的 tab
        history_dir = self._get_history_dir()
        all_tabs_with_history = []
        if os.path.isdir(history_dir):
            for dirname in sorted(os.listdir(history_dir)):
                tab_dir = os.path.join(history_dir, dirname)
                if os.path.isdir(tab_dir):
                    versions = self._list_history_versions(dirname)
                    if versions:
                        all_tabs_with_history.append(dirname)

        if not all_tabs_with_history:
            QMessageBox.information(self, "历史版本", "暂无任何历史版本记录")
            return

        # 从 .ui 文件加载对话框
        loader = QtUiTools.QUiLoader()
        ui_file = QtCore.QFile(self._HISTORY_UI_FILE)
        if not ui_file.open(QtCore.QFile.ReadOnly):
            raise FileNotFoundError(f"无法打开历史对话框 UI 文件: {self._HISTORY_UI_FILE}")
        try:
            dlg = loader.load(ui_file, self)
        finally:
            ui_file.close()

        if dlg is None:
            raise RuntimeError(f"QUiLoader 加载历史对话框 UI 文件失败: {self._HISTORY_UI_FILE}")

        # 查找控件引用
        tab_combo = dlg.findChild(QComboBox, "tab_combo")
        version_list = dlg.findChild(QListWidget, "version_list")
        preview_text = dlg.findChild(QPlainTextEdit, "preview_text")
        splitter = dlg.findChild(QSplitter, "splitter")
        open_dir_btn = dlg.findChild(QPushButton, "open_dir_btn")
        delete_btn = dlg.findChild(QPushButton, "delete_btn")
        cleanup_dup_btn = dlg.findChild(QPushButton, "cleanup_dup_btn")
        new_tab_btn = dlg.findChild(QPushButton, "new_tab_btn")
        restore_btn = dlg.findChild(QPushButton, "restore_btn")

        # 用 CodeEditorWidget 替换 QPlainTextEdit 占位
        if CodeEditorWidget is not None:
            preview = CodeEditorWidget()
            preview.setReadOnly(True)
            preview.setFont(QFont("Consolas", 10))
            preview.set_highlighter(LogCodeHighlighter)
        else:
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            preview.setFont(QFont("Consolas", 10))
        preview.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #404040;"
        )
        # 替换 splitter 中的第二个 widget
        splitter.replaceWidget(1, preview)
        preview_text.deleteLater()
        splitter.setSizes([250, 550])

        # 填充 Tab 下拉列表
        for tab_name in all_tabs_with_history:
            tab_combo.addItem(tab_name)
        # 默认选中当前 tab（如果存在）
        current_idx = self.code_tab_widget.currentIndex()
        current_tab_name = self.code_tab_widget.tabText(current_idx) if current_idx >= 0 else ""
        safe_current = self._safe_tab_name(current_tab_name) if current_tab_name else ""
        if safe_current in all_tabs_with_history:
            tab_combo.setCurrentIndex(all_tabs_with_history.index(safe_current))

        # 切换 tab 时更新列表
        def _on_tab_changed():
            version_list.clear()
            selected_tab = tab_combo.currentText()
            if not selected_tab:
                return
            versions = self._list_history_versions(selected_tab)
            for v in versions:
                ts = v["timestamp"]
                if len(ts) >= 15:
                    display_ts = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
                else:
                    display_ts = ts
                size_kb = v["size"] / 1024.0
                item = QListWidgetItem(f"{display_ts}  ({size_kb:.1f} KB)")
                item.setData(QtCore.Qt.UserRole, v["path"])
                version_list.addItem(item)
            if version_list.count() > 0:
                version_list.setCurrentRow(0)

        tab_combo.currentIndexChanged.connect(lambda _: _on_tab_changed())

        # 选中列表项时更新预览
        def _on_selection_changed():
            items = version_list.selectedItems()
            if not items:
                preview.clear()
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    preview.setPlainText(f.read())
            except Exception as e:
                preview.setPlainText(f"[读取失败: {e}]")

        version_list.currentItemChanged.connect(lambda *_: _on_selection_changed())

        _on_tab_changed()  # 初始加载（信号已连接，setCurrentRow 会触发预览）

        # 按钮事件处理
        def _on_open_dir():
            selected_tab = tab_combo.currentText()
            if selected_tab:
                tab_dir = os.path.join(self._HISTORY_DIR, selected_tab)
                if os.path.isdir(tab_dir):
                    subprocess.Popen(["explorer", tab_dir])
                else:
                    QMessageBox.information(dlg, "提示", "历史目录不存在")

        def _on_delete():
            items = version_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个历史版本")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            fname = os.path.basename(fpath)
            reply = QMessageBox.question(
                dlg, "确认删除",
                f"确定要删除此历史版本吗？\n\n{fname}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    os.remove(fpath)
                    lprint(f"[历史版本] 已删除: {fpath}")
                    _on_tab_changed()  # 刷新列表
                except Exception as e:
                    QMessageBox.warning(dlg, "删除失败", str(e))

        def _on_cleanup_dup():
            selected_tab = tab_combo.currentText()
            if not selected_tab:
                QMessageBox.warning(dlg, "提示", "请先选择一个 Tab")
                return
            removed = self._cleanup_duplicate_versions(selected_tab)
            QMessageBox.information(dlg, "清理完成", f"已清理 {removed} 个重复的历史文件")
            if removed > 0:
                _on_tab_changed()

        def _on_new_tab():
            items = version_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个历史版本")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                QMessageBox.warning(dlg, "读取失败", str(e))
                return
            # 新建 tab，名称从文件名提取
            fname = os.path.basename(fpath)
            # 去掉时间戳和后缀，如 code_1_20260604_025815.py -> code_1
            parts = fname.rsplit("_", 2)
            new_name = parts[0] if len(parts) >= 3 else fname[:-3]
            editor = self._create_new_tab(tab_name=new_name)
            if editor:
                editor.setPlainText(code)
                lprint(f"[历史版本] 从历史新建 Tab: {new_name}")
            dlg.accept()

        def _on_restore():
            items = version_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个历史版本")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            if self._restore_history_version(fpath):
                dlg.accept()
            else:
                QMessageBox.warning(dlg, "恢复失败", "无法将历史版本恢复到当前编辑器")

        open_dir_btn.clicked.connect(_on_open_dir)
        delete_btn.clicked.connect(_on_delete)
        cleanup_dup_btn.clicked.connect(_on_cleanup_dup)
        new_tab_btn.clicked.connect(_on_new_tab)
        restore_btn.clicked.connect(_on_restore)

        dlg.exec()

    def _get_favorites_dir(self) -> str:
        """返回收藏目录路径，不存在则创建。"""
        os.makedirs(self._FAVORITES_DIR, exist_ok=True)
        return self._FAVORITES_DIR

    def _show_favorites_dialog(self) -> None:
        """显示收藏管理对话框：保存/加载/删除代码片段，含代码预览。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("代码收藏管理")
        dlg.resize(900, 550)

        main_layout = QVBoxLayout(dlg)

        # 输入区域：收藏名称
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("收藏名称:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("输入收藏名称（如：查询资产示例）")
        input_layout.addWidget(name_input)
        save_btn = QPushButton("💾 保存当前代码")
        input_layout.addWidget(save_btn)
        main_layout.addLayout(input_layout)

        # 中间区域：左侧列表 + 右侧预览（QSplitter）
        splitter = QSplitter(QtCore.Qt.Horizontal)

        # 左侧：收藏列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        list_label = QLabel("已收藏的代码片段:")
        left_layout.addWidget(list_label)
        favorites_list = QListWidget()
        favorites_list.setSelectionMode(QListWidget.SingleSelection)
        left_layout.addWidget(favorites_list)
        splitter.addWidget(left_widget)

        # 右侧：代码预览
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        preview_label = QLabel("代码预览:")
        right_layout.addWidget(preview_label)
        preview_editor = QPlainTextEdit()
        preview_editor.setReadOnly(True)
        preview_editor.setFont(QFont("Consolas", 10))
        preview_editor.setPlaceholderText("选择一个收藏以预览代码内容...")
        preview_editor.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #333; }"
        )
        _fav_highlighter = PythonHighlighter(preview_editor.document())
        right_layout.addWidget(preview_editor)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, stretch=1)

        # 按钮区域
        btn_layout = QHBoxLayout()
        load_btn = QPushButton("📥 加载到新Tab")
        overwrite_btn = QPushButton("🔄 覆盖到当前Tab")
        update_fav_btn = QPushButton("⬆️ 更新此收藏")
        delete_btn = QPushButton("🗑️ 删除")
        open_dir_btn = QPushButton("📁 打开目录")
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(overwrite_btn)
        btn_layout.addWidget(update_fav_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(open_dir_btn)
        main_layout.addLayout(btn_layout)

        # 加载收藏列表
        def _refresh_list():
            favorites_list.clear()
            fav_dir = self._get_favorites_dir()
            if not os.path.isdir(fav_dir):
                return
            for filename in sorted(os.listdir(fav_dir)):
                if filename.endswith(".py"):
                    fpath = os.path.join(fav_dir, filename)
                    # 提取名称（去掉时间戳后缀）
                    base = filename[:-3]  # 去掉 .py
                    parts = base.rsplit("_", 1)
                    display_name = parts[0] if len(parts) >= 2 else base
                    item = QListWidgetItem(display_name)
                    item.setData(QtCore.Qt.UserRole, fpath)
                    favorites_list.addItem(item)
            # 刷新后自动选中第一项以触发预览
            if favorites_list.count() > 0:
                favorites_list.setCurrentRow(0)

        # 选中列表项时更新预览（必须在 _refresh_list 之前连接，否则首次选中无效）
        def _on_item_changed(current, previous):
            if current is None:
                preview_editor.clear()
                return
            fpath = current.data(QtCore.Qt.UserRole)
            if not fpath or not os.path.isfile(fpath):
                preview_editor.setPlainText("# 文件不存在")
                return
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    code = f.read()
                preview_editor.setPlainText(code)
            except Exception as e:
                preview_editor.setPlainText(f"# 读取失败: {e}")

        favorites_list.currentItemChanged.connect(_on_item_changed)

        _refresh_list()

        # 保存收藏
        def _on_save():
            name = name_input.text().strip()
            if not name:
                name, ok = QInputDialog.getText(dlg, "输入名称", "请输入收藏名称:")
                if not ok or not name.strip():
                    return
                name = name.strip()

            # 获取当前Tab代码
            editor = self._get_current_editor()
            if editor is None:
                QMessageBox.warning(dlg, "提示", "当前没有打开的代码Tab")
                return
            code = editor.toPlainText()
            if not code.strip():
                QMessageBox.warning(dlg, "提示", "当前Tab没有代码内容")
                return

            # 生成安全的文件名
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_{timestamp}.py"
            fpath = os.path.join(self._get_favorites_dir(), filename)

            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(code)
                lprint(f"[代码收藏] 已保存: {name} -> {filename}")
                name_input.clear()
                _refresh_list()
            except Exception as e:
                QMessageBox.warning(dlg, "保存失败", str(e))

        # 加载收藏到新Tab
        def _on_load():
            items = favorites_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个收藏")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    code = f.read()
                # 提取名称
                base = os.path.basename(fpath)[:-3]
                parts = base.rsplit("_", 1)
                new_name = parts[0] if len(parts) >= 2 else base
                editor = self._create_new_tab(tab_name=new_name)
                if editor:
                    editor.setPlainText(code)
                    lprint(f"[代码收藏] 已加载到新Tab: {new_name}")
                dlg.accept()
            except Exception as e:
                QMessageBox.warning(dlg, "加载失败", str(e))

        # 覆盖到当前Tab
        def _on_overwrite():
            items = favorites_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个收藏")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    code = f.read()
                editor = self._get_current_editor()
                if editor:
                    editor.setPlainText(code)
                    base = os.path.basename(fpath)[:-3]
                    lprint(f"[代码收藏] 已覆盖当前Tab: {base}")
                    dlg.accept()
                else:
                    QMessageBox.warning(dlg, "提示", "当前没有打开的Tab")
            except Exception as e:
                QMessageBox.warning(dlg, "加载失败", str(e))

        # 用当前Tab代码更新选中的收藏
        def _on_update_favorite():
            items = favorites_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个收藏")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            base = os.path.basename(fpath)[:-3]
            display_name = items[0].text()
            # 获取当前Tab代码
            editor = self._get_current_editor()
            if editor is None:
                QMessageBox.warning(dlg, "提示", "当前没有打开的代码Tab")
                return
            code = editor.toPlainText()
            if not code.strip():
                QMessageBox.warning(dlg, "提示", "当前Tab没有代码内容")
                return
            reply = QMessageBox.question(
                dlg, "确认更新",
                f"将当前Tab代码覆盖到收藏：\n\n{display_name}\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(code)
                lprint(f"[代码收藏] 已更新收藏: {base}")
                # 刷新预览
                preview_editor.setPlainText(code)
            except Exception as e:
                QMessageBox.warning(dlg, "更新失败", str(e))

        # 删除收藏
        def _on_delete():
            items = favorites_list.selectedItems()
            if not items:
                QMessageBox.warning(dlg, "提示", "请先选择一个收藏")
                return
            fpath = items[0].data(QtCore.Qt.UserRole)
            fname = os.path.basename(fpath)
            reply = QMessageBox.question(
                dlg, "确认删除",
                f"确定要删除此收藏吗？\n\n{fname}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    os.remove(fpath)
                    lprint(f"[代码收藏] 已删除: {fpath}")
                    _refresh_list()
                except Exception as e:
                    QMessageBox.warning(dlg, "删除失败", str(e))

        # 打开目录
        def _on_open_dir():
            import subprocess
            fav_dir = self._get_favorites_dir()
            if os.path.isdir(fav_dir):
                subprocess.Popen(["explorer", fav_dir])
            else:
                QMessageBox.information(dlg, "提示", "收藏目录不存在")

        save_btn.clicked.connect(_on_save)
        load_btn.clicked.connect(_on_load)
        overwrite_btn.clicked.connect(_on_overwrite)
        update_fav_btn.clicked.connect(_on_update_favorite)
        delete_btn.clicked.connect(_on_delete)
        open_dir_btn.clicked.connect(_on_open_dir)

        dlg.exec()

    def set_save_directory(self, directory: str) -> None:
        """设置代码文件保存目录（主程序退出时自动保存所有Tab代码到此目录）。

        Parameters
        ----------
        directory : str
            保存目录的绝对路径，目录不存在时会自动创建。
        """
        self._save_directory = directory
        if directory:
            os.makedirs(directory, exist_ok=True)
            lprint(f"[代码保存] 保存目录已设置: {directory}")

    def _on_reload_clicked(self) -> None:
        """重载按钮点击处理：内部完成完整的重载流程。

        流程：保存会话 → 从宿主 QTabWidget 移除旧实例 → 清除缓存并重载模块
        → 创建新实例并添加回 QTabWidget → 恢复设置 → 切换焦点。
        """
        if self._tab_widget is None:
            lprint("[脚本编辑器] 未设置宿主 QTabWidget，无法重载", level="WARNING")
            return

        tw = self._tab_widget
        old = self

        # 1. 保存当前会话（确保重载不丢失代码）
        try:
            old._session_manager.save_session(old.code_tab_widget)
        except Exception:
            pass

        # 2. 从宿主 QTabWidget 移除旧实例
        idx = tw.indexOf(old)
        if idx >= 0:
            tw.removeTab(idx)
        old.deleteLater()

        # 3. 深度重载模块（清除 sys.modules 中所有子模块缓存）
        try:
            from l_script_editor import reload_mod as _reload_mod
            ReloadedClass = _reload_mod()
        except Exception as e:
            lprint(f"[脚本编辑器] 重载模块失败: {e}", level="ERROR")
            traceback.print_exc()
            # 重载失败，恢复旧实例
            tw.insertTab(max(idx, 0), old, old._tab_display_name)
            return

        # 4. 用重载后的类创建新实例（复用原参数，重载不依赖外部）
        new = ReloadedClass(
            parent=tw,
            main_window=old._main_window,
            session_file=old._session_file,
            tab_widget=tw,
            tab_name=old._tab_display_name,
            save_directory=old._save_directory,
            after_reload_hook=old._after_reload_hook,
            init_code=old._init_code,
        )

        # 5. 添加回宿主 QTabWidget
        tw.addTab(new, old._tab_display_name)

        # 6. 调用重载后回调
        if new._after_reload_hook is not None:
            try:
                new._after_reload_hook(new)
            except Exception:
                traceback.print_exc()

        # 7. 切换到新标签页
        tw.setCurrentWidget(new)

        lprint("[脚本编辑器] ✓ 脚本编辑器已重载")

    def save_all_tabs(self, directory: str = "") -> int:
        """将所有 Tab 的代码保存为历史版本 .py 文件。

        文件命名格式：``{tab_name}_{YYYYMMDD_HHMMSS}.py``
        存储路径：``~/.Lugwit/config/.history/{tab_name}/``
        空代码的 Tab 跳过；内容与最新历史文件相同时也跳过。

        Parameters
        ----------
        directory : str
            兼容旧接口，参数已忽略。

        Returns
        -------
        int
            成功保存的 Tab 数量。
        """
        saved_count = 0
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if not editor or not hasattr(editor, "toPlainText"):
                continue

            code = editor.toPlainText()
            if not code.strip():
                continue

            tab_name = self.code_tab_widget.tabText(i) or f"tab_{i + 1}"

            # 与最新历史文件比对，内容未变化则跳过
            latest_path = self._get_latest_version(tab_name)
            if latest_path:
                try:
                    with open(latest_path, "r", encoding="utf-8") as f:
                        latest_code = f.read()
                    if latest_code == code:
                        lprint(f"[代码保存] '{tab_name}' 内容未变化，跳过")
                        continue
                except Exception:
                    pass  # 读取失败时正常保存

            try:
                self._save_history_version(tab_name, code)
                self._cleanup_old_versions(tab_name)
                saved_count += 1
            except Exception as e:
                lprint(f"[代码保存] 保存历史版本 '{tab_name}' 失败: {e}")

        if saved_count > 0:
            lprint(f"[代码保存] 已保存 {saved_count} 个 Tab 的代码到历史版本目录")
        return saved_count

    def get_all_tab_codes(self) -> List[Dict[str, str]]:
        """获取所有Tab的代码内容。

        Returns
        -------
        List[Dict[str, str]]
            每项包含 ``name`` 和 ``code`` 键。
        """
        result = []
        for i in range(self.code_tab_widget.count()):
            editor = self.code_tab_widget.widget(i)
            if not editor or not hasattr(editor, 'toPlainText'):
                continue
            tab_name = self.code_tab_widget.tabText(i) or f"tab_{i + 1}"
            result.append({
                "name": tab_name,
                "code": editor.toPlainText(),
            })
        return result
