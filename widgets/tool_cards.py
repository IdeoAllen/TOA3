# -*- coding: utf-8 -*-
"""工具启动卡片（首页 / 增效入口）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from services.icon_registry import icon_pixmap

# done=亮绿 / mvp=琥珀 / stub·missing=灰
_STATUS_DOT = {
    "done": ("●", "#22C55E", "已完成（核心对齐且无缺口）"),
    "mvp": ("●", "#F59E0B", "进行中（未做强）"),
    "stub": ("○", "#9CA3AF", "待开发（空页面）"),
    "missing": ("○", "#9CA3AF", "尚未建模块"),
}


def _dev_migration_dots_visible() -> bool:
    try:
        from services.runtime_paths import get_runtime_environment

        return get_runtime_environment() != "release"
    except Exception:
        return True


class StatusDot(QLabel):
    """迁移状态指示灯：完成亮绿，进行中琥珀，空页/缺失灰圈。"""

    def __init__(self, status: str = "mvp", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MigrationStatusDot")
        self.set_status(status)

    def set_status(self, status: str) -> None:
        st = str(status or "mvp").strip().lower()
        glyph, color, tip = _STATUS_DOT.get(st, _STATUS_DOT["mvp"])
        self.setText(glyph)
        self.setToolTip(tip)
        self.setStyleSheet(
            f"QLabel#MigrationStatusDot {{ color: {color}; font-size: 14px; "
            f"font-weight: 700; background: transparent; border: none; padding: 0; }}"
        )
        self.setFixedWidth(16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class ToolLaunchCard(QFrame):
    """图标 + 标题 + 快捷键提示；点击发射 activated。featured=竖向精选大卡。"""

    activated = Signal()

    def __init__(
        self,
        title: str,
        *,
        subtitle: str = "",
        shortcut: str = "",
        icon: str = "file-text",
        status: str = "",
        featured: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ToolLaunchCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("class", "tool-card")
        self.setProperty("featured", "true" if featured else "false")
        if featured:
            self.setMinimumHeight(132)
            self.setMinimumWidth(148)
        else:
            self.setMinimumHeight(88)
            self.setMinimumWidth(160)

        try:
            from app.app_state import AppState

            fg = str((AppState.get().palette or {}).get("primary") or "#2563EB")
        except Exception:
            fg = "#2563EB"

        if featured:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(16, 16, 16, 14)
            lay.setSpacing(10)
            icon_lbl = QLabel()
            icon_lbl.setObjectName("ToolCardIcon")
            icon_lbl.setFixedSize(48, 48)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setPixmap(icon_pixmap(icon, color=fg, size=36, parent=self))
            lay.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignLeft)

            title_row = QHBoxLayout()
            title_row.setSpacing(6)
            title_lbl = QLabel(title)
            title_lbl.setObjectName("ToolCardTitle")
            title_lbl.setProperty("class", "section-title")
            title_lbl.setWordWrap(True)
            title_row.addWidget(title_lbl, 1)
            if status and _dev_migration_dots_visible():
                title_row.addWidget(StatusDot(status), 0)
                tip = _STATUS_DOT.get(str(status).lower(), _STATUS_DOT["mvp"])[2]
                self.setToolTip(tip)
            lay.addLayout(title_row)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setObjectName("ToolCardSub")
                sub.setProperty("class", "hint")
                sub.setWordWrap(True)
                lay.addWidget(sub)
            if shortcut:
                hk = QLabel(shortcut)
                hk.setObjectName("ToolCardShortcut")
                hk.setProperty("class", "hint")
                lay.addWidget(hk)
            lay.addStretch(1)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(12)

            icon_lbl = QLabel()
            icon_lbl.setObjectName("ToolCardIcon")
            icon_lbl.setFixedSize(40, 40)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setPixmap(icon_pixmap(icon, color=fg, size=28, parent=self))
            lay.addWidget(icon_lbl)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            title_row = QHBoxLayout()
            title_row.setSpacing(6)
            title_lbl = QLabel(title)
            title_lbl.setObjectName("ToolCardTitle")
            title_lbl.setProperty("class", "section-title")
            title_row.addWidget(title_lbl)
            if status and _dev_migration_dots_visible():
                title_row.addWidget(StatusDot(status))
                tip = _STATUS_DOT.get(str(status).lower(), _STATUS_DOT["mvp"])[2]
                self.setToolTip(tip)
            title_row.addStretch(1)
            text_col.addLayout(title_row)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setObjectName("ToolCardSub")
                sub.setProperty("class", "hint")
                sub.setWordWrap(True)
                text_col.addWidget(sub)
            if shortcut:
                hk = QLabel(shortcut)
                hk.setObjectName("ToolCardShortcut")
                hk.setProperty("class", "hint")
                text_col.addWidget(hk)
            text_col.addStretch(1)
            lay.addLayout(text_col, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)
