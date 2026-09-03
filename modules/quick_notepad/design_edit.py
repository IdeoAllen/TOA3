# -*- coding: utf-8 -*-
"""设计模式编辑器：支持拖右下角缩放正文内图片。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
)

from widgets import TextEdit

_HANDLE = 14
_MIN_W = 48
_MAX_W = 2400


class DesignTextEdit(TextEdit):
    """多功能记事 · 设计页：悬停图片右下角拖拽改显示宽高。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._drag: dict | None = None
        self._hover_rect: QRect | None = None
        self._hover_handle: QRect | None = None
        self.viewport().setMouseTracking(True)
        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self.isReadOnly():
            hit = self._hit_image(event.position().toPoint())
            if hit is not None:
                frag_pos, img_fmt, _rect, handle = hit
                if handle.contains(event.position().toPoint()):
                    w = float(img_fmt.width() or _rect.width())
                    h = float(img_fmt.height() or _rect.height())
                    if w <= 0 or h <= 0:
                        return super().mousePressEvent(event)
                    self._drag = {
                        "pos": frag_pos,
                        "name": img_fmt.name(),
                        "start_w": w,
                        "start_h": h,
                        "aspect": (w / h) if h else 1.0,
                        "origin": event.position().toPoint(),
                    }
                    self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._drag is not None and not self.isReadOnly():
            self._apply_drag(pos)
            event.accept()
            return

        hit = self._hit_image(pos) if not self.isReadOnly() else None
        if hit is not None:
            _pos, _f, rect, handle = hit
            self._hover_rect = rect
            self._hover_handle = handle
            if handle.contains(pos):
                self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport().update()
        else:
            if self._hover_rect is not None:
                self._hover_rect = None
                self._hover_handle = None
                self.viewport().update()
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.viewport().unsetCursor()
            event.accept()
            # 触发 textChanged → 自动保存
            self.textChanged.emit()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_rect = None
        self._hover_handle = None
        self.viewport().unsetCursor()
        self.viewport().update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        handle = self._hover_handle
        rect = self._hover_rect
        if self._drag is not None:
            hit = self._hit_image_at_doc_pos(int(self._drag["pos"]))
            if hit is not None:
                _p, _f, rect, handle = hit
        if handle is None:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if rect is not None and self._drag is None:
            pen = QPen(QColor(37, 99, 235, 140))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(QColor(37, 99, 235))
        painter.drawRect(handle)
        painter.end()

    def _apply_drag(self, pos: QPoint) -> None:
        assert self._drag is not None
        dx = pos.x() - int(self._drag["origin"].x())
        new_w = max(_MIN_W, min(_MAX_W, int(self._drag["start_w"] + dx)))
        aspect = float(self._drag["aspect"]) or 1.0
        new_h = max(_MIN_W, int(round(new_w / aspect)))
        self._set_image_size(int(self._drag["pos"]), str(self._drag["name"]), new_w, new_h)
        hit = self._hit_image_at_doc_pos(int(self._drag["pos"]))
        if hit is not None:
            self._hover_rect = hit[2]
            self._hover_handle = hit[3]
        self.viewport().update()

    def _set_image_size(self, doc_pos: int, name: str, width: int, height: int) -> None:
        doc = self.document()
        frag_pos = doc_pos
        probe = QTextCursor(doc)
        probe.setPosition(doc_pos)
        if not probe.charFormat().isImageFormat():
            if doc_pos > 0:
                probe.setPosition(doc_pos - 1)
                if probe.charFormat().isImageFormat():
                    frag_pos = doc_pos - 1
                else:
                    return
            else:
                return
        old = probe.charFormat().toImageFormat()
        img = QTextImageFormat()
        img.setName(name or old.name())
        img.setWidth(width)
        img.setHeight(height)
        cur = QTextCursor(doc)
        cur.setPosition(frag_pos)
        cur.setPosition(frag_pos + 1, QTextCursor.MoveMode.KeepAnchor)
        cur.mergeCharFormat(img)
        # 不留下选区
        cur.clearSelection()
        cur.setPosition(frag_pos + 1)
        self.setTextCursor(cur)

    def _natural_size(self, name: str) -> tuple[int, int]:
        if not name:
            return 200, 200
        url = QUrl(name)
        res = self.document().resource(QTextDocument.ResourceType.ImageResource, url)
        if res is not None and hasattr(res, "width"):
            try:
                w, h = int(res.width()), int(res.height())
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
        path = url.toLocalFile() if url.isLocalFile() else name
        img = QImage(path)
        if not img.isNull():
            return max(1, img.width()), max(1, img.height())
        return 200, 200

    def _display_size(self, img_fmt: QTextImageFormat) -> tuple[int, int]:
        nw, nh = self._natural_size(img_fmt.name())
        w = int(img_fmt.width()) if img_fmt.width() > 0 else nw
        h = int(img_fmt.height()) if img_fmt.height() > 0 else nh
        if img_fmt.width() > 0 and img_fmt.height() <= 0 and nw > 0:
            h = max(1, int(round(w * nh / nw)))
        return max(1, w), max(1, h)

    def _hit_image(self, view_pos: QPoint):
        """返回 (frag_pos, image_format, rect, handle) 或 None。"""
        best = None
        best_area = None
        for frag_pos, img_fmt, rect in self._iter_image_rects():
            handle = QRect(
                rect.right() - _HANDLE + 1,
                rect.bottom() - _HANDLE + 1,
                _HANDLE,
                _HANDLE,
            )
            if rect.contains(view_pos) or handle.contains(view_pos):
                area = rect.width() * rect.height()
                if best_area is None or area < best_area:
                    best = (frag_pos, img_fmt, rect, handle)
                    best_area = area
        return best

    def _hit_image_at_doc_pos(self, doc_pos: int):
        for frag_pos, img_fmt, rect in self._iter_image_rects():
            if abs(frag_pos - doc_pos) <= 1:
                handle = QRect(
                    rect.right() - _HANDLE + 1,
                    rect.bottom() - _HANDLE + 1,
                    _HANDLE,
                    _HANDLE,
                )
                return frag_pos, img_fmt, rect, handle
        return None

    def _iter_image_rects(self):
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    cf = frag.charFormat()
                    if cf.isImageFormat():
                        img_fmt = cf.toImageFormat()
                        w, h = self._display_size(img_fmt)
                        cur = QTextCursor(doc)
                        cur.setPosition(frag.position())
                        top_left = self.cursorRect(cur).topLeft()
                        yield frag.position(), img_fmt, QRect(top_left, QSize(w, h))
                it += 1
            block = block.next()
