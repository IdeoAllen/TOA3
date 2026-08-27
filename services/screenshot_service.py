# -*- coding: utf-8 -*-
"""区域 / 全屏截图入口；抓取后默认进入微信风格标注层。"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QPen, QPixmap, QFont, QColor
from PySide6.QtWidgets import QWidget

from core.user_messages import show_error, show_info
from services.config_service import get_hotkeys_config
from services.storage_paths import module_output_dir

logger = logging.getLogger(__name__)


def virtual_screen_geometry() -> tuple[int, int, int, int]:
    """虚拟桌面逻辑坐标 (left, top, width, height)。

    必须与 Qt 窗口坐标系一致（逻辑像素），不能用 Win32 物理像素，
    否则高 DPI 下底图会被「放大」显示。
    """
    union = QRect()
    for screen in QGuiApplication.screens():
        union = union.united(screen.geometry())
    if union.isValid() and union.width() > 0 and union.height() > 0:
        return union.x(), union.y(), union.width(), union.height()
    primary = QGuiApplication.primaryScreen()
    if primary is not None:
        g = primary.geometry()
        return g.x(), g.y(), g.width(), g.height()
    return 0, 0, 1920, 1080


def _max_screen_dpr() -> float:
    dprs = [float(s.devicePixelRatio()) for s in QGuiApplication.screens()]
    return max(dprs) if dprs else 1.0


def _attach_logical_dpr(pix: QPixmap, logical_w: int, logical_h: int) -> QPixmap:
    """按位图像素与逻辑桌面尺寸之比写入 devicePixelRatio，避免 1:1 画到逻辑窗里被放大。"""
    if pix.isNull() or logical_w <= 0 or logical_h <= 0:
        return pix
    pw, ph = pix.width(), pix.height()
    ratio = ((pw / float(logical_w)) + (ph / float(logical_h))) / 2.0
    # 贴近常见缩放档，减少浮点误差
    for cand in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
        if abs(ratio - cand) < 0.12:
            ratio = cand
            break
    ratio = max(1.0, float(ratio))
    pix.setDevicePixelRatio(ratio)
    return pix


def grab_virtual_screen() -> QPixmap | None:
    """抓取全部显示器合成图；返回带正确 devicePixelRatio 的位图（逻辑尺寸=虚拟桌面）。"""
    left, top, w, h = virtual_screen_geometry()
    if w <= 0 or h <= 0:
        return None

    dpr = _max_screen_dpr()
    phys_w = max(1, int(round(w * dpr)))
    phys_h = max(1, int(round(h * dpr)))
    composite = QPixmap(phys_w, phys_h)
    composite.fill(Qt.GlobalColor.black)
    composite.setDevicePixelRatio(dpr)

    painter = QPainter(composite)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    ok_any = False
    for screen in QGuiApplication.screens():
        geo = screen.geometry()
        shot = screen.grabWindow(0)
        if shot.isNull():
            continue
        painter.drawPixmap(geo.x() - left, geo.y() - top, shot)
        ok_any = True
    painter.end()
    if ok_any and not composite.isNull():
        return composite

    # 回退 PIL：物理像素抓取后按逻辑尺寸挂上 DPR
    import sys

    if sys.platform == "win32":
        try:
            from PIL import ImageGrab
            from PySide6.QtGui import QImage

            # ImageGrab 的 bbox 在 Windows 上多为物理像素；用各屏 physical 并集更稳
            try:
                pil_img = ImageGrab.grab(all_screens=True)
            except TypeError:
                pil_img = ImageGrab.grab(bbox=(left, top, left + w, top + h))
            pil_img = pil_img.convert("RGB")
            qimg = QImage(
                pil_img.tobytes("raw", "RGB"),
                pil_img.width,
                pil_img.height,
                QImage.Format.Format_RGB888,
            ).copy()
            return _attach_logical_dpr(QPixmap.fromImage(qimg), w, h)
        except Exception:
            logger.debug("PIL virtual screen grab failed", exc_info=True)

    return None


class _RegionOverlay(QWidget):
    """全屏透明层框选区域。"""

    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        left, top, w, h = virtual_screen_geometry()
        self.setGeometry(left, top, w, h)
        self._virt_origin = QPoint(left, top)
        self._origin = QPoint()
        self._current = QPoint()
        self._mouse = QPoint()
        self._dragging = False
        self._result_rect: QRect | None = None
        self.setMouseTracking(True)
        QTimer.singleShot(0, self._seed_mouse_from_cursor)

    def _seed_mouse_from_cursor(self) -> None:
        local = self.mapFromGlobal(QCursor.pos())
        self._mouse = QPoint(
            max(0, min(self.width() - 1, local.x())),
            max(0, min(self.height() - 1, local.y())),
        )
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self._dragging = True

    def mouseMoveEvent(self, event) -> None:
        self._mouse = event.position().toPoint()
        if self._dragging:
            self._current = self._mouse
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._current = event.position().toPoint()
            rect = QRect(self._origin, self._current).normalized()
            self._result_rect = rect if rect.width() > 4 and rect.height() > 4 else None
            self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._result_rect = None
            self.close()

    def closeEvent(self, event) -> None:
        self.finished.emit()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(0.35)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setOpacity(1.0)
        if self._dragging:
            rect = QRect(self._origin, self._current).normalized()
            pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            if rect.width() > 0 and rect.height() > 0:
                label_y = rect.top() - 8 if rect.top() > 24 else rect.bottom() + 16
                painter.setPen(QColor("#FFFFFF"))
                font = QFont()
                font.setPointSize(10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(rect.left() + 4, label_y, f"{rect.width()} × {rect.height()}")

        mx, my = self._mouse.x(), self._mouse.y()
        if not self._dragging:
            return
        sx = self._virt_origin.x() + mx
        sy = self._virt_origin.y() + my
        tx, ty = mx + 16, my + 16
        box_w, box_h = 168, 30
        if tx + box_w > self.width():
            tx = mx - box_w - 16
        if ty + box_h > self.height():
            ty = my - box_h - 16
        tx, ty = max(4, tx), max(4, ty)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRoundedRect(tx, ty, box_w, box_h, 5, 5)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(tx + 8, ty + 20, f"{mx}, {my}  ·  屏幕 {sx}, {sy}")

    @property
    def result_rect(self) -> QRect | None:
        return self._result_rect


def _grab_rect(rect: QRect) -> QPixmap | None:
    left, top, _, _ = virtual_screen_geometry()
    screen = QGuiApplication.screenAt(rect.center())
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None
    # rect 为全局桌面坐标
    return screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())


def _save_pixmap(pix: QPixmap, module_id: str = "screenshot") -> Path:
    out_dir = module_output_dir(module_id, create=True)
    name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = out_dir / name
    pix.save(str(path), "PNG")
    return path


def save_screenshot_pixmap(pix: QPixmap, module_id: str = "screenshot") -> Path:
    """公开：保存位图到模块输出目录。"""
    return _save_pixmap(pix, module_id=module_id)


def _after_grab(pix: QPixmap, parent=None, *, annotate: bool = True, interactive_select: bool = False) -> Path | None:
    """抓取后默认打开全屏标注；annotate=False 时直接保存并复制。"""
    if pix is None or pix.isNull():
        show_error(parent, "截图失败。")
        return None
    if annotate:
        from services.screenshot_overlay import open_screenshot_overlay

        return open_screenshot_overlay(pix, interactive_select=interactive_select, parent=parent)
    path = _save_pixmap(pix)
    QGuiApplication.clipboard().setPixmap(pix)
    try:
        from services.screenshot_history import record_screenshot

        record_screenshot(path, source="direct")
    except Exception:
        logger.debug("history record failed", exc_info=True)
    try:
        from services.notify_bus import NotifyLevel, notify

        notify(NotifyLevel.SUCCESS, title="截图已保存", body=str(path), channel="status")
    except Exception:
        pass
    show_info(parent, f"截图已保存并复制到剪贴板：\n{path}")
    return path


def capture_fullscreen(parent=None, *, annotate: bool = True) -> Path | None:
    pix = grab_virtual_screen()
    if pix is None or pix.isNull():
        show_error(parent, "无法获取屏幕。")
        return None
    return _after_grab(pix, parent, annotate=annotate, interactive_select=False)


def capture_region(parent=None, *, annotate: bool = True) -> Path | None:
    pix = grab_virtual_screen()
    if pix is None or pix.isNull():
        show_error(parent, "无法获取屏幕。")
        return None
    return _after_grab(pix, parent, annotate=annotate, interactive_select=True)


def hotkeys_enabled() -> bool:
    hk = get_hotkeys_config()
    return bool(hk.get("enable_screenshot", True))


def run_screenshot_hotkey(parent=None, *, full: bool = False) -> None:
    if not hotkeys_enabled():
        show_info(parent, "截图功能已在系统设置中关闭。")
        return
    try:
        if full:
            capture_fullscreen(parent)
        else:
            capture_region(parent)
    except Exception as e:
        logger.exception("截图失败")
        show_error(parent, f"截图失败：{e}")


def capture_region_pixmap(parent=None) -> QPixmap | None:
    """仅框选抓取位图，不进标注层。"""
    held: list[QRect | None] = [None]
    overlay = _RegionOverlay()
    loop = QEventLoop()

    def _done() -> None:
        held[0] = overlay.result_rect
        loop.quit()

    overlay.finished.connect(_done)
    overlay.destroyed.connect(loop.quit)
    overlay.showFullScreen()
    overlay.raise_()
    overlay.activateWindow()
    loop.exec()
    rect = held[0]
    if rect is None:
        return None
    return _grab_rect(rect)


def run_screenshot_ocr(parent=None, *, full: bool = False) -> str | None:
    """截图 → OCR → 复制文本；返回识别文本（取消则 None）。"""
    try:
        if full:
            pix = grab_virtual_screen()
            if pix is None or pix.isNull():
                show_error(parent, "无法获取屏幕。")
                return None
        else:
            pix = capture_region_pixmap(parent)
        if pix is None or pix.isNull():
            return None

        path = _save_pixmap(pix, module_id="ocr_tool")
        from services.integrations import get_client

        client = get_client("ocr")
        result = client.recognize_pixmap(pix)
        text = str(result.get("text") or "").strip()
        if text:
            QGuiApplication.clipboard().setText(text)
        try:
            from services.notify_bus import NotifyLevel, notify

            body = f"已复制 {len(text)} 字" if text else "未识别到文字"
            notify(
                NotifyLevel.SUCCESS if text else NotifyLevel.WARNING,
                title="截图转文字",
                body=body,
                channel="all",
                parent=parent,
            )
        except Exception:
            pass
        # 把结果挂到 OCR 页（若已打开/稍后进入）
        try:
            from modules.ocr_tool.ocr_tool_page import OcrToolPage

            OcrToolPage.stash_last_result(text, path=str(path))
        except Exception:
            logger.debug("stash ocr result failed", exc_info=True)
        if not text:
            show_info(parent, "截图完成，但未识别到文字。")
        return text
    except Exception as e:
        logger.exception("截图转文字失败")
        show_error(parent, f"截图转文字失败：{e}")
        return None
