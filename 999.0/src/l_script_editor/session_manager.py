# -*- coding: utf-8 -*-
"""
会话管理器 - l_script_editor

保存/恢复脚本编辑器的 Tab 状态（代码内容、光标位置等）。
"""

from __future__ import print_function, unicode_literals

import datetime
import glob
import json
import os
from typing import Callable, Optional

import Lugwit_Module as LM
lprint = LM.lprint


class SessionManager:
    """脚本编辑器会话管理器

    功能：
    - 保存所有 Tab 的代码内容 + 光标位置到 JSON 文件
    - 恢复上次保存的会话状态
    - 清空会话文件
    """

    def __init__(self, session_file: str, history_dir: str = ""):
        self.session_file = session_file
        self.history_dir = history_dir or os.path.expanduser("~/.Lugwit/config/.history")

        # 确保配置目录存在
        session_dir = os.path.dirname(self.session_file)
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    def save_session(self, tab_widget) -> bool:
        """保存当前会话状态

        Parameters
        ----------
        tab_widget : QTabWidget
            代码编辑器所在的 QTabWidget。

        Returns
        -------
        bool
            保存是否成功。
        """
        try:
            if not tab_widget:
                return False

            session_data = {
                "tabs": [],
                "current_tab_index": tab_widget.currentIndex(),
                "timestamp": str(datetime.datetime.now())
            }

            for i in range(tab_widget.count()):
                tab_name = tab_widget.tabText(i)
                editor = tab_widget.widget(i)

                if editor and hasattr(editor, 'toPlainText'):
                    tab_content = editor.toPlainText()
                    cursor_pos = editor.textCursor().position() if hasattr(editor, 'textCursor') else 0

                    tab_info = {
                        "name": tab_name,
                        "content": tab_content,
                        "cursor_position": cursor_pos
                    }
                    session_data["tabs"].append(tab_info)

            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

            lprint(f"[会话管理] 已保存 {len(session_data['tabs'])} 个Tab的会话状态")
            return True

        except Exception as e:
            lprint(f"[会话管理] 保存会话失败: {str(e)}")
            return False

    # ------------------------------------------------------------------
    # 恢复
    # ------------------------------------------------------------------

    def restore_session(self, tab_widget, create_tab_fn: Callable) -> bool:
        """恢复上次的会话状态

        优先从历史版本目录读取每个 tab 的最新 .py 文件，
        如果没有历史记录则降级使用 session JSON 中的 content 字段。

        Parameters
        ----------
        tab_widget : QTabWidget
            代码编辑器所在的 QTabWidget。
        create_tab_fn : Callable
            用于创建新 Tab 的函数，签名为
            ``create_tab_fn(tab_name: str, with_example: bool) -> editor``。

        Returns
        -------
        bool
            恢复是否成功。
        """
        try:
            if not os.path.exists(self.session_file):
                lprint("[会话管理] 没有找到会话文件，创建新会话")
                return False

            with open(self.session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            if not session_data.get("tabs"):
                lprint("[会话管理] 会话文件为空，创建新会话")
                return False

            # 清空现有 tabs
            while tab_widget.count() > 0:
                tab_widget.removeTab(0)

            # 恢复每个 tab
            restored_tabs = []
            for tab_info in session_data["tabs"]:
                tab_name = tab_info.get("name", f"code_{len(restored_tabs) + 1}")
                tab_content = tab_info.get("content", "")
                cursor_pos = tab_info.get("cursor_position", 0)

                # 优先从历史版本目录读取最新文件
                latest_code = self._read_latest_history(tab_name)
                if latest_code is not None:
                    tab_content = latest_code

                editor = create_tab_fn(tab_name, False)
                if editor:
                    editor.setPlainText(tab_content)

                    if cursor_pos > 0 and hasattr(editor, 'textCursor'):
                        cursor = editor.textCursor()
                        cursor.setPosition(cursor_pos)
                        editor.setTextCursor(cursor)

                    restored_tabs.append(tab_name)

            # 恢复当前选中的 tab
            current_index = session_data.get("current_tab_index", 0)
            if 0 <= current_index < tab_widget.count():
                tab_widget.setCurrentIndex(current_index)

            lprint(f"[会话管理] 已恢复 {len(restored_tabs)} 个Tab的会话状态")
            return True

        except Exception as e:
            lprint(f"[会话管理] 恢复会话失败: {str(e)}")
            return False

    def _read_latest_history(self, tab_name: str) -> Optional[str]:
        """从历史版本目录读取指定 tab 的最新代码文件内容。

        Parameters
        ----------
        tab_name : str
            Tab 名称。

        Returns
        -------
        Optional[str]
            代码内容，无历史记录时返回 None。
        """
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in tab_name) or "tab"
        tab_dir = os.path.join(self.history_dir, safe_name)
        if not os.path.isdir(tab_dir):
            return None
        pattern = os.path.join(tab_dir, f"{safe_name}_*.py")
        files = sorted(glob.glob(pattern), reverse=True)
        if not files:
            return None
        try:
            with open(files[0], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            lprint(f"[会话管理] 读取历史版本失败 {files[0]}: {e}")
            return None

    # ------------------------------------------------------------------
    # 清空 / 信息
    # ------------------------------------------------------------------

    def clear_session(self) -> bool:
        """清空会话文件"""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                lprint("[会话管理] 已清空会话文件")
                return True
            return False
        except Exception as e:
            lprint(f"[会话管理] 清空会话文件失败: {str(e)}")
            return False

    def get_session_info(self) -> dict:
        """获取会话信息"""
        info = {
            "session_file": self.session_file,
            "tab_count": 0,
            "save_time": "未知",
        }
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                info["tab_count"] = len(data.get("tabs", []))
                info["save_time"] = data.get("timestamp", "未知")
        except Exception as e:
            lprint(f"[会话管理] 获取会话信息失败: {e}")
        return info
