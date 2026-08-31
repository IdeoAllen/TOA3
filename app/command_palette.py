# -*- coding: utf-8 -*-
"""全局命令面板 Ctrl+K。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout

from core.ui_spec import center_on_screen
from services.harness_actions import palette_actions, run_palette_action
from services.menu_registry import visible_menu_items, is_migrated
from services.access_control import can_open, nav_clickable
from widgets import HintLabel, LineEdit, ListWidget, PrimaryButton


class CommandPalette(QDialog):
    """命令面板：固定尺寸、屏幕居中。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("检索工作")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)
        self.setFixedSize(480, 420)
        self._selected_id: str | None = None
        self._selected_action: str | None = None

        lay = QVBoxLayout(self)
        lay.addWidget(HintLabel("输入关键字过滤模块或 Harness 动作，回车或双击打开。"))
        self._query = LineEdit()
        self._query.setPlaceholderText("搜索模块、动作、智能体…")
        self._query.textChanged.connect(self._filter)
        lay.addWidget(self._query)
        self._list = ListWidget()
        self._list.itemDoubleClicked.connect(self._accept_current)
        lay.addWidget(self._list, 1)
        btn = PrimaryButton("打开")
        btn.clicked.connect(self._accept_current)
        lay.addWidget(btn)

        self._items: list[tuple[str, str]] = []
        for it in visible_menu_items():
            mid = str(it.get("id") or "")
            if not mid or not is_migrated(mid):
                continue
            name = str(it.get("name") or mid)
            self._items.append((mid, name))
        for aid, label, _kw in palette_actions():
            self._items.append((f"action:{aid}", label))
        self._filter("")
        self._query.setFocus()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        center_on_screen(self)

    def _filter(self, text: str) -> None:
        q = (text or "").strip().lower()
        self._list.clear()
        for mid, name in self._items:
            blob = f"{mid} {name}".lower()
            if q and q not in blob:
                if mid.startswith("action:"):
                    from services.harness_actions import palette_actions

                    extra = ""
                    for aid, label, kw in palette_actions():
                        if f"action:{aid}" == mid:
                            extra = kw
                            break
                    if q not in extra.lower():
                        continue
                else:
                    continue
            prefix = "动作 · " if mid.startswith("action:") else ""
            self._list.addItem(f"{prefix}{name}  ({mid})")

    def _accept_current(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        q = self._query.text().strip().lower()
        visible = []
        for mid, name in self._items:
            blob = f"{mid} {name}".lower()
            if not q or q in blob:
                visible.append((mid, name))
            elif mid.startswith("action:"):
                from services.harness_actions import palette_actions

                for aid, label, kw in palette_actions():
                    if f"action:{aid}" == mid and q in kw.lower():
                        visible.append((mid, name))
                        break
        if 0 <= row < len(visible):
            mid = visible[row][0]
            if mid.startswith("action:"):
                self._selected_action = mid.split(":", 1)[1]
                self.accept()
                return
            ok, reason = can_open(mid)
            nav_ok, _ = nav_clickable(mid)
            if not ok and not nav_ok:
                from core.user_messages import show_warning

                show_warning(self, reason or "无权限")
                return
            self._selected_id = mid
            self.accept()

    def selected_module_id(self) -> str | None:
        return self._selected_id

    def selected_action_id(self) -> str | None:
        return self._selected_action

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept_current()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


def open_command_palette(shell) -> None:
    dlg = CommandPalette(shell)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        if dlg.selected_action_id():
            run_palette_action(shell, dlg.selected_action_id())
            return
        if dlg.selected_module_id():
            shell.navigate(dlg.selected_module_id())
