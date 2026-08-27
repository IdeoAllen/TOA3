# -*- coding: utf-8 -*-
"""勾选、单选、开关与滑块。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QRadioButton, QSizePolicy, QSlider


class CheckBox(QCheckBox):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        # 给指示器留足高度，避免列表行里裁切成「缺边」
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)


def _palette_colors() -> dict[str, str]:
    try:
        from app.app_state import AppState

        return AppState.get().palette or {}
    except Exception:
        return {}


class Switch(QCheckBox):
    """拨动开关：滑块占轨道左/右半，样式自绘（不依赖 indicator QSS）。"""

    TRACK_W = 44
    TRACK_H = 22
    GAP = 10

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Switch")
        self.setMinimumHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        text_w = self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0
        w = self.TRACK_W + (self.GAP + text_w if text_w else 0) + 4
        return QSize(w, max(28, self.TRACK_H + 8))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = _palette_colors()
        primary = QColor(str(p.get("primary") or "#2563EB"))
        border = QColor(str(p.get("border") or "#CBD5E1"))
        track_off = QColor(str(p.get("surface_hover") or p.get("row_hover") or "#E2E8F0"))
        thumb = QColor(str(p.get("surface") or "#FFFFFF"))
        text = QColor(str(p.get("text_primary") or "#1E293B"))
        text_dis = QColor(str(p.get("text_disabled") or p.get("text_secondary") or "#94A3B8"))

        if not self.isEnabled():
            primary = border
            track_off = QColor(str(p.get("primary_disabled_bg") or border))
            thumb = track_off.lighter(108)
            text = text_dis

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        y = (self.height() - self.TRACK_H) // 2
        track = QRectF(0, y, self.TRACK_W, self.TRACK_H)
        radius = self.TRACK_H / 2.0
        margin = 2.0
        thumb_w = (self.TRACK_W - margin * 2) / 2.0
        thumb_h = self.TRACK_H - margin * 2
        thumb_x = margin if not self.isChecked() else margin + thumb_w
        thumb_rect = QRectF(thumb_x, y + margin, thumb_w, thumb_h)

        track_fill = primary if self.isChecked() else track_off
        painter.setPen(QPen(border if not self.isChecked() else primary.darker(110), 1))
        painter.setBrush(track_fill)
        painter.drawRoundedRect(track, radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF") if self.isEnabled() else thumb)
        painter.drawRoundedRect(thumb_rect, thumb_h / 2.2, thumb_h / 2.2)

        label = self.text()
        if label:
            painter.setPen(text if self.isEnabled() else text_dis)
            text_x = int(self.TRACK_W + self.GAP)
            painter.drawText(
                text_x,
                0,
                self.width() - text_x,
                self.height(),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                label,
            )


class RadioButton(QRadioButton):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setMinimumHeight(28)


class Slider(QSlider):
    """水平滑块（主题 QSS）；默认 0–100。"""

    def __init__(
        self,
        parent=None,
        *,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        minimum: int = 0,
        maximum: int = 100,
        value: int = 0,
    ) -> None:
        super().__init__(orientation, parent)
        self.setMinimum(minimum)
        self.setMaximum(maximum)
        self.setValue(value)
        self.setMinimumHeight(28)
