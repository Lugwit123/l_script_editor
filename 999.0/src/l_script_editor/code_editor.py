# -*- coding: utf-8 -*-
"""
代码编辑器 - l_script_editor

支持代码自动补全、快捷转换的 Python 代码编辑器。
行号显示、当前行高亮、Ctrl+滚轮缩放等功能复用自 l_qt_wgt_lib 的 LineNumberTextEdit。
"""

from __future__ import print_function, unicode_literals

import re

from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit

import Lugwit_Module as LM
lprint = LM.lprint

from l_qt_wgt_lib.smart_widget.code_editor import LineNumberTextEdit
from .code_completer import CodeCompleter


# ============================================================================
# CodeEditorWithCompletion - 支持补全和快捷转换的编辑器
# ============================================================================

class CodeEditorWithCompletion(LineNumberTextEdit):
    """支持代码补全和快捷转换的编辑器

    继承自 ``l_qt_wgt_lib.smart_widget.code_editor.LineNumberTextEdit``，
    复用行号显示、当前行高亮、Ctrl+滚轮缩放等功能，并叠加：

    - 代码自动补全（输入 ``.`` 后自动弹出，输入2+字符触发）
    - 快捷转换（``lp.xxx`` -> ``lprint(xxx)`` 等）
    - 粘贴清理（U+2028/U+2029 -> ``\\n``）
    - Ctrl+Space 手动触发补全
    - 调试模式开关
    - 补全缓存优化
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # 创建补全器
        self.completer = CodeCompleter(self)

        # 配置补全器弹窗尺寸和行为
        self.completer.setWidget(self)
        self.completer.setMaxVisibleItems(10)
        self.completer.activated.connect(self.insert_completion)

        # 设置弹窗最小尺寸
        popup = self.completer.popup()
        popup.setMinimumWidth(200)
        popup.setMaximumWidth(400)
        popup.setMinimumHeight(50)
        popup.setMaximumHeight(300)

        # 配置选项
        self.debug_mode = False  # 调试模式开关
        self.enable_shortcuts = True  # 启用快捷转换

        # 补全缓存
        self._completion_cache = {}
        self._last_completion_path = ""

        # 快捷转换映射
        self.shortcut_map = {
            'lprint': 'lprint',
            'p': 'print',
            'dir': 'lprint(dir)',
            'type': 'lprint(type)',
            'len': 'lprint(len)'
        }

    def clear_completion_cache(self):
        """清理补全缓存"""
        self._completion_cache.clear()
        self._last_completion_path = ""

    # ------------------------------------------------------------------
    # 补全插入
    # ------------------------------------------------------------------

    def insert_completion(self, completion):
        """插入补全文本（支持多种快捷转换）"""
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        current_word = cursor.selectedText()

        if self.debug_mode:
            lprint(f"[补全调试] 选择了补全项: '{completion}'")
            lprint(f"[补全调试] 当前单词: '{current_word}'")

        # 特殊处理：快捷转换
        if self.enable_shortcuts and str(completion) in self.shortcut_map:
            shortcut_type = self.shortcut_map[str(completion)]

            full_line = self.textCursor().block().text()
            cursor_position = self.textCursor().position()
            line_start = self.textCursor().block().position()
            text_before_cursor = full_line[:cursor_position - line_start]

            if self.debug_mode:
                lprint(f"[补全调试] 检测到快捷转换: {completion} -> {shortcut_type}")
                lprint(f"[补全调试] 光标前文本: '{text_before_cursor}'")

            if text_before_cursor.endswith('.' + current_word):
                obj_part = text_before_cursor[:-(len(current_word) + 1)]

                if self.debug_mode:
                    lprint(f"[补全调试] 提取的对象部分: '{obj_part}'")

                if obj_part and self._is_valid_object_expression(obj_part):
                    cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                    cursor.removeSelectedText()

                    indent_match = re.match(r'^[ \t]*', obj_part)
                    indent = indent_match.group(0) if indent_match else ''
                    clean_obj = obj_part.strip()

                    if shortcut_type == 'lprint':
                        new_text = f'{indent}lprint({clean_obj})'
                    elif shortcut_type == 'print':
                        new_text = f'{indent}print({clean_obj})'
                    elif shortcut_type == 'lprint(dir)':
                        new_text = f'{indent}lprint(dir({clean_obj}))'
                    elif shortcut_type == 'lprint(type)':
                        new_text = f'{indent}lprint(type({clean_obj}))'
                    elif shortcut_type == 'lprint(len)':
                        new_text = f'{indent}lprint(len({clean_obj}))'
                    else:
                        new_text = f'{indent}{shortcut_type}({clean_obj})'

                    cursor.insertText(new_text)
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                    self.setTextCursor(cursor)

                    if self.debug_mode:
                        lprint(f"[补全调试] 转换完成: '{new_text}'")
                    return
                else:
                    if self.debug_mode:
                        lprint("[补全调试] 对象部分无效")
            else:
                if self.debug_mode:
                    lprint(f"[补全调试] 不是以 .{current_word} 结尾")

        # 正常补全处理
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def _is_valid_object_expression(self, expr):
        """检查是否是有效的对象表达式"""
        if not expr:
            return False
        expr = expr.strip()
        if not expr:
            return False

        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._[]()')
        for char in expr:
            if char not in allowed_chars:
                return False

        if expr[0].isalpha() or expr[0] == '_':
            return True

        if '.' in expr:
            parts = expr.split('.')
            for part in parts:
                if part and not (part[0].isalpha() or part[0] == '_'):
                    return False
            return True

        return False

    # ------------------------------------------------------------------
    # 调试/配置
    # ------------------------------------------------------------------

    def set_debug_mode(self, enabled):
        """设置调试模式"""
        self.debug_mode = enabled
        if self.debug_mode:
            lprint("[配置] 调试模式已启用")
        else:
            lprint("[配置] 调试模式已禁用")

    def set_shortcuts_enabled(self, enabled):
        """设置快捷转换是否启用"""
        self.enable_shortcuts = enabled
        if self.debug_mode:
            status = "启用" if enabled else "禁用"
            lprint(f"[配置] 快捷转换已{status}")

    def add_custom_shortcut(self, trigger, target):
        """添加自定义快捷转换"""
        if self.debug_mode:
            lprint(f"[配置] 添加自定义快捷: {trigger} -> {target}")
        self.shortcut_map[trigger] = target

    # ------------------------------------------------------------------
    # 文本提取
    # ------------------------------------------------------------------

    def text_under_cursor(self):
        """获取光标下的文本（用于匹配补全）"""
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor.selectedText()

    def get_full_path_under_cursor(self):
        """获取光标前的完整点分路径（如 dw.data_center）"""
        try:
            cursor = self.textCursor()
            position = cursor.position()

            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
            line_text = cursor.selectedText()

            if not line_text:
                return ""

            # 从右向左扫描，构建路径
            path_chars = []
            i = len(line_text) - 1

            while i >= 0 and line_text[i].isspace():
                i -= 1

            while i >= 0:
                char = line_text[i]
                if char.isalnum() or char in '._':
                    path_chars.append(char)
                    i -= 1
                else:
                    break

            if not path_chars:
                return ""

            full_path = ''.join(reversed(path_chars))

            if full_path and (full_path[0].isalpha() or full_path[0] == '_'):
                return full_path

            return ""

        except Exception as e:
            lprint(f"[路径提取] 异常: {str(e)}")
            return ""

    # ------------------------------------------------------------------
    # 粘贴清理
    # ------------------------------------------------------------------

    def insertFromMimeData(self, source):
        """重写粘贴方法，清理不可见的Unicode字符"""
        if source.hasText():
            text = source.text()
            text = text.replace('\u2028', '\n').replace('\u2029', '\n')
            cleaned_source = QtCore.QMimeData()
            cleaned_source.setText(text)
            super().insertFromMimeData(cleaned_source)
        else:
            super().insertFromMimeData(source)

    # ------------------------------------------------------------------
    # 按键事件
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        """处理按键事件 - 叠加补全逻辑到父类行为之上"""
        try:
            # 如果补全器正在显示
            if self.completer.popup().isVisible():
                # 回车键：如果没有选中项，自动选择第一个
                if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                    current_index = self.completer.popup().currentIndex()

                    if not current_index.isValid():
                        model = self.completer.popup().model()
                        if model and model.rowCount() > 0:
                            first_index = model.index(0, 0)
                            if first_index.isValid():
                                self.completer.popup().setCurrentIndex(first_index)
                                first_completion = model.data(first_index, QtCore.Qt.ItemDataRole.DisplayRole)
                                self.insert_completion(first_completion)
                                self.completer.popup().hide()
                                return
                    else:
                        pass  # 有选中项，交给补全器处理

                    event.ignore()
                    return

                # 上下箭头键：允许用户选择补全项
                elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    popup = self.completer.popup()
                    model = popup.model()

                    if model and model.rowCount() > 0:
                        current_index = popup.currentIndex()

                        if event.key() == Qt.Key.Key_Down:
                            if not current_index.isValid():
                                new_index = model.index(0, 0)
                            else:
                                row = current_index.row()
                                if row < model.rowCount() - 1:
                                    new_index = model.index(row + 1, 0)
                                else:
                                    new_index = current_index
                        else:  # Key_Up
                            if not current_index.isValid():
                                new_index = model.index(model.rowCount() - 1, 0)
                            else:
                                row = current_index.row()
                                if row > 0:
                                    new_index = model.index(row - 1, 0)
                                else:
                                    new_index = current_index

                        popup.setCurrentIndex(new_index)
                    return

                # 其他特殊按键交给补全器处理
                elif event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Tab):
                    event.ignore()
                    return

            # Ctrl+Space 触发补全
            if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.show_completions()
                return

            # 调用父类处理正常按键（包括 LineNumberTextEdit 的图片粘贴等）
            super().keyPressEvent(event)

            # 输入 . 后自动显示补全
            if event.text() == '.':
                self.show_completions()
            # 输入字母数字且长度>=2时触发补全
            elif event.text().isalnum():
                text = self.text_under_cursor()
                if len(text) >= 2:
                    self.show_completions()

        except Exception as e:
            lprint(f"[按键事件] 异常: {str(e)}")

    # ------------------------------------------------------------------
    # 补全显示
    # ------------------------------------------------------------------

    def show_completions(self):
        """显示补全列表（支持逐级动态补全）"""
        try:
            full_path = self.get_full_path_under_cursor()
            completion_prefix = self.text_under_cursor()

            # 缓存优化
            if full_path == self._last_completion_path and full_path in self._completion_cache:
                completions = self._completion_cache[full_path]
            else:
                completions = self._get_dynamic_completions(full_path)
                self._completion_cache[full_path] = completions
                self._last_completion_path = full_path

            if completions:
                model = QtCore.QStringListModel(completions, self)
                self.completer.setModel(model)
                self.completer.setCompletionPrefix(completion_prefix)

                cursor_rect = self.cursorRect()
                cursor_rect.setWidth(
                    self.completer.popup().sizeHintForColumn(0) +
                    self.completer.popup().verticalScrollBar().sizeHint().width()
                )
                self.completer.complete(cursor_rect)

                # 默认不选中任何项目
                popup = self.completer.popup()
                if popup.isVisible():
                    popup.clearSelection()
                    popup.setCurrentIndex(QtCore.QModelIndex())

        except Exception as e:
            lprint(f"[补全] 异常: {str(e)}")

    def _get_dynamic_completions(self, full_path):
        """根据完整路径动态生成补全选项"""
        try:
            parts = full_path.split('.') if full_path else []

            # 情况1: 输入某个模块名（在 api_tree 中）
            if len(parts) == 1 and parts[0] in self.completer.api_tree:
                api_tree = self.completer.api_tree
                result = sorted(list(api_tree.keys()))
                return result

            # 情况2: 输入 module.xxx（正在输入第二级）
            elif len(parts) == 2 and parts[0] in self.completer.api_tree:
                second_part = parts[1]
                api_tree = self.completer.api_tree

                # 检查光标前最后一个字符是否是点
                cursor = self.textCursor()
                position = cursor.position()
                cursor.setPosition(max(0, position - 1))
                cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
                last_char = cursor.selectedText()

                if last_char == '.':
                    if second_part in api_tree:
                        children = api_tree[second_part]
                        return sorted(list(children))
                else:
                    result = sorted(list(api_tree.keys()))
                    return result

            # 情况3: 输入 module.xxx.yyy（正在输入第三级）
            elif len(parts) == 3 and parts[0] in self.completer.api_tree:
                parent_attr = parts[1]
                api_tree = self.completer.api_tree

                if parent_attr in api_tree:
                    children = api_tree[parent_attr]
                    return sorted(list(children))

            # 情况4: 其他情况，返回通用补全
            python_keywords = [
                'and', 'as', 'assert', 'break', 'class', 'continue',
                'def', 'del', 'elif', 'else', 'except', 'False', 'finally', 'for',
                'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'None',
                'not', 'or', 'pass', 'raise', 'return', 'True', 'try',
                'while', 'with', 'yield'
            ]

            python_builtins = [
                'abs', 'all', 'any', 'bin', 'bool', 'bytes',
                'chr', 'dict', 'dir', 'enumerate', 'filter', 'float',
                'help', 'hex', 'int', 'isinstance', 'len', 'lprint', 'list',
                'map', 'max', 'min', 'next', 'object', 'oct',
                'open', 'ord', 'print', 'range', 'repr',
                'round', 'set', 'sorted', 'str', 'sum', 'super',
                'tuple', 'type', 'zip',
                'p', 'dir', 'type', 'len'
            ]

            # 添加 API 树顶级项
            api_top = list(self.completer.api_tree.keys()) if self.completer.api_tree else []

            return python_keywords + python_builtins + api_top

        except Exception as e:
            lprint(f"[动态补全] 异常: {str(e)}")
            return []
