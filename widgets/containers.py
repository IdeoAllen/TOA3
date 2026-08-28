# -*- coding: utf-8 -*-
"""分区、滚动页等容器。"""
from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QScrollArea, QVBoxLayout, QWidget

from core.ui_spec import page_content_margins, page_spec
from widgets.themed_labels import SectionTitle


class FormSection(QGroupBox):
    """带标题的分区（QGroupBox + 标准内边距）。"""

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(title, parent)
        self._inner = QVBoxLayout(self)
        spec = page_spec()
        gap = int(spec.get("spacing") or 12)
        self._inner.setSpacing(gap)

    def add_widget(self, widget, stretch: int = 0) -> None:
        self._inner.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._inner.addLayout(layout)

    def add_stretch(self, stretch: int = 1) -> None:
        self._inner.addStretch(stretch)


class ScrollPage(QScrollArea):
    """可滚动页面容器（业务页外层）。"""

    def __init__(self, parent=None, *, padded: bool = True) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self._host = QWidget()
        self._host.setObjectName("PageRoot")
        self.setWidget(self._host)
        self._layout = QVBoxLayout(self._host)
        if padded:
            m = page_content_margins()
            self._layout.setContentsMargins(m[0], m[1], m[2], m[3])
        else:
            self._layout.setContentsMargins(0, 0, 0, 0)
        spec = page_spec()
        self._layout.setSpacing(int(spec.get("spacing") or 12))

    def add_widget(self, widget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_stretch(self, stretch: int = 1) -> None:
        self._layout.addStretch(stretch)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._layout

    @property
    def content_widget(self) -> QWidget:
        return self._host


class PageHeader(QWidget):
    """页标题 + 可选说明。"""

    def __init__(self, title: str, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        from widgets.themed_labels import HintLabel, PageTitle

        self._hint_label: HintLabel | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(PageTitle(title))
        if hint:
            self._hint_label = HintLabel(hint)
            lay.addWidget(self._hint_label)

    def set_hint(self, text: str) -> None:
        if self._hint_label is None:
            from widgets.themed_labels import HintLabel

            self._hint_label = HintLabel(text or "")
            self.layout().addWidget(self._hint_label)
        else:
            self._hint_label.setText(text or "")
            self._hint_label.setVisible(bool(text))
