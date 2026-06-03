# -*- coding: utf-8 -*-

name = "l_script_editor"
version = "999.0"
description = "独立可复用的 Python 脚本编辑器组件库 - 提供代码编辑、自动补全、语法高亮、会话管理等功能"
authors = ["Lugwit Team"]

requires = [
    "python-3.12+<3.13",
    "pyside6",
    "Lugwit_Module",
]

build_command = False
cachable = True
relocatable = True


def commands():
    env.PYTHONPATH.prepend("{root}/src")
    env.L_SCRIPT_EDITOR_ROOT = "{root}"
