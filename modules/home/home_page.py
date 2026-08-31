# -*- coding: utf-8 -*-

"""首页：产品 curated 入口（product.yml · home），不随菜单整表渲染。"""

from __future__ import annotations



from PySide6.QtCore import Qt

from PySide6.QtGui import QKeySequence, QShortcut

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget



from app.app_state import AppState

from core.base_page import BasePage

from services.access_control import can_open, requires_purchase_redirect

from services.config_service import get_hotkeys_config

from services.home_content import (

    home_advanced_note,

    home_office_pins,

    home_promises,

    home_search_hint,

    home_suite_highlights,

)

from services.menu_registry import get_menu_item_by_id

from services.migration_manifest import get_module_status

from services.module_hotkeys import get_module_shortcut

from services.runtime_paths import get_runtime_environment

from widgets import FormSection, HintLabel, PageTitle, ScrollPage, SemanticLabel

from widgets.tool_cards import ToolLaunchCard





def _hk_for(module_id: str) -> str:

    return get_module_shortcut(module_id)





def _build_vision_block() -> QWidget:

    """产品定位条：使命 / 愿景 / 目标（关于弹窗另含套件 / 定位）。"""

    from services.product_vision import vision_home_rows



    sec = FormSection("使命 · 愿景 · 目标")

    for label, body in vision_home_rows():

        row = QWidget()

        lay = QHBoxLayout(row)

        lay.setContentsMargins(0, 0, 0, 0)

        lay.setSpacing(10)

        tag = QLabel(label)

        tag.setObjectName("VisionRowTag")

        tag.setProperty("class", "section-title")

        tag.setFixedWidth(40)

        tag.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        text = HintLabel(body)

        text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        lay.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)

        lay.addWidget(text, 1)

        sec.add_widget(row)

    return sec





def _build_card_grid(home: "HomePage", cards: list[dict[str, str]]) -> QWidget | None:

    grid = QGridLayout()

    grid.setHorizontalSpacing(12)

    grid.setVerticalSpacing(12)

    col = row = 0

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

        )

        card.activated.connect(lambda m=mid: home._open_module(m))

        grid.addWidget(card, row, col)

        col += 1

        if col >= 3:

            col = 0

            row += 1

    if col == 0 and row == 0:

        return None

    host = QWidget()

    host.setLayout(grid)

    return host





class HomePage(BasePage):

    page_id = "home"

    page_title = "首页"



    def __init__(self, parent=None) -> None:

        super().__init__(parent)

        st = AppState.get()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)



        outer = QVBoxLayout(self)

        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollPage()

        outer.addWidget(scroll)



        head = QWidget()

        head_lay = QHBoxLayout(head)

        head_lay.setContentsMargins(0, 0, 0, 0)

        head_lay.setSpacing(12)

        head_lay.addWidget(PageTitle(st.brand_name()), 0)

        head_lay.addStretch(1)

        scroll.add_widget(head)



        scroll.add_widget(_build_vision_block())

        self._validity_banner = SemanticLabel("", kind="info")

        self._validity_banner.hide()

        scroll.add_widget(self._validity_banner)



        search_hint = HintLabel(home_search_hint())

        search_hint.setWordWrap(True)

        scroll.add_widget(search_hint)



        office_sec = FormSection("办公增效 · 一键开工")

        if get_runtime_environment() != "release":

            office_sec.add_widget(HintLabel("图标 + 标题 + 快捷键；绿/琥珀/灰=模块完成度。"))

        office_grid = _build_card_grid(self, home_office_pins())

        if office_grid is not None:

            office_sec.add_widget(office_grid)

        else:

            office_sec.add_widget(HintLabel("当前授权下暂无快捷入口。"))

        scroll.add_widget(office_sec)



        suite_sec = FormSection("套件精选 · 常用入口")

        suite_grid = _build_card_grid(self, home_suite_highlights())

        if suite_grid is not None:

            suite_sec.add_widget(suite_grid)

        else:

            suite_sec.add_widget(HintLabel("升级授权后可使用更多套件能力。"))

        scroll.add_widget(suite_sec)



        promises = home_promises()

        if promises:

            prom_sec = FormSection("我们承诺")

            for line in promises[:5]:

                prom_sec.add_widget(HintLabel(f"· {line}"))

            scroll.add_widget(prom_sec)



        adv = HintLabel(home_advanced_note())

        adv.setWordWrap(True)

        scroll.add_widget(adv)



        hk = get_hotkeys_config()

        jump_k = str(hk.get("home_jump_office") or "K")

        jump_i = str(hk.get("home_jump_image") or "I")

        if get_runtime_environment() != "release":

            scroll.add_widget(

                HintLabel(

                    f"页内快捷键：{jump_k} 办公 · {jump_i} 图片 · Ctrl+K 检索工作 · F11 沉浸全屏。"

                )

            )



        scroll.add_stretch(1)

        self._bind_page_shortcuts()



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


