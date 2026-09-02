# -*- coding: utf-8 -*-
"""首页：品牌 Hero + curated 精选入口（product.yml · home）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from app.app_state import AppState
from core.base_page import BasePage
from services.access_control import can_open, requires_purchase_redirect
from services.config_service import get_hotkeys_config
from services.home_content import (
    home_advanced_note,
    home_office_pins,
    home_promises,
    home_suite_highlights,
)
from services.menu_registry import get_menu_item_by_id
from services.migration_manifest import get_module_status
from services.module_hotkeys import get_module_shortcut
from services.product_vision import load_vision
from services.runtime_paths import get_runtime_environment
from widgets import HintLabel, ScrollPage, SemanticLabel
from widgets.home_hero import HomeHeroBand, HomePromiseStrip, HomeSectionLabel
from widgets.tool_cards import ToolLaunchCard


def _hk_for(module_id: str) -> str:
    return get_module_shortcut(module_id)


def _build_card_grid(
    home: "HomePage",
    cards: list[dict[str, str]],
    *,
    featured: bool = False,
    columns: int = 3,
) -> QWidget | None:
    grid = QGridLayout()
    grid.setHorizontalSpacing(14 if featured else 12)
    grid.setVerticalSpacing(14 if featured else 12)
    col = row = 0
    cols = max(2, min(columns, 5))
    for spec in cards:
        mid = str(spec.get("id") or "")
        if not mid:
            continue
        ok, _reason = can_open(mid)
        if not ok and not requires_purchase_redirect():
            continue
        item = get_menu_item_by_id(mid) or {}
        icon = str(item.get("icon") or mid)
        card = ToolLaunchCard(
            str(spec.get("title") or item.get("name") or mid),
            subtitle=str(spec.get("subtitle") or item.get("desc") or ""),
            shortcut=_hk_for(mid),
            icon=icon,
            status=get_module_status(mid),
            featured=featured,
        )
        card.activated.connect(lambda m=mid: home._open_module(m))
        grid.addWidget(card, row, col)
        col += 1
        if col >= cols:
            col = 0
            row += 1
    if col == 0 and row == 0:
        return None
    host = QWidget()
    host.setObjectName("HomeCardGrid")
    host.setLayout(grid)
    return host


class HomePage(BasePage):
    page_id = "home"
    page_title = "首页"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        st = AppState.get()
        vision = load_vision()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        hero = HomeHeroBand(
            brand=st.brand_name() or "运营宝 TOA",
            tagline=str(vision.get("tagline") or ""),
            statement=str(vision.get("statement") or ""),
        )
        hero.start_work.connect(self._on_start_work)
        hero.search_work.connect(self._open_command_palette)
        scroll.add_widget(hero)

        self._validity_banner = SemanticLabel("", kind="info")
        self._validity_banner.hide()
        scroll.add_widget(self._validity_banner)

        office_head = HomeSectionLabel("今日高频", eyebrow="START HERE")
        scroll.add_widget(office_head)
        if get_runtime_environment() != "release":
            scroll.add_widget(HintLabel("精选入口 · 绿/琥珀/灰为模块完成度（仅开发可见）。"))

        office_grid = _build_card_grid(self, home_office_pins(), featured=True, columns=5)
        if office_grid is not None:
            scroll.add_widget(office_grid)
        else:
            scroll.add_widget(HintLabel("当前授权下暂无快捷入口。"))

        suite_head = HomeSectionLabel("套件精选", eyebrow="SUITE")
        scroll.add_widget(suite_head)
        suite_grid = _build_card_grid(self, home_suite_highlights(), featured=False, columns=4)
        if suite_grid is not None:
            scroll.add_widget(suite_grid)
        else:
            scroll.add_widget(HintLabel("升级授权后可使用更多套件能力。"))

        promises = home_promises()
        if promises:
            strip = HomePromiseStrip([str(x) for x in promises[:4]])
            scroll.add_widget(strip)

        adv = HintLabel(home_advanced_note())
        adv.setWordWrap(True)
        adv.setObjectName("HomeAdvancedNote")
        scroll.add_widget(adv)

        scroll.add_stretch(1)
        self._bind_page_shortcuts()
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self

    def _on_start_work(self) -> None:
        pins = home_office_pins()
        for spec in pins:
            mid = str(spec.get("id") or "")
            if not mid:
                continue
            ok, _ = can_open(mid)
            if ok or requires_purchase_redirect():
                self._open_module(mid)
                return
        self._open_first_in("office")

    def _open_command_palette(self) -> None:
        shell = self.window()
        opener = getattr(shell, "_open_command_palette", None)
        if callable(opener):
            opener()

    def _open_module(self, module_id: str) -> None:
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            shell.navigate(module_id)

    def _bind_page_shortcuts(self) -> None:
        hk = get_hotkeys_config()
        jump_k = str(hk.get("home_jump_office") or "K").strip() or "K"
        jump_i = str(hk.get("home_jump_image") or "I").strip() or "I"
        if jump_k.lower() != "none":
            QShortcut(QKeySequence(jump_k), self, activated=lambda: self._open_first_in("office"))
        if jump_i.lower() != "none":
            QShortcut(QKeySequence(jump_i), self, activated=lambda: self._open_first_in("image"))

    def _open_first_in(self, group_id: str) -> None:
        from services.menu_registry import grouped_menu_items, is_migrated

        for gid, _glab, items in grouped_menu_items(licensed_only=False, migrated_only=True):
            if gid != group_id:
                continue
            for it in items:
                mid = str(it.get("id") or "")
                if mid and mid != "home" and it.get("show", True) and is_migrated(mid):
                    self._open_module(mid)
                    return

    def on_enter(self) -> None:
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.report_status("首页")
