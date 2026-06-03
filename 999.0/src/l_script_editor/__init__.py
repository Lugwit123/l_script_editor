# -*- coding: utf-8 -*-
"""
l_script_editor - 独立可复用的 Python 脚本编辑器组件库

提供代码编辑、自动补全、语法高亮、会话管理等功能。
"""

from .script_editor_tab import ScriptEditorTab
from .code_completer import CodeCompleter
from .code_editor import CodeEditorWithCompletion
from .python_highlighter import PythonHighlighter
from .syntax_colors import SyntaxHighlightColors
from .session_manager import SessionManager

__all__ = [
    "ScriptEditorTab",
    "CodeCompleter",
    "CodeEditorWithCompletion",
    "PythonHighlighter",
    "SyntaxHighlightColors",
    "SessionManager",
]
