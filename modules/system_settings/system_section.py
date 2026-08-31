# -*- coding: utf-8 -*-
"""系统设置 · 系统（版本、更新、关于、切换身份、运行）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from services.settings_access import can_switch_local_identity
from widgets import FormSection, HintLabel, SecondaryButton


class SystemSection(QWidget):
    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        from modules.system_settings.app_update_section import AppUpdateSection

        outer.addWidget(AppUpdateSection(parent), 1)

        if can_switch_local_identity():
            admin = FormSection("身份")
            admin.add_widget(
                HintLabel("在本机已发卡的账号之间切换；切换后菜单与权限立即生效。")
            )
            row = QHBoxLayout()
            btn = SecondaryButton("切换身份…")
            btn.clicked.connect(self._on_switch_user)
            row.addWidget(btn)
            row.addStretch(1)
            admin.add_layout(row)
            outer.addWidget(admin)

        outer.addWidget(
            HintLabel("账号查看与退出登录见顶栏人像；商业与发版见「运营台与商业 → 运营台」。")
        )

    def _on_switch_user(self) -> None:
        from app.switch_user_dialog import SwitchUserDialog

        shell = self.window()
        parent = shell if shell is not None and hasattr(shell, "navigate") else self._page
        SwitchUserDialog(parent).exec()
