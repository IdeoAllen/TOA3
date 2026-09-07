# -*- coding: utf-8 -*-
"""引擎管家：收录目录 + Comfy 同构 Host 详情（新板块，开闭不改旧引擎页）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from services.engine_host.catalog import CatalogEntry, list_catalog_entries, status_badge
from widgets import HintLabel, ListWidget, SecondaryButton


class EngineHostHubPage(BasePage):
    page_id = "engine_host_hub"
    page_title = "引擎管家"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hosts: dict[str, QWidget] = {}
        self._host_index: dict[str, int] = {}
        self._current_id = ""

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(max(4, m[0] // 2), 4, max(4, m[2] // 2), 4)
        outer.setSpacing(6)

        portal = QHBoxLayout()
        portal.setSpacing(8)
        self._portal_hint = HintLabel("办公传送门")
        self._portal_hint.setToolTip("运行中可将剪贴板投喂到浏览器工作台；未运行时按钮禁用")
        portal.addWidget(self._portal_hint)
        self._btn_feed_clip = SecondaryButton("送剪贴板到浏览器")
        self._btn_feed_clip.setToolTip("打开工作台并把剪贴板文本保持可粘贴")
        self._btn_feed_clip.clicked.connect(self._feed_clipboard)
        portal.addWidget(self._btn_feed_clip)
        self._btn_collab = SecondaryButton("打开协作任务表")
        self._btn_collab.clicked.connect(self._open_collab)
        portal.addWidget(self._btn_collab)
        portal.addStretch(1)
        outer.addLayout(portal)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(6)
        left_lay.addWidget(HintLabel("开源收录"))
        self._list = ListWidget()
        self._list.setObjectName("EngineHostCatalog")
        self._list.currentItemChanged.connect(self._on_select)
        left_lay.addWidget(self._list, 1)
        split.addWidget(left)

        self._stack = QStackedWidget()
        self._placeholder = QLabel("从左侧选择引擎")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._placeholder)
        split.addWidget(self._stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 900])
        outer.addWidget(split, 1)

        self._entries: list[CatalogEntry] = []
        self._reload_catalog(prefer_id="")
        self._set_portal_enabled(False)

    def _reload_catalog(self, *, prefer_id: str = "") -> None:
        keep = (prefer_id or self._current_id or "").strip()
        self._list.blockSignals(True)
        try:
            self._list.clear()
            self._entries = list_catalog_entries()
            select_row = 0
            for i, entry in enumerate(self._entries):
                badge = status_badge(entry)
                item = QListWidgetItem(f"{entry.title}  ·  {badge}")
                item.setToolTip(entry.description or entry.title)
                item.setData(Qt.ItemDataRole.UserRole, entry.engine_id)
                self._list.addItem(item)
                if keep and entry.engine_id == keep:
                    select_row = i
            if self._list.count():
                self._list.setCurrentRow(select_row)
        finally:
            self._list.blockSignals(False)
        # 手动切换（block 期间未触发）
        cur = self._list.currentItem()
        if cur is not None:
            eid = str(cur.data(Qt.ItemDataRole.UserRole) or "")
            if eid and eid != self._current_id:
                self._switch_host(eid)
            elif eid:
                self._sync_portal()

    def _on_select(self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None = None) -> None:
        if cur is None:
            return
        eid = str(cur.data(Qt.ItemDataRole.UserRole) or "")
        if not eid or eid == self._current_id:
            self._sync_portal()
            return
        self._switch_host(eid)

    def _find_entry(self, eid: str) -> CatalogEntry | None:
        for e in self._entries:
            if e.engine_id == eid:
                return e
        return None

    def _switch_host(self, eid: str) -> None:
        prev = self._hosts.get(self._current_id)
        if prev is not None and self._current_id != eid:
            if hasattr(prev, "soft_leave"):
                prev.soft_leave()
            elif hasattr(prev, "on_leave"):
                prev.on_leave()

        host = self._hosts.get(eid)
        if host is None:
            entry = self._find_entry(eid)
            if entry is None:
                return
            if entry.kind == "harness":
                from modules.engine_host_hub.hub_harness_host import HubHarnessHost

                host = HubHarnessHost(self)
            else:
                from modules.engine_host_hub.hub_local_web_host import HubLocalWebHost

                host = HubLocalWebHost(eid, self)
            self._hosts[eid] = host
            idx = self._stack.addWidget(host)
            self._host_index[eid] = idx

        idx = self._host_index.get(eid)
        if idx is None:
            return
        self._stack.setCurrentIndex(idx)
        self._current_id = eid
        if hasattr(host, "on_enter"):
            host.on_enter()
        self._sync_portal()

    def _sync_portal(self) -> None:
        entry = self._find_entry(self._current_id)
        running = bool(entry and status_badge(entry) == "运行中")
        self._set_portal_enabled(running)

    def _set_portal_enabled(self, on: bool) -> None:
        self._btn_feed_clip.setEnabled(on)
        tip = "打开工作台，请在浏览器粘贴剪贴板内容" if on else "引擎未运行：启动后再投喂"
        self._btn_feed_clip.setToolTip(tip)

    def _feed_clipboard(self) -> None:
        host = self._hosts.get(self._current_id)
        if host is None:
            return
        if hasattr(host, "_on_open_workbench"):
            host._on_open_workbench()
        elif hasattr(host, "_btn_open_bench"):
            host._btn_open_bench.click()
        self.report_status("已打开工作台 · 请在浏览器粘贴剪贴板", level=StatusLevel.INFO)

    def _open_collab(self) -> None:
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            from services.collab_board import resolve_board_path, sync_board_to_user_copies

            sync_board_to_user_copies()
            path = resolve_board_path()
            if path is not None:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                self.report_status("已打开协作任务表", level=StatusLevel.INFO)
                return
        except Exception:
            pass
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            shell.navigate("quick_notepad")
        self.report_status("请在记事本查看协作任务", level=StatusLevel.INFO)

    def on_enter(self) -> None:
        self.report_status("引擎管家", level=StatusLevel.INFO)
        self._reload_catalog(prefer_id=self._current_id)
        if self._current_id and self._current_id in self._hosts:
            h = self._hosts[self._current_id]
            if hasattr(h, "on_enter"):
                h.on_enter()
        self._sync_portal()

    def on_leave(self) -> None:
        h = self._hosts.get(self._current_id)
        if h is not None:
            if hasattr(h, "soft_leave"):
                h.soft_leave()
            elif hasattr(h, "on_leave"):
                h.on_leave()

    def uses_webengine_embed(self) -> bool:
        h = self._hosts.get(self._current_id)
        if h is not None and hasattr(h, "uses_webengine_embed"):
            return bool(h.uses_webengine_embed())
        return False
