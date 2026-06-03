# -*- coding: utf-8 -*-
"""
Python 语法高亮器 - l_script_editor

支持 f-string、多行字符串、细粒度语法高亮。
"""

from __future__ import print_function, unicode_literals

import re

from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont

import Lugwit_Module as LM
lprint = LM.lprint

from .syntax_colors import SyntaxHighlightColors as SC

# 多行字符串状态常量
STATE_NORMAL = 0
STATE_MULTILINE_STRING_DOUBLE = 1
STATE_MULTILINE_STRING_SINGLE = 2
STATE_MULTILINE_FSTRING_DOUBLE = 3
STATE_MULTILINE_FSTRING_SINGLE = 4


class PythonHighlighter(QSyntaxHighlighter):
    """Python语法高亮器 - 支持f-string和多行字符串"""

    def __init__(self, document):
        super(PythonHighlighter, self).__init__(document)
        self.setup_patterns()

    def setup_patterns(self):
        """设置高亮模式"""
        self.keyword_pattern = re.compile(r'\b(?:' + '|'.join([
            'and', 'as', 'assert', 'break', 'continue',
            'del', 'elif', 'else', 'except', 'finally', 'for',
            'from', 'global', 'if', 'import', 'in', 'is', 'lambda',
            'not', 'or', 'pass', 'print', 'raise', 'return', 'try',
            'while', 'with', 'yield', 'None', 'True', 'False'
        ]) + r')\b')

        # class, def 单独处理
        self.class_keyword_pattern = re.compile(r'\bclass\s+([A-Za-z_][A-Za-z0-9_]*)')
        self.def_keyword_pattern = re.compile(r'\bdef\s+([A-Za-z_][A-Za-z0-9_]*)')

        # 函数调用模式
        self.function_call_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()')

        # 类名模式（大写字母开头）
        self.class_name_pattern = re.compile(r'\b([A-Z][A-Za-z0-9_]*)\b')

        # 模块/对象属性访问
        self.module_attr_pattern = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\.')

        # 属性访问（点号后的属性名）
        self.attr_access_pattern = re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)')

        # f-string 模式
        self.fstring_pattern = re.compile(r'[fF]("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')')
        # 普通字符串模式
        self.string_pattern = re.compile(r'(?<![fF])("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')')
        # 注释模式
        self.comment_pattern = re.compile(r'#[^\n]*')
        # 数字模式
        self.number_pattern = re.compile(r'\b\d+\.?\d*\b')
        # 装饰器模式
        self.decorator_pattern = re.compile(r'@[A-Za-z_][A-Za-z0-9_]*')

    def highlightBlock(self, text):
        """高亮文本块"""
        try:
            # 首先处理多行字符串
            string_regions = self._handle_multiline_strings(text)

            # 处理注释
            for match in self.comment_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.COMMENT.to_qcolor())
                    fmt.setFontItalic(True)
                    self.setFormat(match.start(), match.end() - match.start(), fmt)

            # 处理单行 f-string
            for match in self.fstring_pattern.finditer(text):
                string_start = match.start()
                string_end = match.end()

                if self._is_in_string(text, string_start, string_regions):
                    continue

                fmt = QTextCharFormat()
                fmt.setForeground(SC.STRING.to_qcolor())
                self.setFormat(string_start, string_end - string_start, fmt)

                self._highlight_fstring_braces(text, string_start, string_end)

            # 处理普通单行字符串
            for match in self.string_pattern.finditer(text):
                if self._is_in_string(text, match.start(), string_regions):
                    continue

                fmt = QTextCharFormat()
                fmt.setForeground(SC.STRING.to_qcolor())
                self.setFormat(match.start(), match.end() - match.start(), fmt)

            # 处理装饰器
            for match in self.decorator_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.DECORATOR.to_qcolor())
                    fmt.setFontItalic(True)
                    self.setFormat(match.start(), match.end() - match.start(), fmt)

            # 处理 class 定义
            for match in self.class_keyword_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.KEYWORD.to_qcolor())
                    self.setFormat(match.start(), 5, fmt)

                    class_name_start = match.start(1)
                    class_name_length = len(match.group(1))
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.CLASS_DEFINITION.to_qcolor())
                    fmt.setFontWeight(QFont.Weight.Bold)
                    self.setFormat(class_name_start, class_name_length, fmt)

            # 处理 def 定义
            for match in self.def_keyword_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.KEYWORD.to_qcolor())
                    self.setFormat(match.start(), 3, fmt)

                    func_name_start = match.start(1)
                    func_name_length = len(match.group(1))
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.FUNCTION_DEFINITION.to_qcolor())
                    fmt.setFontWeight(QFont.Weight.Bold)
                    self.setFormat(func_name_start, func_name_length, fmt)

            # 处理模块/对象属性访问
            for match in self.module_attr_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    obj_name = match.group(1)
                    obj_name_start = match.start(1)
                    obj_name_length = len(obj_name)

                    is_root_object = False
                    if obj_name_start > 0:
                        before_char = text[obj_name_start - 1]
                        if not (before_char == '.' or before_char.isalnum() or before_char == '_'):
                            is_root_object = True
                    else:
                        is_root_object = True

                    fmt = QTextCharFormat()
                    if is_root_object:
                        fmt.setForeground(SC.ROOT_OBJECT.to_qcolor())
                    else:
                        fmt.setForeground(SC.OBJECT_NAME.to_qcolor())
                    self.setFormat(obj_name_start, obj_name_length, fmt)

            # 处理属性访问（.attribute）
            for match in self.attr_access_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    attr_name = match.group(1)
                    attr_name_start = match.start(1)
                    attr_name_length = len(attr_name)

                    after_pos = match.end()
                    is_callable = False
                    if after_pos < len(text):
                        remaining = text[after_pos:].lstrip()
                        if remaining.startswith('('):
                            is_callable = True

                    fmt = QTextCharFormat()
                    if is_callable:
                        fmt.setForeground(SC.FUNCTION_CALL.to_qcolor())
                    else:
                        fmt.setForeground(SC.ATTRIBUTE.to_qcolor())
                    self.setFormat(attr_name_start, attr_name_length, fmt)

            # 处理函数调用
            for match in self.function_call_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    func_name = match.group(1)
                    func_start = match.start(1)

                    before_text = text[:func_start].rstrip()
                    if not (before_text.endswith('def') or before_text.endswith('class')):
                        fmt = QTextCharFormat()
                        fmt.setForeground(SC.FUNCTION_CALL.to_qcolor())
                        self.setFormat(func_start, len(func_name), fmt)

            # 处理类名（大写开头的标识符）
            for match in self.class_name_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    class_name = match.group(1)
                    class_start = match.start(1)

                    before_text = text[:class_start].rstrip()
                    if not before_text.endswith('class'):
                        fmt = QTextCharFormat()
                        fmt.setForeground(SC.CLASS_NAME.to_qcolor())
                        self.setFormat(class_start, len(class_name), fmt)

            # 处理关键字
            for match in self.keyword_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.KEYWORD.to_qcolor())
                    self.setFormat(match.start(), match.end() - match.start(), fmt)

            # 处理数字
            for match in self.number_pattern.finditer(text):
                if not self._is_in_string(text, match.start(), string_regions):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.NUMBER.to_qcolor())
                    self.setFormat(match.start(), match.end() - match.start(), fmt)

        except Exception:
            pass

    # ------------------------------------------------------------------
    # 多行字符串处理
    # ------------------------------------------------------------------

    def _handle_multiline_strings(self, text):
        """处理多行字符串和多行f-string，返回字符串占用的区域列表"""
        string_regions = []
        current_state = self.previousBlockState()
        if current_state == -1:
            current_state = STATE_NORMAL

        pos = 0

        # 处理从上一行延续的多行字符串
        if current_state != STATE_NORMAL:
            if current_state == STATE_MULTILINE_STRING_DOUBLE:
                end_marker = '"""'
                is_fstring = False
            elif current_state == STATE_MULTILINE_STRING_SINGLE:
                end_marker = "'''"
                is_fstring = False
            elif current_state == STATE_MULTILINE_FSTRING_DOUBLE:
                end_marker = '"""'
                is_fstring = True
            elif current_state == STATE_MULTILINE_FSTRING_SINGLE:
                end_marker = "'''"
                is_fstring = True
            else:
                end_marker = None
                is_fstring = False

            if end_marker:
                end_pos = text.find(end_marker)
                if end_pos >= 0:
                    end_pos += len(end_marker)
                    string_regions.append((0, end_pos))

                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.STRING.to_qcolor())
                    self.setFormat(0, end_pos, fmt)

                    if is_fstring:
                        self._highlight_fstring_braces(text, 0, end_pos)

                    current_state = STATE_NORMAL
                    pos = end_pos
                else:
                    string_regions.append((0, len(text)))

                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.STRING.to_qcolor())
                    self.setFormat(0, len(text), fmt)

                    if is_fstring:
                        self._highlight_fstring_braces(text, 0, len(text))

                    self.setCurrentBlockState(current_state)
                    return string_regions

        # 处理当前行新开始的多行字符串
        while pos < len(text):
            in_region = False
            for start, end in string_regions:
                if start <= pos < end:
                    in_region = True
                    break

            if in_region:
                pos += 1
                continue

            remaining = text[pos:]

            if remaining.startswith('f"""') or remaining.startswith('F"""'):
                start_marker = '"""'
                marker_len = 4
                is_fstring = True
                new_state = STATE_MULTILINE_FSTRING_DOUBLE
            elif remaining.startswith("f'''") or remaining.startswith("F'''"):
                start_marker = "'''"
                marker_len = 4
                is_fstring = True
                new_state = STATE_MULTILINE_FSTRING_SINGLE
            elif remaining.startswith('"""'):
                start_marker = '"""'
                marker_len = 3
                is_fstring = False
                new_state = STATE_MULTILINE_STRING_DOUBLE
            elif remaining.startswith("'''"):
                start_marker = "'''"
                marker_len = 3
                is_fstring = False
                new_state = STATE_MULTILINE_STRING_SINGLE
            else:
                pos += 1
                continue

            string_start = pos
            pos += marker_len

            end_marker = start_marker
            end_pos = text.find(end_marker, pos)

            if end_pos >= 0:
                end_pos += len(end_marker)
                string_regions.append((string_start, end_pos))

                fmt = QTextCharFormat()
                fmt.setForeground(SC.STRING.to_qcolor())
                self.setFormat(string_start, end_pos - string_start, fmt)

                if is_fstring:
                    self._highlight_fstring_braces(text, string_start, end_pos)

                pos = end_pos
            else:
                string_regions.append((string_start, len(text)))

                fmt = QTextCharFormat()
                fmt.setForeground(SC.STRING.to_qcolor())
                self.setFormat(string_start, len(text) - string_start, fmt)

                if is_fstring:
                    self._highlight_fstring_braces(text, string_start, len(text))

                current_state = new_state
                break

        self.setCurrentBlockState(current_state)
        return string_regions

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _is_in_string(self, text, pos, string_regions=None):
        """检查位置是否在字符串内"""
        if string_regions:
            for start, end in string_regions:
                if start <= pos < end:
                    return True

        before_text = text[:pos]
        single_quotes = before_text.count("'") - before_text.count("\\'")
        double_quotes = before_text.count('"') - before_text.count('\\"')
        return (single_quotes % 2 == 1) or (double_quotes % 2 == 1)

    def _highlight_fstring_braces(self, text, string_start, string_end):
        """高亮f-string中的大括号表达式"""
        string_text = text[string_start:string_end]

        brace_depth = 0
        expr_start = -1

        for i, char in enumerate(string_text):
            actual_pos = string_start + i

            if char == '{':
                if i + 1 < len(string_text) and string_text[i + 1] == '{':
                    continue
                if brace_depth == 0:
                    expr_start = actual_pos
                brace_depth += 1

            elif char == '}':
                if i + 1 < len(string_text) and string_text[i + 1] == '}':
                    continue
                brace_depth -= 1

                if brace_depth == 0 and expr_start >= 0:
                    expr_content_start = expr_start + 1
                    expr_content_end = actual_pos
                    expr_content = text[expr_content_start:expr_content_end]

                    self._highlight_expression_in_fstring(expr_content, expr_content_start)

                    brace_format = QTextCharFormat()
                    brace_format.setForeground(SC.FSTRING_BRACE.to_qcolor())
                    brace_format.setFontWeight(QFont.Weight.Bold)
                    self.setFormat(expr_start, 1, brace_format)
                    self.setFormat(actual_pos, 1, brace_format)

                    expr_start = -1

    def _highlight_expression_in_fstring(self, expr_text, expr_start):
        """对f-string中的表达式内容应用细粒度语法高亮"""
        if not expr_text:
            return

        try:
            # 关键字
            for match in self.keyword_pattern.finditer(expr_text):
                fmt = QTextCharFormat()
                fmt.setForeground(SC.KEYWORD.to_qcolor())
                abs_start = expr_start + match.start()
                abs_length = match.end() - match.start()
                self.setFormat(abs_start, abs_length, fmt)

            # 模块/对象属性访问
            for match in self.module_attr_pattern.finditer(expr_text):
                obj_name = match.group(1)
                obj_name_start = match.start(1)
                obj_name_length = len(obj_name)

                is_root_object = False
                if obj_name_start > 0:
                    before_char = expr_text[obj_name_start - 1]
                    if not (before_char == '.' or before_char.isalnum() or before_char == '_'):
                        is_root_object = True
                else:
                    is_root_object = True

                fmt = QTextCharFormat()
                if is_root_object:
                    fmt.setForeground(SC.ROOT_OBJECT.to_qcolor())
                else:
                    fmt.setForeground(SC.OBJECT_NAME.to_qcolor())
                abs_start = expr_start + obj_name_start
                self.setFormat(abs_start, obj_name_length, fmt)

            # 属性访问
            for match in self.attr_access_pattern.finditer(expr_text):
                attr_name = match.group(1)
                attr_name_start = match.start(1)
                attr_name_length = len(attr_name)

                after_pos = match.end()
                is_callable = False
                if after_pos < len(expr_text):
                    remaining = expr_text[after_pos:].lstrip()
                    if remaining.startswith('('):
                        is_callable = True

                fmt = QTextCharFormat()
                if is_callable:
                    fmt.setForeground(SC.FUNCTION_CALL.to_qcolor())
                else:
                    fmt.setForeground(SC.ATTRIBUTE.to_qcolor())
                abs_start = expr_start + attr_name_start
                self.setFormat(abs_start, attr_name_length, fmt)

            # 函数调用
            for match in self.function_call_pattern.finditer(expr_text):
                func_name = match.group(1)
                func_start = match.start(1)

                if not self.keyword_pattern.match(func_name):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.FUNCTION_CALL.to_qcolor())
                    abs_start = expr_start + func_start
                    self.setFormat(abs_start, len(func_name), fmt)

            # 类名
            for match in self.class_name_pattern.finditer(expr_text):
                class_name = match.group(1)
                class_start = match.start(1)

                if not self.keyword_pattern.match(class_name):
                    fmt = QTextCharFormat()
                    fmt.setForeground(SC.CLASS_NAME.to_qcolor())
                    abs_start = expr_start + class_start
                    self.setFormat(abs_start, len(class_name), fmt)

            # 数字
            for match in self.number_pattern.finditer(expr_text):
                fmt = QTextCharFormat()
                fmt.setForeground(SC.NUMBER.to_qcolor())
                abs_start = expr_start + match.start()
                abs_length = match.end() - match.start()
                self.setFormat(abs_start, abs_length, fmt)

        except Exception as e:
            lprint(f"[语法高亮] f-string表达式高亮出错: {e}")
