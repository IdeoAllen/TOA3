# -*- coding: utf-8 -*-
"""Harness 左栏：会话列表、搜索、resume。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.user_messages import show_info, show_warning
from services.harness_store import list_sessions, resume_info, search_sessions, set_archived
from widgets import HintLabel, LineEdit, ListWidget, SecondaryButton


class SessionPanel(QWidget):
    session_selected = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lay.addWidget(HintLabel("会话 · 点选恢复"))
        self._search = LineEdit()
        self._search.setPlaceholderText("搜索会话…")
        self._search.textChanged.connect(self._on_search)
        lay.addWidget(self._search)

        self._list = ListWidget()
        self._list.itemClicked.connect(self._on_click)
        lay.addWidget(self._list, 1)

        row = QWidget()
        row_lay = QVBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(self.refresh)
        row_lay.addWidget(btn_refresh)
        btn_resume = SecondaryButton("复制恢复 URI")
        btn_resume.clicked.connect(self._copy_resume_uri)
        row_lay.addWidget(btn_resume)
        btn_arch = SecondaryButton("归档")
        btn_arch.clicked.connect(lambda: self._set_archived(True))
        row_lay.addWidget(btn_arch)
        btn_unarch = SecondaryButton("取消归档")
        btn_unarch.clicked.connect(lambda: self._set_archived(False))
        row_lay.addWidget(btn_unarch)
        lay.addWidget(row)

        self._sessions: list[dict] = []
        self._ids: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.refresh)

    def start_auto_refresh(self) -> None:
        self._timer.start()

    def stop_auto_refresh(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        q = self._search.text().strip()
        if q:
            self._sessions = search_sessions(q, limit=40)
        else:
            self._sessions = list_sessions(include_archived=False)
        self._ids = [str(s.get("id") or "") for s in self._sessions]
        self._list.clear()
        for s in self._sessions:
            sid = str(s.get("id") or "")
            short = sid.replace("session-", "")[:8]
            title = str(s.get("title") or "未命名")
            turns = s.get("turns") or s.get("steps") or ""
            label = f"{short} · {title}"
            if turns:
                label += f"  ({turns})"
            self._list.addItem(label)
        self.refresh_requested.emit()

    def _on_search(self, _text: str) -> None:
        self.refresh()

    def _current_id(self) -> str:
        row = self._list.currentRow()
        if 0 <= row < len(self._ids):
            return self._ids[row]
        return ""

    def _on_click(self, _item) -> None:
        sid = self._current_id()
        if sid:
            self.session_selected.emit(sid)

    def _copy_resume_uri(self) -> None:
        sid = self._current_id()
        if not sid:
            show_warning(self, "请先选择一条会话。")
            return
        info = resume_info(sid) or {}
        uri = str(info.get("resumeUri") or info.get("uri") or "")
        if not uri:
            show_warning(self, "无法生成恢复 URI，请在 Harness 侧边栏手动选择会话。")
            return
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(uri)
        show_info(
            self,
            "已复制 dsh-session 引用。\n在 Harness 新会话中 @mention 引用，或于 Web 侧边栏选该会话继续。",
        )

    def _set_archived(self, archived: bool) -> None:
        sid = self._current_id()
        if not sid:
            show_warning(self, "请先选择一条会话。")
            return
        if set_archived(sid, archived):
            self.refresh()
            show_info(self, "已归档" if archived else "已取消归档")
        else:
            show_warning(self, "归档操作失败，请确认 Harness 空闲后重试。")
