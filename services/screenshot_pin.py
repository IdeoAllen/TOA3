# -*- coding: utf-8 -*-
"""截图钉图：对标 Snipaste 贴屏对照（无边框置顶，Esc / 双击关闭）。"""
from __future__ import annotations

import logging
import weakref

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPixmap, QScreen
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


def pin_display_size(
    pixmap: QPixmap,
    *,
    logical_size: tuple[int, int] | None = None,
    screen: QScreen | None = None,
) -> tuple[int, int]:
    """钉图窗口逻辑尺寸：优先用选区逻辑大小，避免 crop 导出（dpr=1 物理像素）贴屏翻倍。"""
    if logical_size is not None:
        lw = max(1, int(logical_size[0]))
        lh = max(1, int(logical_size[1]))
    else:
        dpr = float(pixmap.devicePixelRatio() or 1.0)
        if abs(dpr - 1.0) < 1e-6:
            scr = screen or QGuiApplication.primaryScreen()
            screen_dpr = float(scr.devicePixelRatio()) if scr is not None else 1.0
            if screen_dpr > 1.05:
                dpr = screen_dpr
        lw = max(1, int(round(pixmap.width() / max(1.0, dpr))))
        lh = max(1, int(round(pixmap.height() / max(1.0, dpr))))

    scr = screen or QGuiApplication.primaryScreen()
    if scr is not None:
        geo = scr.availableGeometry()
        max_w = max(120, int(geo.width() * 0.85))
        max_h = max(120, int(geo.height() * 0.85))
        if lw > max_w or lh > max_h:
            scale = min(max_w / lw, max_h / lh)
            lw = max(1, int(lw * scale))
            lh = max(1, int(lh * scale))
    return lw, lh


def _clamp_anchor(anchor: QPoint, width: int, height: int) -> QPoint:
    """把钉图左上角夹到可见屏可用区内，避免多屏/贴边时整窗飞出。"""
    scr = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
    if scr is None:
        return anchor
    geo = scr.availableGeometry()
    x = min(max(anchor.x(), geo.left()), geo.right() - width + 1)
    y = min(max(anchor.y(), geo.top()), geo.bottom() - height + 1)
    return QPoint(x, y)


class ScreenshotPinWindow(QWidget):
    """桌面钉图：置顶、无边框、可拖移；Esc / 双击关闭。"""

    closed = Signal()

    def __init__(
        self,
        pixmap: QPixmap,
        parent=None,
        *,
        logical_size: tuple[int, int] | None = None,
    ) -> None:
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

        lw, lh = pin_display_size(self._pix, logical_size=logical_size)
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


def pin_screenshot(
    pixmap: QPixmap,
    *,
    anchor: QPoint | None = None,
    logical_size: tuple[int, int] | None = None,
) -> ScreenshotPinWindow | None:
    """钉一张图到桌面。返回窗口；失败返回 None。

    logical_size：选区逻辑宽高（与 overlay 一致）。导出图常为物理像素 + dpr=1，
    传入后贴屏尺寸与框选所见一致，避免 HiDPI 下钉图翻倍。
    """
    if pixmap is None or pixmap.isNull():
        return None
    try:
        win = ScreenshotPinWindow(pixmap, logical_size=logical_size)
    except Exception:
        logger.exception("create pin window failed")
        return None
    if anchor is not None:
        win.move(_clamp_anchor(anchor, win.width(), win.height()))
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
