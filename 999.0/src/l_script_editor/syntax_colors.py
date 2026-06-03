# -*- coding: utf-8 -*-
"""
语法高亮颜色定义 - l_script_editor

独立的颜色枚举，不依赖任何外部项目配置。
"""

from enum import Enum


class SyntaxHighlightColors(Enum):
    """Python语法高亮颜色定义 - 统一管理代码编辑器的配色方案"""

    # 关键字（import, def, class, if, for等）
    KEYWORD = (86, 156, 214)  # 蓝色

    # 字符串（普通字符串和f-string）
    STRING = (206, 145, 120)  # 橙棕色

    # 注释
    COMMENT = (106, 153, 85)  # 绿色

    # 数字
    NUMBER = (181, 206, 168)  # 浅绿色

    # 根对象/顶级模块（链式调用的第一个对象，如 aa.bb.cc 中的 aa）
    ROOT_OBJECT = (78, 201, 176)  # 青绿色（更醒目）

    # 对象名/模块名（点号前，如 dw、main_window）
    OBJECT_NAME = (156, 220, 254)  # 浅蓝色

    # 属性名（点号后无括号，如 .current、.name）
    ATTRIBUTE = (156, 220, 254)  # 浅蓝色（与对象名相同）

    # 函数/方法调用（点号后有括号，如 .method()、独立函数）
    FUNCTION_CALL = (220, 220, 170)  # 浅黄色

    # 类名（定义时）
    CLASS_DEFINITION = (78, 201, 176)  # 青绿色

    # 类名（使用时）
    CLASS_NAME = (78, 201, 176)  # 青绿色

    # 函数名（定义时）
    FUNCTION_DEFINITION = (220, 220, 170)  # 浅黄色

    # 装饰器（@decorator）
    DECORATOR = (220, 220, 170)  # 浅黄色

    # f-string大括号
    FSTRING_BRACE = (255, 215, 0)  # 金色

    @property
    def rgb(self) -> tuple:
        """获取RGB颜色元组"""
        return self.value

    @property
    def hex(self) -> str:
        """获取十六进制颜色字符串"""
        r, g, b = self.value
        return f"#{r:02X}{g:02X}{b:02X}"

    def to_qcolor(self):
        """转换为QColor对象"""
        try:
            from PySide6.QtGui import QColor
            r, g, b = self.value
            return QColor(r, g, b)
        except ImportError:
            try:
                from PySide2.QtGui import QColor
                r, g, b = self.value
                return QColor(r, g, b)
            except ImportError:
                raise RuntimeError("需要安装 PySide6 或 PySide2")
