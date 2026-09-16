# -*- coding: utf-8 -*-
"""右侧组件库：卡片展示拖入后的样子；拖入落文末。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from modules.quick_notepad.chart_schematic import ChartSchematic, ImageSchematic
from modules.quick_notepad.component_blocks import (
    BlockSpec,
    blocks_by_group,
    markdown_for_block,
    mime_for_block,
)
from modules.quick_notepad.rich_body import refresh_markdown_preview
from widgets import HintLabel, SectionTitle, TextEdit


class _MdEffectPreview(TextEdit):
    """只读：与预览页同一条 refresh_markdown_preview = 拖入后的样子。"""

    def __init__(self, markdown: str, parent=None) -> None:
        super().__init__("", parent)
        self.setObjectName("NotepadComponentLivePreview")
        self.setReadOnly(True)
        self.setAcceptRichText(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(28)
        self.document().setDocumentMargin(4)
        md = (markdown or "").strip()
        if md:
            src = TextEdit("")
            src.setPlainText(md)
            refresh_markdown_preview(src, self)
            src.deleteLater()
        else:
            self.clear()
        self._fit_height()

    def _fit_height(self) -> None:
        doc = self.document()
        doc.adjustSize()
        h = int(doc.size().height()) + 12
        self.setFixedHeight(min(max(h, 32), 160))


class _ComponentCard(QFrame):
    clicked = Signal(str)
    drag_started = Signal(str)

    def __init__(self, spec: BlockSpec, parent=None) -> None:
        super().__init__(parent)
        self._block_id = spec.id
        self._press_pos: QPoint | None = None
        self.setObjectName("NotepadComponentCard")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)

        caption = HintLabel(spec.title)
        caption.setObjectName("NotepadComponentCardCaption")
        caption.setToolTip(spec.hint)
        lay.addWidget(caption)
        # 卡片主体 =「拖进去长什么样」
        if (spec.group or "") == "图表" or str(spec.id).startswith("mermaid_"):
            lay.addWidget(ChartSchematic(spec.id, self))
        elif spec.id in ("image", "icon"):
            lay.addWidget(ImageSchematic(self, kind=spec.id))
        else:
            lay.addWidget(_MdEffectPreview(markdown_for_block(spec.id), self))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.position().toPoint() - self._press_pos
            if delta.manhattanLength() >= 8:
                self._press_pos = None
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self.drag_started.emit(self._block_id)
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_pos is not None
        ):
            self._press_pos = None
            self.clicked.emit(self._block_id)
            return
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        md = mime_for_block(self._block_id)
        if md is None:
            return
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.CopyAction)


class ComponentPalette(QWidget):
    insert_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NotepadComponentPalette")
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(6, 6, 6, 6)
        self._root.setSpacing(4)

        self._head = SectionTitle("组件")
        self._root.addWidget(self._head)
        self._tip = HintLabel("卡片=拖入后的样子 · 点或拖到编辑区")
        self._tip.setWordWrap(True)
        self._root.addWidget(self._tip)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("NotepadComponentScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._root.addWidget(self._scroll, 1)

        self.set_surface("md")

    def set_surface(self, surface: str) -> None:
        self._head.setText("组件")
        self._tip.setText("卡片=拖入后的样子 · 点或拖到编辑区")

        inner = QWidget()
        inner.setObjectName("NotepadComponentList")
        col = QVBoxLayout(inner)
        col.setContentsMargins(2, 2, 2, 2)
        col.setSpacing(6)
        for group_name, specs in blocks_by_group("md"):
            col.addWidget(SectionTitle(group_name))
            for spec in specs:
                card = _ComponentCard(spec, inner)
                card.setToolTip(
                    f"{spec.title}\n拖入后效果见卡片样子\n点击或拖入 → 文末"
                )
                card.clicked.connect(self.insert_requested.emit)
                col.addWidget(card)
        col.addStretch(1)
        self._scroll.setWidget(inner)

    def clear_selection(self) -> None:
        return
