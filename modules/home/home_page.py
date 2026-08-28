# -*- coding: utf-8 -*-
"""首页：完全由菜单配置驱动（系统设置 → 菜单 可维护）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.app_state import AppState
from app.version import APP_VERSION
from core.base_page import BasePage
from services.config_service import get_hotkeys_config
from services.menu_registry import GROUP_ORDER, grouped_menu_items, is_migrated
from services.migration_manifest import get_module_status, status_label
from services.module_hotkeys import get_module_shortcut
from widgets import FormSection, HintLabel, PageTitle, ScrollPage, SectionTitle, SemanticLabel
from widgets.tool_cards import StatusDot, ToolLaunchCard

# 首页置顶：办公增效快捷卡（对照控件库 ToolLaunchCard 示例）
_WAVE_PINNED: tuple[tuple[str, str, str], ...] = (
    ("quick_notepad", "快速记事", "会议纪要草稿"),
    ("screenshot_tool", "截图工具", "区域 / 全屏"),
    ("clipboard_history", "剪贴板历史", "Alt+Shift+C 速贴"),
    ("quadrant_tasks", "四象限任务", "本地看板"),
    ("pomodoro", "番茄钟", "沉浸专注"),
)


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
        ver = HintLabel(f"TOA3 {APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignBottom)
        head_lay.addWidget(ver, 0)
        head_lay.addStretch(1)
        scroll.add_widget(head)

        scroll.add_widget(_build_vision_block())
        self._validity_banner = SemanticLabel("", kind="info")
        scroll.add_widget(self._validity_banner)
        self._refresh_validity_banner()
        scroll.add_widget(_build_wave_pins(self))
        hk = get_hotkeys_config()
        jump_k = str(hk.get("home_jump_office") or "K")
        jump_i = str(hk.get("home_jump_image") or "I")
        scroll.add_widget(
            HintLabel(
                "状态灯：绿=已完成 · 琥珀=进行中 · 灰=未建。"
                f" ←/→ 顶栏子模块 · ↑/↓ 侧栏功能（全应用） · "
                f"{jump_k} 办公 · {jump_i} 图片 · Ctrl+K 命令面板。"
            )
        )

        groups = {
            gid: (glab, items)
            for gid, glab, items in grouped_menu_items(
                licensed_only=False, migrated_only=True
            )
        }

        # 按 GROUP_ORDER 渲染：office/image 用卡片，其余用按钮
        for gid in GROUP_ORDER:
            if gid not in groups:
                continue
            glab, items = groups[gid]
            visible = [
                it
                for it in items
                if it.get("show", True)
                and str(it.get("id") or "") not in ("home",)
                and is_migrated(str(it.get("id") or ""))
            ]
            if not visible:
                continue

            scroll.add_widget(SectionTitle(glab))
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(12)
            col = row = 0
            for it in visible:
                mid = str(it.get("id") or "")
                title = str(it.get("name") or mid)
                sub = str(it.get("desc") or "")
                icon = str(it.get("icon") or mid)
                shortcut = _hk_for(mid)
                st_code = get_module_status(mid)
                tip = status_label(mid)
                card = ToolLaunchCard(
                    title,
                    subtitle=sub or tip,
                    shortcut=shortcut,
                    icon=icon,
                    status=st_code,
                )
                card.activated.connect(lambda m=mid: self._open_module(m))
                grid.addWidget(card, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
            host = QWidget()
            host.setLayout(grid)
            scroll.add_widget(host)

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
        self._refresh_validity_banner()
        self.report_status("首页 · ←/→ 子模块 · ↑/↓ 功能模块")

    def _refresh_validity_banner(self) -> None:
        try:
            from services.license_manager import global_license_manager

            lm = global_license_manager
            text = lm.get_validity_text()
            if lm.is_licensed():
                kind = "success"
            elif lm.is_standalone_mode():
                kind = "info"
            else:
                kind = "warning"
            self._validity_banner.setText(text)
            self._validity_banner.setProperty("class", f"semantic-{kind}")
            self._validity_banner.style().unpolish(self._validity_banner)
            self._validity_banner.style().polish(self._validity_banner)
        except Exception:
            pass


def _build_wave_pins(home: HomePage) -> QWidget:
    """置顶办公增效 ToolLaunchCard（控件库同款）。"""
    from services.access_control import can_open
    from services.menu_registry import get_menu_item_by_id

    sec = FormSection("办公增效 · 一键开工")
    sec.add_widget(HintLabel("图标 + 标题 + 快捷键；绿/琥珀/灰=模块完成度。"))
    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(12)
    col = row = 0
    for mid, title, sub in _WAVE_PINNED:
        ok, _ = can_open(mid)
        if not ok:
            continue
        item = get_menu_item_by_id(mid) or {}
        icon = str(item.get("icon") or mid)
        card = ToolLaunchCard(
            title,
            subtitle=sub,
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
        sec.add_widget(HintLabel("当前授权下暂无快捷入口。"))
    else:
        host = QWidget()
        host.setLayout(grid)
        sec.add_widget(host)
    return sec
