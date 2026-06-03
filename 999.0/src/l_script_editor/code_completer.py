# -*- coding: utf-8 -*-
"""
代码补全器 - l_script_editor

通用的 Python 代码补全器，支持注入自定义 API 树和补全项。
"""

from __future__ import print_function, unicode_literals

from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter

import Lugwit_Module as LM
lprint = LM.lprint


class CodeCompleter(QCompleter):
    """代码补全器 - 动态获取补全内容

    功能：
    - Python 关键字 + 内置函数补全
    - 可注入自定义 API 树（树形结构，支持逐级补全）
    - 快捷转换映射（lp -> lprint, p -> print 等）
    """

    def __init__(self, parent=None):
        super(CodeCompleter, self).__init__(parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setWrapAround(False)

        # 存储 API 树形结构（可通过 set_api_tree 注入）
        self.api_tree = {}

        # 快捷转换映射（与编辑器保持一致）
        self.shortcuts = {
            'lp': 'lprint',
            'p': 'print',
            'dir': 'lprint(dir({obj}))',
            'type': 'lprint(type({obj}))',
            'len': 'lprint(len({obj}))'
        }

        self.setup_completions()

    # ------------------------------------------------------------------
    # API 树管理
    # ------------------------------------------------------------------

    def set_api_tree(self, api_tree: dict):
        """注入自定义 API 树形结构。

        Parameters
        ----------
        api_tree : dict
            形如 ``{"module_name": ["attr1", "attr2"], ...}`` 的字典。
        """
        self.api_tree = api_tree or {}
        self.setup_completions()
        lprint(f"[代码补全] 已注入自定义 API 树，共 {len(self.api_tree)} 个顶级项")

    def set_custom_completions(self, items: list):
        """追加自定义补全项（合并到已有列表中）。"""
        self._custom_completions = list(items or [])
        self.setup_completions()
        lprint(f"[代码补全] 已追加 {len(self._custom_completions)} 个自定义补全项")

    def _get_api_apis_flat(self):
        """将 api_tree 展平为一级 API 列表（为兼容补全列表）。"""
        flat = []
        for attr, children in self.api_tree.items():
            flat.append(attr)
            if callable_check := False:
                pass
            # 如果是可调用模块，添加带括号的版本
        return sorted(set(flat))

    # ------------------------------------------------------------------
    # 对象成员提取
    # ------------------------------------------------------------------

    def _extract_object_members(self, obj, prefix, result_list, max_depth=1, current_depth=0):
        """递归提取对象的属性和方法"""
        if current_depth >= max_depth:
            return

        try:
            members = [m for m in dir(obj) if not m.startswith('_')]
        except Exception:
            return

        _QT_SKIP = {
            'staticMetaObject', 'metaObject', 'parent', 'children',
            'findChild', 'findChildren', 'deleteLater', 'destroyed',
            'objectName', 'setObjectName', 'inherits', 'isWidgetType',
            'isWindowType', 'thread', 'moveToThread',
        }

        for member in members:
            if member in _QT_SKIP:
                continue
            try:
                sub_obj = getattr(obj, member)
                member_path = f'{prefix}.{member}'
                result_list.append(member_path)
                if callable(sub_obj):
                    result_list.append(f'{member_path}()')
                elif hasattr(sub_obj, '__dict__') and current_depth < max_depth - 1:
                    self._extract_object_members(
                        sub_obj, member_path, result_list,
                        max_depth, current_depth + 1
                    )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 补全词库
    # ------------------------------------------------------------------

    def setup_completions(self):
        """设置补全词库"""
        # Python 关键字
        python_keywords = [
            'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
            'def', 'del', 'elif', 'else', 'except', 'False', 'finally', 'for',
            'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'None',
            'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'True', 'try',
            'while', 'with', 'yield'
        ]

        # Python 内置函数
        python_builtins = [
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytes', 'callable',
            'chr', 'classmethod', 'compile', 'complex', 'delattr', 'dict', 'dir',
            'divmod', 'enumerate', 'eval', 'exec', 'filter', 'float', 'format',
            'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help', 'hex',
            'id', 'input', 'int', 'isinstance', 'issubclass', 'iter', 'len',
            'lprint', 'list', 'locals', 'map', 'max', 'min', 'next', 'object', 'oct',
            'open', 'ord', 'pow', 'print', 'property', 'range', 'repr', 'reversed',
            'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str',
            'sum', 'super', 'tuple', 'type', 'vars', 'zip',
            # 快捷转换方式
            'lprint', 'p', 'dir', 'type', 'len'
        ]

        # API 树展平
        api_flat = self._get_api_apis_flat()

        # 常用模块
        common_modules = [
            'import', 'from', 'os', 'sys', 'json', 'time', 'datetime',
            're', 'math', 'random', 'collections', 'itertools'
        ]

        # 自定义补全项
        custom = getattr(self, '_custom_completions', [])

        # 合并所有补全项
        all_completions = python_keywords + python_builtins + api_flat + common_modules + custom

        # 去重
        all_completions = sorted(set(all_completions))

        # 创建模型
        model = QtCore.QStringListModel(all_completions, self)
        self.setModel(model)

        lprint(f"[代码补全] 总计 {len(all_completions)} 个补全项（API树 {len(api_flat)} 项，自定义 {len(custom)} 项）")

    def refresh_completions(self):
        """刷新补全列表"""
        lprint("[代码补全] 刷新补全列表...")
        self.setup_completions()
