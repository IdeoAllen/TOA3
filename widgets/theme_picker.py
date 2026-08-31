# -*- coding: utf-8 -*-
"""主题选择器：全部主题以按钮网格展示。"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QPushButton, QWidget

from app.theme_loader import theme_json_path
from services.theme_catalog import selectable_themes


def _swatch_icon(theme_id: str, size: int = 20) -> QIcon:
    path = theme_json_path(theme_id)
    if not path.is_file():
        return QIcon()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return QIcon()
    pal = doc.get("palette") or {}
    sidebar = QColor(str(pal.get("surface_sidebar") or "#1E293B"))
    primary = QColor(str(pal.get("primary") or pal.get("accent") or "#2563EB"))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    half = size // 2
    painter.fillRect(0, 0, half, size, sidebar)
    painter.fillRect(half, 0, size - half, size, primary)
    painter.end()
    return QIcon(pix)


class ThemePicker(QWidget):
    """可点击的主题按钮网格；选中项为 checked 状态。"""

    theme_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._applying = False

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        cols = 3
        for index, (tid, label) in enumerate(selectable_themes()):
            btn = QPushButton(label)
            btn.setObjectName("ThemePickerBtn")
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setIcon(_swatch_icon(tid))
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _checked=False, theme_id=tid: self._on_clicked(theme_id))
            self._group.addButton(btn)
            self._buttons[tid] = btn
            grid.addWidget(btn, index // cols, index % cols)

    def set_theme(self, theme_id: str) -> None:
        self._applying = True
        btn = self._buttons.get(theme_id)
        if btn is not None:
            btn.setChecked(True)
        self._applying = False

    def current_theme(self) -> str | None:
        for tid, btn in self._buttons.items():
            if btn.isChecked():
                return tid
        return None

    def _on_clicked(self, theme_id: str) -> None:
        if self._applying:
            return
        self.theme_selected.emit(theme_id)
