# -*- coding: utf-8 -*-
"""截图钉图：对标 Snipaste 贴屏对照（无边框置顶，Esc / 双击关闭）。"""
from __future__ import annotations

import logging
import weakref

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("TOA3.screenshot_pin")

_PIN_WINDOWS: list[weakref.ref] = []


def _prune_pins() -> None:
    global _PIN_WINDOWS
    live: list[weakref.ref] = []
    for ref in _PIN_WINDOWS:
        w = ref()
        if w is not None:
            try:
                if w.isVisible():
                    live.append(ref)
            except RuntimeError:
                pass
    _PIN_WINDOWS = live


class ScreenshotPinWindow(QWidget):
    """桌面钉图：置顶、无边框、可拖移；Esc / 双击关闭。"""

    closed = Signal()

    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ScreenshotPinWindow")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._pix = QPixmap(pixmap)
        self._drag_origin: QPoint | None = None
        self._win_origin: QPoint | None = None

        dpr = float(self._pix.devicePixelRatio() or 1.0)
        lw = max(1, int(round(self._pix.width() / dpr)))
        lh = max(1, int(round(self._pix.height() / dpr)))
        # 过大时按逻辑像素缩放到可看范围
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            max_w = max(120, int(geo.width() * 0.85))
            max_h = max(120, int(geo.height() * 0.85))
            if lw > max_w or lh > max_h:
                scale = min(max_w / lw, max_h / lh)
                lw = max(1, int(lw * scale))
                lh = max(1, int(lh * scale))
        self.setFixedSize(lw, lh)
        self.setToolTip("钉图 · 拖动移动 · Esc/双击关闭")

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawPixmap(self.rect(), self._pix)
            # 细边框便于在浅色桌面辨认
            p.setPen(Qt.GlobalColor.darkGray)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        finally:
            p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._win_origin = self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._drag_origin is not None
            and self._win_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._drag_origin
            self.move(self._win_origin + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_origin = None
        self._win_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        _prune_pins()
        super().closeEvent(event)


def pin_screenshot(pixmap: QPixmap, *, anchor: QPoint | None = None) -> ScreenshotPinWindow | None:
    """钉一张图到桌面。返回窗口；失败返回 None。"""
    if pixmap is None or pixmap.isNull():
        return None
    try:
        win = ScreenshotPinWindow(pixmap)
    except Exception:
        logger.exception("create pin window failed")
        return None
    if anchor is not None:
        win.move(anchor)
    else:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            win.move(
                geo.left() + max(20, (geo.width() - win.width()) // 2),
                geo.top() + max(20, (geo.height() - win.height()) // 2),
            )
    win.show()
    win.raise_()
    win.activateWindow()
    _prune_pins()
    _PIN_WINDOWS.append(weakref.ref(win))
    logger.info("screenshot pinned size=%sx%s", win.width(), win.height())
    return win
