# -*- coding: utf-8 -*-
"""
l_script_editor - 独立可复用的 Python 脚本编辑器组件库

提供代码编辑、自动补全、语法高亮、会话管理等功能。
"""

import importlib
import sys

from .script_editor_tab import ScriptEditorTab, TraceOptions
from .code_completer import CodeCompleter
from .code_editor import CodeEditorWithCompletion
from .python_highlighter import PythonHighlighter
from .syntax_colors import SyntaxHighlightColors
from .session_manager import SessionManager

_PKG_NAME = "l_script_editor"


def reload_mod():
    """深度重载 l_script_editor 及其所有子模块，返回重载后的 ScriptEditorTab 类。

    ``importlib.reload`` 仅重载顶层包，不会递归重载子模块。
    此函数通过清除 ``sys.modules`` 中所有 ``l_script_editor.*`` 条目后
    重新 import，确保子模块（code_editor、session_manager 等）也一并刷新。

    调用方需在重载后重新创建 ScriptEditorTab 实例，示例::

        ReloadedScriptEditorTab = reload_mod()
        new_tab = ReloadedScriptEditorTab(parent=..., main_window=...)

    Returns
    -------
    type
        重载后的 ScriptEditorTab 类。
    """
    # 1. 收集所有 l_script_editor 开头的模块名（包括子模块）
    keys_to_remove = [k for k in sys.modules if k == _PKG_NAME or k.startswith(f"{_PKG_NAME}.")]
    # 2. 从 sys.modules 中全部删除，强制下次 import 时重新加载
    for k in keys_to_remove:
        del sys.modules[k]
    # 3. 重新 import 整个包
    mod = importlib.import_module(_PKG_NAME)
    return mod.ScriptEditorTab


__all__ = [
    "ScriptEditorTab",
    "TraceOptions",
    "CodeCompleter",
    "CodeEditorWithCompletion",
    "PythonHighlighter",
    "SyntaxHighlightColors",
    "SessionManager",
    "reload_mod",
]
