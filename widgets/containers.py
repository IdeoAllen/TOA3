# -*- coding: utf-8 -*-
"""分区、滚动页、布局行等容器。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.ui_spec import page_content_margins, page_spec


def _page_gap() -> int:
    return int(page_spec().get("spacing") or 12)


class FormSection(QGroupBox):
    """带标题的分区（QGroupBox + 标准内边距）。"""

    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(title, parent)
        self._inner = QVBoxLayout(self)
        self._inner.setSpacing(_page_gap())

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
        self._layout.setSpacing(_page_gap())

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


class HBox(QWidget):
    """水平布局容器（业务页主结构优先用本类，少散落裸 QHBoxLayout）。"""

    def __init__(self, parent=None, *, spacing: int | None = None, margins: int = 0) -> None:
        super().__init__(parent)
        self.setObjectName("HBox")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(margins, margins, margins, margins)
        self._lay.setSpacing(_page_gap() if spacing is None else int(spacing))

    def add_widget(self, widget, stretch: int = 0) -> None:
        self._lay.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self._lay.addLayout(layout, stretch)

    def add_stretch(self, stretch: int = 1) -> None:
        self._lay.addStretch(stretch)

    @property
    def content_layout(self) -> QHBoxLayout:
        return self._lay


class VBox(QWidget):
    """垂直布局容器。"""

    def __init__(self, parent=None, *, spacing: int | None = None, margins: int = 0) -> None:
        super().__init__(parent)
        self.setObjectName("VBox")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(margins, margins, margins, margins)
        self._lay.setSpacing(_page_gap() if spacing is None else int(spacing))

    def add_widget(self, widget, stretch: int = 0) -> None:
        self._lay.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self._lay.addLayout(layout, stretch)

    def add_stretch(self, stretch: int = 1) -> None:
        self._lay.addStretch(stretch)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._lay


class FormRow(QWidget):
    """表单行：左侧标签 + 右侧字段。"""

    def __init__(
        self,
        label: str,
        field: QWidget | None = None,
        *,
        label_width: int = 96,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FormRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._label = QLabel(label)
        self._label.setObjectName("FormRowLabel")
        self._label.setFixedWidth(int(label_width))
        self._label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._label)
        self._field = field
        if field is not None:
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lay.addWidget(field, 1)
        else:
            lay.addStretch(1)

    @property
    def label_widget(self) -> QLabel:
        return self._label

    @property
    def field(self) -> QWidget | None:
        return self._field

    def set_field(self, field: QWidget) -> None:
        lay = self.layout()
        assert lay is not None
        if self._field is not None:
            lay.removeWidget(self._field)
            self._field.setParent(None)
        self._field = field
        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(field, 1)


class PathRow(QWidget):
    """路径行：输入框 + 浏览。"""

    path_changed = Signal(str)

    def __init__(
        self,
        *,
        placeholder: str = "选择路径…",
        browse_label: str = "浏览",
        directory: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PathRow")
        self._directory = bool(directory)
        from widgets.buttons import SecondaryButton
        from widgets.inputs import LineEdit

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._edit = LineEdit(placeholder)
        self._btn = SecondaryButton(browse_label)
        self._btn.clicked.connect(self._browse)
        self._edit.textChanged.connect(self.path_changed.emit)
        lay.addWidget(self._edit, 1)
        lay.addWidget(self._btn)

    def text(self) -> str:
        return self._edit.text().strip()

    def set_text(self, path: str) -> None:
        self._edit.setText(str(path or ""))

    def path(self) -> Path | None:
        t = self.text()
        return Path(t) if t else None

    def _browse(self) -> None:
        start = self.text() or str(Path.home())
        if self._directory:
            chosen = QFileDialog.getExistingDirectory(self, "选择目录", start)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "选择文件", start)
        if chosen:
            self.set_text(chosen)


class GridBox(QWidget):
    """简单网格容器（卡片宫格等）。"""

    def __init__(
        self,
        parent=None,
        *,
        columns: int = 2,
        spacing: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GridBox")
        self._columns = max(1, int(columns))
        self._count = 0
        self._lay = QGridLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        gap = _page_gap() if spacing is None else int(spacing)
        self._lay.setHorizontalSpacing(gap)
        self._lay.setVerticalSpacing(gap)

    def add_widget(self, widget) -> None:
        r, c = divmod(self._count, self._columns)
        self._lay.addWidget(widget, r, c)
        self._count += 1

    def set_columns(self, columns: int) -> None:
        self._columns = max(1, int(columns))


class SplitPane(QSplitter):
    """左右/上下分割（主题跟全局 QSplitter）。"""

    def __init__(self, orientation=None, parent=None) -> None:
        ori = orientation if orientation is not None else Qt.Orientation.Horizontal
        super().__init__(ori, parent)
        self.setObjectName("SplitPane")
        self.setChildrenCollapsible(False)
