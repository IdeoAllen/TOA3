# -*- coding: utf-8 -*-
"""顶栏用户入口：统一账号/购买弹窗。"""
from __future__ import annotations

from app.commerce_dialog import open_account_dialog


class UserProfileDialog:
    """兼容旧调用：直接打开 CommerceDialog。"""

    def __init__(self, parent=None) -> None:
        self._parent = parent

    def exec(self) -> int:
        open_account_dialog(self._parent)
        return 0
