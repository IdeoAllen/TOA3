# -*- coding: utf-8 -*-
"""系统设置 · 运营台枢纽（入口 + 本机联动项说明）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.commerce_urls import admin_console_url, open_admin_console
from services.settings_access import (
    TAB_LICENSE,
    TAB_MENU,
    TAB_SUBSCRIPTION,
    is_settings_admin,
    subscription_tab_visible,
)
from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton, SemanticLabel


class OpsConsoleSection(QWidget):
    """把与运营台相关的终端入口收在一处，避免散落。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        hub = FormSection("TOA 运营台")
        hub.add_widget(
            SemanticLabel(
                "产品方案、订单履约、发码台账、版本发布在运营台；"
                "本机侧栏菜单与本机用户仍在终端维护。",
                kind="info",
            )
        )
        hub.add_widget(HintLabel(admin_console_url()))
        row = QHBoxLayout()
        btn = PrimaryButton("打开运营台")
        btn.clicked.connect(self._on_open)
        row.addWidget(btn)
        row.addStretch(1)
        hub.add_layout(row)
        outer.addWidget(hub)

        link = FormSection("本机联动")
        link.add_widget(
            HintLabel(
                "下列为本机设置中与运营台衔接的能力；"
                "改方案定价 / 发版请直接进运营台。"
            )
        )
        row2 = QHBoxLayout()
        if is_settings_admin():
            btn_lic = SecondaryButton("授权管理")
            btn_lic.clicked.connect(lambda: self._open_tab(TAB_LICENSE))
            row2.addWidget(btn_lic)
            btn_menu = SecondaryButton("菜单 · 同步目录")
            btn_menu.clicked.connect(lambda: self._open_tab(TAB_MENU))
            row2.addWidget(btn_menu)
        if subscription_tab_visible():
            btn_sub = SecondaryButton("开通与续费")
            btn_sub.clicked.connect(lambda: self._open_tab(TAB_SUBSCRIPTION))
            row2.addWidget(btn_sub)
        row2.addStretch(1)
        link.add_layout(row2)
        if not is_settings_admin() and not subscription_tab_visible():
            link.add_widget(
                HintLabel("当前账号已授权：商业变更请打开运营台；本机账号见顶栏人像。")
            )
        outer.addWidget(link)
        outer.addStretch(1)

    def _on_open(self) -> None:
        if open_admin_console():
            show_info(self._page, f"已在浏览器打开运营台：\n{admin_console_url()}")
            self._page.report_status("已打开运营台")
        else:
            show_warning(
                self._page,
                f"无法打开浏览器，请手动访问：\n{admin_console_url()}",
            )

    def _open_tab(self, key: str) -> None:
        page = self._page
        if hasattr(page, "open_tab"):
            page.open_tab(key)
            return
        if key == TAB_LICENSE and hasattr(page, "open_license_tab"):
            page.open_license_tab()
        elif key == TAB_SUBSCRIPTION and hasattr(page, "open_subscription_tab"):
            page.open_subscription_tab()
        elif key == TAB_MENU and hasattr(page, "open_tab"):
            page.open_tab(TAB_MENU)
