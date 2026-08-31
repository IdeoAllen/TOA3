# -*- coding: utf-8 -*-
"""全屏微信风格截图：框选 / 切图 (S) + 标注 + 浮动工具栏。

对齐 TOA2 wechat_screenshot：先全屏抓取，再在同一层调整选区并标注，导出时按选区裁剪。
# 控件库例外：截图全屏层
"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from services.screenshot_annotate import (
    _BAR_H,
    _COLORS,
    _DEFAULT_COLOR,
    _DEFAULT_WIDTH,
    _HANDLE,
    _HIT_PAD,
    _SEL_BORDER,
    _SUB_H,
    _SUB_ICON,
    _TOOL_BG,
    _TOOL_BORDER,
    _WIDTHS,
    _WX_GREEN,
    AnnotSession,
    AnnotStyle,
    _paint_arrow,
    _paint_shape_box,
    _SubSwatch,
    _ToolBtn,
    build_annot_text_font,
    compose_annotated_pixmap,
    crop_logical,
    densify_points,
    normalize_color,
    paint_pen_stroke,
    refine_pen_points,
    shot_text_edit_stylesheet,
    text_edit_box_height,
    _SHOT_TEXT_EDIT_OBJECT,
)

from services.screenshot_service import virtual_screen_geometry

logger = logging.getLogger(__name__)

# 全局单会话：从热键受理到叠加层关闭全程占锁；再按只取消、绝不叠层
_active_overlay: ScreenshotOverlay | None = None
_session_busy = False
_session_token = 0
_app_state_hooked = False
_ignore_focus_loss_until = 0.0
_cooldown_until = 0.0


def is_screenshot_session_active() -> bool:
    """热键/抓屏/叠加层任一阶段均视为占用。"""
    if _session_busy:
        return True
    try:
        if _active_overlay is not None:
            return True
    except RuntimeError:
        pass
    return _any_overlay_alive()


def _any_overlay_alive() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    for w in app.topLevelWidgets():
        if isinstance(w, ScreenshotOverlay):
            try:
                return True
            except RuntimeError:
                continue
    return False


def try_acquire_screenshot_session() -> int:
    """抢锁成功返回 >0 令牌；失败返回 0（调用方只取消、勿新开）。"""
    global _session_busy, _session_token, _cooldown_until
    import time

    if time.monotonic() < _cooldown_until:
        return 0
    if _session_busy or _active_overlay is not None or _any_overlay_alive():
        return 0
    _session_busy = True
    _session_token += 1
    return _session_token


def current_screenshot_token() -> int:
    return _session_token


def release_screenshot_session() -> None:
    global _session_busy, _active_overlay
    _session_busy = False
    _active_overlay = None


def release_screenshot_session_if_token(token: int) -> None:
    """抓屏失败或未进入叠加层时，按令牌释放占锁。"""
    global _session_busy
    if token and token == _session_token and _active_overlay is None:
        _session_busy = False


def cancel_active_screenshot(*, reason: str = "") -> bool:
    """终止当前截图层并作废进行中的抓屏令牌，清掉所有残留层。"""
    global _active_overlay, _session_busy, _session_token, _cooldown_until
    import time

    if reason:
        logger.info("cancel screenshot session: %s", reason)
    # 作废进行中的 grab→open，防止取消后旧调用又弹出一层
    _session_token += 1
    _cooldown_until = time.monotonic() + 0.4
    closed = False
    ov = _active_overlay
    _active_overlay = None
    if ov is not None:
        try:
            ov._force_abort()
            closed = True
        except Exception:
            logger.debug("cancel primary overlay failed", exc_info=True)
            try:
                ov.close()
                closed = True
            except Exception:
                pass
    app = QApplication.instance()
    if app is not None:
        for w in list(app.topLevelWidgets()):
            if not isinstance(w, ScreenshotOverlay):
                continue
            if w is ov:
                continue
            try:
                w._force_abort()
                closed = True
            except Exception:
                try:
                    w.close()
                    closed = True
                except Exception:
                    pass
    _session_busy = False
    return closed


def _hook_app_state_once() -> None:
    """应用失去前台焦点时自动终止截图。"""
    global _app_state_hooked
    if _app_state_hooked:
        return
    app = QApplication.instance()
    if app is None:
        return
    _app_state_hooked = True

    def _on_state(state) -> None:
        import time

        if time.monotonic() < _ignore_focus_loss_until:
            return
        if state in (
            Qt.ApplicationState.ApplicationInactive,
            Qt.ApplicationState.ApplicationSuspended,
            Qt.ApplicationState.ApplicationHidden,
        ):
            if is_screenshot_session_active():
                cancel_active_screenshot(reason="app_focus_lost")

    app.applicationStateChanged.connect(_on_state)


def _save_pixmap(pix: QPixmap, module_id: str = "screenshot") -> Path:
    from services.storage_paths import module_output_dir

    out_dir = module_output_dir(module_id, create=True)
    name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = out_dir / name
    if path.exists():
        name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S_%f.png")
        path = out_dir / name
    pix.save(str(path), "PNG")
    return path


class ScreenshotOverlay(QWidget):
    """全屏截图 + 框选切图 + 标注。"""

    finished_ok = Signal(object)
    finished_cancel = Signal()

    def __init__(self, bg: QPixmap, *, interactive_select: bool = False, parent=None) -> None:
        # 必须顶层窗：挂到 MainShell 时 WindowShortcut(Esc) 会被壳吃掉，多屏几何也被父窗裁切 → 框选/Esc 失灵
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        _ = parent  # 仅兼容旧调用，不作为 Qt parent
        self._bg = bg
        self._session = AnnotSession()
        self._style = AnnotStyle()
        self._interactive_select = interactive_select
        # 全屏直进标注：默认马赛克（培训/反馈路径）；区域框选完成后再切马赛克
        self._mode = "select" if interactive_select else "rect"
        self._sel: QRect | None = None if interactive_select else QRect(0, 0, bg.width(), bg.height())
        self._selecting = False
        self._resizing: str | None = None
        self._drag_origin_sel: QRect | None = None
        self._drag_origin = QPoint()
        self._drawing = False
        self._pen_points: list[tuple[float, float]] = []
        self._origin = QPointF()
        self._preview: dict[str, Any] | None = None
        self._shift = False
        self._text_edit: QLineEdit | None = None
        self._toolbar: QWidget | None = None
        self._sub: QWidget | None = None
        self._sub_l: QHBoxLayout | None = None
        self._tool_btns: dict[str, _ToolBtn] = {}
        self._color_btns: list[_SubSwatch] = []
        self._width_btns: dict[int, _SubSwatch] = {}
        self._style_btns: dict[str, _SubSwatch] = {}
        self._accepted = False
        self._result_path: Path | None = None

        left, top, w, h = virtual_screen_geometry()
        self.setGeometry(left, top, w, h)
        self._virt_left = left
        self._virt_top = top
        self._mouse = QPoint(w // 2, h // 2)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bind_shortcuts()
        if not interactive_select:
            QTimer.singleShot(30, self._show_toolbar)
        else:
            QTimer.singleShot(0, self._seed_loupe_from_cursor)
            QTimer.singleShot(0, self._claim_input)

    def _claim_input(self) -> None:
        """框选阶段即抢键鼠，避免 Esc/拖拽被主壳或其它浮层截走。"""
        if not self.isVisible():
            return
        try:
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            self.grabMouse()
            self.grabKeyboard()
        except Exception:
            logger.debug("screenshot claim input failed", exc_info=True)

    def changeEvent(self, event) -> None:  # noqa: N802
        # 切到其它应用时终止（与 applicationStateChanged 双保险）
        if event.type() == QEvent.Type.WindowDeactivate:
            import time

            if time.monotonic() >= _ignore_focus_loss_until and is_screenshot_session_active():
                # 延迟一拍：工具栏弹窗等内部失焦勿误杀
                QTimer.singleShot(80, self._maybe_abort_on_deactivate)
        super().changeEvent(event)

    def _maybe_abort_on_deactivate(self) -> None:
        import time

        if time.monotonic() < _ignore_focus_loss_until:
            return
        app = QApplication.instance()
        if app is None:
            return
        active = app.activeWindow()
        # 本应用内其它窗（主壳/错误弹窗）抢焦点时也要退出，否则 grabKeyboard 卡死
        if active is not None and active is not self:
            try:
                if not self.isAncestorOf(active):
                    if is_screenshot_session_active():
                        cancel_active_screenshot(reason="focus_lost_in_app")
                    return
            except RuntimeError:
                pass
        # 仍属本应用前台则保留（例如工具栏子菜单）；真正切到其它进程才取消
        if app.applicationState() == Qt.ApplicationState.ApplicationActive:
            return
        if is_screenshot_session_active():
            cancel_active_screenshot(reason="window_deactivate")

    def _bind_shortcuts(self) -> None:
        for seq, slot in (
            ("Ctrl+Z", self._undo),
            ("Ctrl+Y", self._redo),
            ("Ctrl+Shift+Z", self._redo),
            ("Return", self._on_ok),
            ("Enter", self._on_ok),
            # Esc 不走 QShortcut：与 eventFilter 双触发会「一键连退两级」甚至卡死
            ("R", lambda: self._select_tool("rect")),
            ("C", lambda: self._select_tool("ellipse")),
            ("A", lambda: self._select_tool("arrow")),
            ("P", lambda: self._select_tool("pen")),
            ("M", lambda: self._select_tool("mosaic")),
            ("T", lambda: self._select_tool("text")),
            ("S", self._hotkey_select),
            ("F", self._hotkey_fill),
            ("Ctrl+S", self._save_as),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)

        # 1/2/3：全部标注工具线宽/字号（Application 级，避免焦点落在子控件时失效）
        for key, idx in (
            (Qt.Key.Key_1, 0),
            (Qt.Key.Key_2, 1),
            (Qt.Key.Key_3, 2),
        ):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda i=idx: self._pick_width_hotkey(i, force=True))
            sc_c = QShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | key), self)
            sc_c.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc_c.activated.connect(lambda i=idx: self._pick_width_hotkey(i, force=True))

        QApplication.instance().installEventFilter(self)
        self._esc_guard_until = 0.0
        self.setFocus()

    def _try_width_key(self, event) -> bool:
        """1/2/3 → 细/中/粗，对矩形·椭圆·箭头·画笔·马赛克·文字全部生效。"""
        width_map = {
            Qt.Key.Key_1: 0,
            Qt.Key.Key_2: 1,
            Qt.Key.Key_3: 2,
            Qt.Key.Key_Keypad1: 0,
            Qt.Key.Key_Keypad2: 1,
            Qt.Key.Key_Keypad3: 2,
        }
        for name, idx in (("Key_Keypad1", 0), ("Key_Keypad2", 1), ("Key_Keypad3", 2)):
            k = getattr(Qt.Key, name, None)
            if k is not None:
                width_map[k] = idx
        key = event.key()
        if key not in width_map:
            return False
        # 有其它修饰键（除 Ctrl）时不抢，避免挡 Alt+… 全局热键
        mods = event.modifiers()
        if mods & (
            Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
            | Qt.KeyboardModifier.ShiftModifier
        ):
            return False
        # 文字输入框聚焦时不抢数字键
        if self._text_edit is not None:
            try:
                if self._text_edit.hasFocus():
                    return False
            except RuntimeError:
                pass
        self._pick_width_hotkey(width_map[key], force=True)
        return True

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if not self.isVisible():
            return super().eventFilter(obj, event)
        # 模态对话框（另存/OCR）期间不抢 Esc
        if QApplication.activeModalWidget() is not None:
            return super().eventFilter(obj, event)
        if et == QEvent.Type.ShortcutOverride and event.key() == Qt.Key.Key_Escape:
            # accept = 声明接管 Esc；return False 让 KeyPress 继续到达
            event.accept()
            return False
        if et == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            event.accept()
            self._handle_escape()
            return True
        if et == QEvent.Type.KeyPress:
            if self._try_width_key(event):
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._handle_escape()
            event.accept()
            return
        if self._try_width_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def _seed_loupe_from_cursor(self) -> None:
        """框选前立即显示当前鼠标坐标（对齐 TOA2 取景）。"""
        local = self.mapFromGlobal(QCursor.pos())
        self._mouse = QPoint(
            max(0, min(self.width() - 1, local.x())),
            max(0, min(self.height() - 1, local.y())),
        )
        self.update()

    def _loupe_visible(self) -> bool:
        """仅在框选/调整选区时显示取景，标注阶段隐藏以免挡视线。"""
        if self._selecting or self._resizing:
            return True
        return bool(self._interactive_select and self._sel is None)

    def _sample_surface_pixmap(self) -> QPixmap:
        """当前可见画面（底图 + 已提交标注 + 实时预览），用于取色/放大镜。"""
        annots = list(self._session.annots)
        if self._preview and self._preview.get("type") in ("mosaic",):
            annots = annots + [self._preview]
        composed = compose_annotated_pixmap(self._bg, annots)
        if self._preview and self._preview.get("type") not in ("mosaic",):
            pm = QPixmap(composed.size())
            pm.setDevicePixelRatio(composed.devicePixelRatio())
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.drawPixmap(0, 0, composed)
            self._paint_preview(painter, self._preview)
            painter.end()
            return pm
        return composed

    def _sample_color_at(self, cx: int, cy: int, surface: QPixmap | None = None) -> tuple[int, int, int]:
        pm = surface if surface is not None else self._sample_surface_pixmap()
        img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        dpr = max(1.0, float(pm.devicePixelRatio()))
        px = min(img.width() - 1, max(0, int(round(cx * dpr))))
        py = min(img.height() - 1, max(0, int(round(cy * dpr))))
        c = QColor(img.pixel(px, py))
        return c.red(), c.green(), c.blue()

    def _pixel_rgb(self, cx: int, cy: int) -> str:
        r, g, b = self._sample_color_at(cx, cy)
        return f"RGB({r}, {g}, {b})"

    def _paint_sel_size(self, p: QPainter) -> None:
        if self._sel is None or self._sel.width() < 1:
            return
        if not (self._selecting or self._resizing):
            return
        r = self._sel
        label_y = r.top() - 8 if r.top() > 28 else r.bottom() + 16
        p.setPen(QColor("#FFFFFF"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)
        p.drawText(r.left() + 6, label_y, f"{r.width()} × {r.height()}")

    def _paint_loupe(self, p: QPainter, cx: int, cy: int) -> None:
        """微信式取景：放大镜 + 坐标 + 当前像素色（所见即所得取色）。"""
        surface = self._sample_surface_pixmap()
        bw, bh = surface.width(), surface.height()
        cx = max(0, min(bw - 1, cx))
        cy = max(0, min(bh - 1, cy))

        src_r = 7
        zoom = 5
        x0, y0 = max(0, cx - src_r), max(0, cy - src_r)
        x1, y1 = min(bw, cx + src_r + 1), min(bh, cy + src_r + 1)
        if x1 <= x0 or y1 <= y0:
            return

        crop_w, crop_h = x1 - x0, y1 - y0
        out_w, out_h = crop_w * zoom, crop_h * zoom
        info_h = 34
        pad = 6
        box_w = max(out_w + pad * 2, 188)

        # 跟鼠标走，优先右下；贴边时翻转
        lx, ly = cx + 18, cy + 18
        if lx + box_w > bw - 4:
            lx = cx - box_w - 18
        if ly + out_h + info_h + pad * 2 > bh - 4:
            ly = cy - out_h - info_h - pad * 2 - 18
        lx, ly = max(4, lx), max(4, ly)

        outer = QRect(lx, ly, box_w, out_h + info_h + pad * 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawRoundedRect(outer, 6, 6)

        crop = surface.copy(QRect(x0, y0, crop_w, crop_h))
        scaled = crop.scaled(
            out_w,
            out_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        mag_x, mag_y = lx + pad, ly + pad
        p.fillRect(mag_x, mag_y, out_w, out_h, QColor(32, 32, 32))
        p.drawPixmap(mag_x, mag_y, scaled)

        accent = QColor(_WX_GREEN)
        p.setPen(QPen(accent, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(mag_x, mag_y, out_w, out_h)
        mid_x, mid_y = mag_x + out_w // 2, mag_y + out_h // 2
        p.drawLine(mid_x, mag_y, mid_x, mag_y + out_h)
        p.drawLine(mag_x, mid_y, mag_x + out_w, mid_y)

        screen_x = self._virt_left + cx
        screen_y = self._virt_top + cy
        r, g, b = self._sample_color_at(cx, cy, surface)
        rgb = f"RGB({r}, {g}, {b})"

        info_y = mag_y + out_h + pad
        swatch = QRect(lx + pad, info_y + 10, 14, 14)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.setBrush(QColor(r, g, b))
        p.drawRoundedRect(swatch, 2, 2)

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(lx + pad + 20, info_y + 14, f"{cx}, {cy}")
        font.setBold(False)
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QColor("#B8B8B8"))
        p.drawText(lx + pad + 20, info_y + 28, f"屏幕 {screen_x}, {screen_y} · {rgb}")

    def _clamp_sel(self, x1: int, y1: int, x2: int, y2: int) -> QRect:
        w, h = self._bg.width(), self._bg.height()
        x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
        y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
        return QRect(x1, y1, max(0, x2 - x1), max(0, y2 - y1))

    def _hit_handle(self, x: int, y: int) -> str | None:
        if self._sel is None:
            return None
        r = self._sel
        pad = _HIT_PAD
        handles = {
            "nw": QRect(r.left() - pad, r.top() - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "ne": QRect(r.right() - _HANDLE - pad, r.top() - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "sw": QRect(r.left() - pad, r.bottom() - _HANDLE - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "se": QRect(r.right() - _HANDLE - pad, r.bottom() - _HANDLE - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "n": QRect(r.center().x() - pad, r.top() - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "s": QRect(r.center().x() - pad, r.bottom() - _HANDLE - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "w": QRect(r.left() - pad, r.center().y() - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
            "e": QRect(r.right() - _HANDLE - pad, r.center().y() - pad, _HANDLE + pad * 2, _HANDLE + pad * 2),
        }
        for name, box in handles.items():
            if box.contains(x, y):
                return name
        return None

    def _inside_sel(self, x: int, y: int) -> bool:
        return self._sel is not None and self._sel.contains(x, y)

    def _begin_reselect(self, x: int, y: int) -> None:
        self._selecting = True
        self._drag_origin = QPoint(x, y)
        self._sel = QRect(x, y, 0, 0)
        self._session.annots.clear()
        self._session.redo.clear()
        self._mode = "select"
        self._hide_toolbar()
        self._preview = None
        self.update()

    def _restore_toolbar_keyboard(self) -> None:
        if self.isVisible() and self._toolbar is not None and self._toolbar.isVisible():
            try:
                self.activateWindow()
                self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
                self.grabKeyboard()
            except Exception:
                pass

    def _release_toolbar_keyboard(self) -> None:
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        try:
            self.releaseMouse()
        except Exception:
            pass

    def _hide_toolbar(self) -> None:
        if self._toolbar is not None:
            self._toolbar.hide()
        # 重新框选时再抢鼠标
        try:
            if self.isVisible():
                self.grabMouse()
                self.grabKeyboard()
        except Exception:
            pass

    def _show_toolbar(self) -> None:
        if self._sel is None or self._sel.width() < 6 or self._sel.height() < 6:
            return
        if self._toolbar is None:
            self._build_toolbar()
        # 框选后可能先设 _mode 再建栏：同步选中态
        for k, btn in self._tool_btns.items():
            btn.setChecked(k == self._mode)
        self._rebuild_subbar()
        self._position_toolbar()
        self._toolbar.show()
        self._toolbar.raise_()
        # 工具栏需正常点选：松开鼠标抢占，仅保留键盘
        try:
            self.releaseMouse()
        except Exception:
            pass
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.grabKeyboard()

    def _build_toolbar(self) -> None:
        wrap = QWidget(self)
        wrap.setStyleSheet(
            f"QWidget {{ background: {_TOOL_BG}; border-radius: 10px; border: 1px solid {_TOOL_BORDER}; }}"
        )
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(2)

        bar = QWidget(wrap)
        bar.setFixedHeight(_BAR_H)
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(4, 2, 4, 2)
        bar_l.setSpacing(3)

        # 矩形默认 · 箭头第三（主理人）
        for key, tip in (
            ("rect", "矩形 (R)"),
            ("ellipse", "椭圆 (C)"),
            ("arrow", "箭头 (A)"),
            ("pen", "画笔 (P)"),
            ("mosaic", "马赛克 (M) · Shift=矩形"),
            ("text", "文字 (T)"),
        ):
            btn = _ToolBtn(tip=tip, icon_key=key, checkable=True, parent=bar)
            btn.clicked.connect(lambda _=False, k=key: self._select_tool(k))
            bar_l.addWidget(btn)
            self._tool_btns[key] = btn

        bar_l.addSpacing(6)
        btn_undo = _ToolBtn(tip="撤销 (Ctrl+Z)", icon_key="undo", parent=bar)
        btn_undo.clicked.connect(self._undo)
        bar_l.addWidget(btn_undo)
        btn_redo = _ToolBtn(tip="重做 (Ctrl+Y)", icon_key="redo", parent=bar)
        btn_redo.clicked.connect(self._redo)
        bar_l.addWidget(btn_redo)

        bar_l.addSpacing(6)
        btn_ocr = _ToolBtn(tip="图转文 OCR", icon_key="ocr", parent=bar)
        btn_ocr.clicked.connect(self._on_ocr_only)
        bar_l.addWidget(btn_ocr)
        btn_tr = _ToolBtn(tip="翻译（OCR+译文）", icon_key="translate", parent=bar)
        btn_tr.clicked.connect(self._on_translate)
        bar_l.addWidget(btn_tr)
        btn_save = _ToolBtn(tip="保存 (Ctrl+S)", icon_key="save", parent=bar)
        btn_save.clicked.connect(self._save_as)
        bar_l.addWidget(btn_save)
        btn_ok = _ToolBtn(tip="完成并复制 (Enter)", icon_key="ok", parent=bar)
        btn_ok.setStyleSheet(
            btn_ok.styleSheet() + f"QPushButton {{ background: {_WX_GREEN}; border-color: {_WX_GREEN}; }}"
        )
        btn_ok.clicked.connect(self._on_ok)
        bar_l.addWidget(btn_ok)
        btn_cancel = _ToolBtn(tip="取消 (Esc)", icon_key="cancel", parent=bar)
        btn_cancel.clicked.connect(self._abort_overlay)
        bar_l.addWidget(btn_cancel)

        outer.addWidget(bar)

        sub = QWidget(wrap)
        sub.setFixedHeight(_SUB_H)
        sub.setStyleSheet("QWidget { background: #262626; border-radius: 8px; border: 1px solid #333; }")
        self._sub = sub
        self._sub_l = QHBoxLayout(sub)
        self._sub_l.setContentsMargins(8, 6, 8, 6)
        self._sub_l.setSpacing(4)
        outer.addWidget(sub)

        self._toolbar = wrap

    def _position_toolbar(self) -> None:
        if self._toolbar is None or self._sel is None:
            return
        self._toolbar.adjustSize()
        bw = max(self._toolbar.width(), 120)
        bh = self._toolbar.height()
        left = max(8, min(self._sel.left(), self.width() - bw - 8))
        top = self._sel.bottom() + 10
        if top + bh + 8 > self.height() - 4:
            top = max(8, self._sel.top() - bh - 10)
        self._toolbar.setGeometry(left, top, bw, bh)

    def _select_tool(self, mode: str) -> None:
        self._commit_text_if_any()
        self._mode = mode
        for k, btn in self._tool_btns.items():
            btn.setChecked(k == mode)
        self._rebuild_subbar()
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _rebuild_subbar(self) -> None:
        if self._sub_l is None or self._sub is None:
            return
        while self._sub_l.count():
            item = self._sub_l.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._color_btns.clear()
        self._width_btns.clear()
        self._style_btns.clear()

        need = self._mode in ("rect", "ellipse", "arrow", "pen", "mosaic", "text")
        self._sub.setVisible(need)
        if not need:
            return

        st = self._style
        for c in _COLORS:
            btn = _SubSwatch(self._sub)
            btn.configure_color(c)
            btn.setChecked(normalize_color(c) == normalize_color(st.color))
            btn.clicked.connect(lambda _=False, col=c: self._pick_color(col))
            self._sub_l.addWidget(btn)
            self._color_btns.append(btn)

        sep = QLabel("|", self._sub)
        sep.setStyleSheet("color: #555; background: transparent; border: none; font-size: 18px;")
        self._sub_l.addWidget(sep)

        for w in _WIDTHS:
            btn = _SubSwatch(self._sub)
            btn.configure_width(
                w,
                mosaic=(self._mode == "mosaic"),
                filled_shape=(self._mode in ("rect", "ellipse") and st.filled),
            )
            btn.setChecked(w == st.width)
            btn.clicked.connect(lambda _=False, ww=w: self._pick_width(ww))
            self._sub_l.addWidget(btn)
            self._width_btns[w] = btn

        if self._mode in ("rect", "ellipse"):
            sep_fill = QLabel("|", self._sub)
            sep_fill.setStyleSheet("color: #555; background: transparent; border: none; font-size: 18px;")
            self._sub_l.addWidget(sep_fill)
            fill_btn = _SubSwatch(self._sub)
            fill_btn.configure_fill()
            fill_btn.setChecked(bool(st.filled))
            fill_btn.clicked.connect(lambda _=False: self._toggle_filled())
            self._sub_l.addWidget(fill_btn)
            self._style_btns["filled"] = fill_btn

        if self._mode == "text":
            sep2 = QLabel("|", self._sub)
            sep2.setStyleSheet("color: #555; background: transparent; border: none; font-size: 18px;")
            self._sub_l.addWidget(sep2)
            for key, lab in (("bold", "B"), ("italic", "I"), ("strike", "S")):
                btn = _SubSwatch(self._sub)
                btn.configure_style(key, lab)
                on = bool(getattr(st, key, False))
                btn.setChecked(on)
                btn.clicked.connect(lambda _=False, k=key: self._toggle_style(k))
                self._sub_l.addWidget(btn)
                self._style_btns[key] = btn

        self._sub_l.addStretch(1)
        self._position_toolbar()

    def _pick_color(self, color: str) -> None:
        self._style.color = normalize_color(color)
        for btn in self._color_btns:
            btn.setChecked(normalize_color(btn._color) == normalize_color(color))

    def _pick_width(self, width: int) -> None:
        """细/中/粗：矩形/椭圆/箭头/画笔/马赛克/文字字号共用（与当前选中工具无关）。"""
        self._style.width = int(width)
        # 副栏可能因工具切换暂空，仍写入样式，下次笔画立即生效
        for w, btn in list(self._width_btns.items()):
            btn.setChecked(w == width)
        if self._preview is not None:
            self._preview["width"] = int(width)
            self.update()
        if self._text_edit is not None:
            self._sync_text_edit_style()

    def _pick_width_hotkey(self, index: int, *, force: bool = False) -> None:
        """1/2/3 → 细/中/粗，全部标注工具。"""
        if not force and self._text_edit is not None and self._text_edit.hasFocus():
            return
        if 0 <= index < len(_WIDTHS):
            self._pick_width(_WIDTHS[index])

    def _toggle_filled(self) -> None:
        self._style.filled = not self._style.filled
        btn = self._style_btns.get("filled")
        if btn is not None:
            btn.setChecked(self._style.filled)
        if self._preview and self._preview.get("type") in ("rect", "ellipse"):
            self._preview["filled"] = self._style.filled
            self.update()
        self._rebuild_subbar()

    def _toggle_style(self, key: str) -> None:
        cur = bool(getattr(self._style, key, False))
        setattr(self._style, key, not cur)
        btn = self._style_btns.get(key)
        if btn is not None:
            btn.setChecked(not cur)
        if self._text_edit is not None:
            self._sync_text_edit_style()

    def _undo(self) -> None:
        self._commit_text_if_any()
        if self._session.undo():
            self.update()

    def _redo(self) -> None:
        self._commit_text_if_any()
        if self._session.redo_one():
            self.update()

    def _hotkey_select(self) -> None:
        if self._text_edit is not None:
            return
        self._session.annots.clear()
        self._session.redo.clear()
        self._sel = None
        self._mode = "select"
        self._hide_toolbar()
        self.update()

    def _hotkey_fill(self) -> None:
        if self._text_edit is not None:
            return
        if self._mode not in ("rect", "ellipse"):
            return
        self._toggle_filled()

    def _compose_result(self) -> QPixmap | None:
        if self._sel is None:
            return None
        r = self._sel
        if r.width() < 2 or r.height() < 2:
            return None
        full = compose_annotated_pixmap(self._bg, self._session.annots)
        return crop_logical(full, r)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # 马赛克预览并入 compose，做到所见即所得（勿只画灰线）
        annots = list(self._session.annots)
        preview_mosaic = False
        if self._preview and self._preview.get("type") in ("mosaic",):
            annots = annots + [self._preview]
            preview_mosaic = True
        composed = compose_annotated_pixmap(self._bg, annots)
        p.drawPixmap(self.rect(), composed)

        if self._sel is not None and self._sel.width() > 0 and self._sel.height() > 0:
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))
            path.addRect(QRectF(self._sel))
            path.setFillRule(Qt.FillRule.OddEvenFill)
            p.fillPath(path, QColor(0, 0, 0, 100))
            pen = QPen(QColor(_SEL_BORDER), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self._sel)
            self._draw_handles(p)
        else:
            p.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._preview and not preview_mosaic:
            self._paint_preview(p, self._preview)

        if self._interactive_select and self._sel is None and not self._selecting:
            p.setPen(QColor("#FFFFFF"))
            p.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter),
                "拖拽框选区域 · Esc 取消",
            )

        self._paint_sel_size(p)
        if self._loupe_visible():
            self._paint_loupe(p, self._mouse.x(), self._mouse.y())

    def _draw_handles(self, p: QPainter) -> None:
        if self._sel is None:
            return
        r = self._sel
        hs = _HANDLE
        p.setBrush(QColor(_SEL_BORDER))
        p.setPen(Qt.PenStyle.NoPen)
        for pt in (
            (r.left(), r.top()),
            (r.right() - hs, r.top()),
            (r.left(), r.bottom() - hs),
            (r.right() - hs, r.bottom() - hs),
            (r.center().x() - hs // 2, r.top()),
            (r.center().x() - hs // 2, r.bottom() - hs),
            (r.left(), r.center().y() - hs // 2),
            (r.right() - hs, r.center().y() - hs // 2),
        ):
            p.drawRect(pt[0], pt[1], hs, hs)

    def _paint_preview(self, p: QPainter, a: dict[str, Any]) -> None:
        t = a.get("type")
        color = QColor(normalize_color(a.get("color")))
        w = max(1, int(a.get("width") or self._style.width))
        if t in ("rect", "ellipse", "mosaic_rect"):
            if t == "mosaic_rect":
                pen = QPen(QColor("#AAAAAA"), w)
                pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                rect = QRectF(a["x1"], a["y1"], a["x2"] - a["x1"], a["y2"] - a["y1"]).normalized()
                if t == "ellipse":
                    p.drawEllipse(rect)
                else:
                    p.drawRect(rect)
            else:
                _paint_shape_box(
                    p,
                    t,
                    float(a["x1"]),
                    float(a["y1"]),
                    float(a["x2"]),
                    float(a["y2"]),
                    color,
                    w,
                    filled=bool(a.get("filled")),
                )
        elif t == "arrow":
            _paint_arrow(p, a["x1"], a["y1"], a["x2"], a["y2"], color, w)
        elif t in ("pen", "mosaic"):
            pts = a.get("points") or []
            if t == "pen":
                paint_pen_stroke(
                    p,
                    [(float(pt[0]), float(pt[1])) for pt in pts],
                    color=color,
                    width=w,
                    smooth=True,
                )
            elif len(pts) >= 2:
                pen = QPen(
                    QColor("#888888"),
                    w,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
                p.setPen(pen)
                for i in range(1, len(pts)):
                    p.drawLine(QPointF(*pts[i - 1]), QPointF(*pts[i]))

    def _constrain(self, o: QPointF, c: QPointF) -> QPointF:
        if not self._shift:
            return c
        dx, dy = c.x() - o.x(), c.y() - o.y()
        m = max(abs(dx), abs(dy))
        return QPointF(o.x() + math.copysign(m, dx or 1), o.y() + math.copysign(m, dy or 1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = int(event.position().x()), int(event.position().y())
        self._commit_text_if_any()

        if self._sel is None:
            self._begin_reselect(x, y)
            return

        handle = self._hit_handle(x, y)
        if handle:
            self._resizing = handle
            self._drag_origin = QPoint(x, y)
            self._drag_origin_sel = QRect(self._sel)
            self._hide_toolbar()
            return

        if not self._inside_sel(x, y):
            self._begin_reselect(x, y)
            return

        if self._mode == "select":
            self._begin_reselect(x, y)
            return

        if self._mode == "text":
            self._begin_text(QPointF(x, y))
            return

        self._drawing = True
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self._origin = QPointF(x, y)
        self._pen_points = [(float(x), float(y))]
        if self._mode in ("pen", "mosaic") and not (self._mode == "mosaic" and self._shift):
            self._preview = {
                "type": self._mode,
                "points": list(self._pen_points),
                "color": self._style.color,
                "width": self._style.width,
            }
        else:
            typ = "mosaic_rect" if (self._mode == "mosaic" and self._shift) else self._mode
            self._preview = {
                "type": typ,
                "x1": float(x),
                "y1": float(y),
                "x2": float(x),
                "y2": float(y),
                "color": self._style.color,
                "width": self._style.width,
                "filled": bool(self._style.filled and typ in ("rect", "ellipse")),
            }
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x, y = int(event.position().x()), int(event.position().y())
        self._mouse = QPoint(x, y)
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if self._selecting:
            ox, oy = self._drag_origin.x(), self._drag_origin.y()
            self._sel = self._clamp_sel(ox, oy, x, y)
            self.update()
            return

        if self._resizing and self._drag_origin_sel is not None:
            self._apply_resize(x, y)
            self.update()
            return

        if not self._drawing:
            if self._loupe_visible():
                self.update()
            return

        if self._mode in ("pen", "mosaic") and not (self._mode == "mosaic" and self._shift):
            if self._pen_points:
                lx, ly = self._pen_points[-1]
                if math.hypot(float(x) - lx, float(y) - ly) < 1.6:
                    return
            self._pen_points.append((float(x), float(y)))
            if self._preview:
                self._preview["points"] = list(self._pen_points)
        else:
            c = self._constrain(self._origin, QPointF(x, y))
            if self._preview:
                self._preview["x2"] = c.x()
                self._preview["y2"] = c.y()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._selecting:
            self._selecting = False
            if self._sel and (self._sel.width() < 6 or self._sel.height() < 6):
                self._sel = None
            else:
                self._mode = "rect"
            self.update()
            self._show_toolbar()
            return

        if self._resizing:
            self._resizing = None
            self._drag_origin_sel = None
            self._mode = "rect"
            self.update()
            self._show_toolbar()
            return

        if not self._drawing:
            return
        self._drawing = False
        x, y = int(event.position().x()), int(event.position().y())
        a = self._finalize_stroke(QPointF(x, y))
        self._preview = None
        if a is not None:
            self._session.push(a)
        self.update()

    def _apply_resize(self, x: int, y: int) -> None:
        if self._drag_origin_sel is None:
            return
        r = QRect(self._drag_origin_sel)
        h = self._resizing or ""
        if "n" in h:
            r.setTop(y)
        if "s" in h:
            r.setBottom(y)
        if "w" in h:
            r.setLeft(x)
        if "e" in h:
            r.setRight(x)
        self._sel = self._clamp_sel(r.left(), r.top(), r.right(), r.bottom())

    def _finalize_stroke(self, pt: QPointF) -> dict[str, Any] | None:
        st = self._style
        if self._mode in ("pen", "mosaic") and not (self._mode == "mosaic" and self._shift):
            self._pen_points.append((pt.x(), pt.y()))
            if self._mode == "pen":
                pts = refine_pen_points(self._pen_points)
            else:
                pts = densify_points(self._pen_points, spacing=2.0)
            if len(pts) < 1:
                return None
            return {"type": self._mode, "points": pts, "color": st.color, "width": st.width}
        c = self._constrain(self._origin, pt)
        x1, y1, x2, y2 = self._origin.x(), self._origin.y(), c.x(), c.y()
        if abs(x2 - x1) < 3 and abs(y2 - y1) < 3:
            return None
        if self._mode == "mosaic" and self._shift:
            return {"type": "mosaic", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": st.width}
        if self._mode in ("rect", "ellipse", "arrow"):
            payload: dict[str, Any] = {
                "type": self._mode,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "color": st.color,
                "width": st.width,
            }
            if self._mode in ("rect", "ellipse") and st.filled:
                payload["filled"] = True
            return payload
        return None

    def _begin_text(self, pt: QPointF) -> None:
        # 只允许一个文字框：先结束旧框并清孤儿
        self._finish_text_edit()
        self._purge_all_text_edits()
        self._release_toolbar_keyboard()
        edit = QLineEdit(self)
        edit.setObjectName(_SHOT_TEXT_EDIT_OBJECT)
        self._text_edit = edit
        edit.setPlaceholderText("输入文字，Enter 确认 · Esc 退出编辑")
        edit._img_origin = pt  # type: ignore[attr-defined]
        self._sync_text_edit_style()
        edit.resize(max(160, 220), edit.height())
        edit.move(int(pt.x()), int(pt.y()))
        edit.returnPressed.connect(self._finish_text_edit)
        edit.installEventFilter(self)
        edit.show()
        edit.raise_()
        edit.setFocus(Qt.FocusReason.MouseFocusReason)

    def _sync_text_edit_style(self) -> None:
        if self._text_edit is None:
            return
        st = self._style
        font = build_annot_text_font(
            st.font_size,
            bold=st.bold,
            italic=st.italic,
            strike=st.strike,
        )
        self._text_edit.setFont(font)
        self._text_edit.setStyleSheet(shot_text_edit_stylesheet(st.color, font))
        h = text_edit_box_height(font)
        self._text_edit.setFixedHeight(h)
        fs = font.pixelSize() if font.pixelSize() > 0 else st.font_size
        self._text_edit.setMinimumWidth(max(160, int(fs * 8)))

    def _purge_all_text_edits(self) -> None:
        """销毁所有文字输入框（含 Esc 曾只清引用留下的孤儿）。"""
        self._text_edit = None
        for child in list(self.findChildren(QLineEdit)):
            try:
                if child.objectName() == _SHOT_TEXT_EDIT_OBJECT:
                    child.hide()
                    child.deleteLater()
            except RuntimeError:
                pass

    def _finish_text_edit(self) -> bool:
        """结束文字编辑：有内容则写入标注保留，无内容则丢弃。返回是否处理了编辑框。"""
        edit = self._text_edit
        if edit is None:
            orphans = [
                c
                for c in self.findChildren(QLineEdit)
                if c.objectName() == _SHOT_TEXT_EDIT_OBJECT
            ]
            if not orphans:
                return False
            edit = orphans[0]

        text = ""
        origin = QPointF(0, 0)
        try:
            text = edit.text().strip()
            origin = getattr(edit, "_img_origin", QPointF(0, 0))
        except RuntimeError:
            pass

        self._purge_all_text_edits()
        self._restore_toolbar_keyboard()
        if text:
            st = self._style
            self._session.push(
                {
                    "type": "text",
                    "x": float(origin.x()),
                    "y": float(origin.y()),
                    "text": text,
                    "color": st.color,
                    "size": st.font_size,
                    "bold": st.bold,
                    "italic": st.italic,
                    "strike": st.strike,
                }
            )
        self.update()
        try:
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        except Exception:
            pass
        return True

    def _commit_text_if_any(self) -> None:
        """点击别处 / Enter：有字保留，无字丢弃（与 Esc 退出编辑一致）。"""
        self._finish_text_edit()

    def _handle_escape(self) -> None:
        """Esc 分级：① 退出文字框（有字保留）② 再按退出截图。防双触发。"""
        import time

        now = time.monotonic()
        if now < float(getattr(self, "_esc_guard_until", 0.0) or 0.0):
            return
        self._esc_guard_until = now + 0.15
        if self._finish_text_edit():
            return
        self._abort_overlay()

    def _abort_overlay(self) -> None:
        """安全退出截图：必松键鼠，清文字框，关层。"""
        if getattr(self, "_aborting", False):
            return
        self._aborting = True
        self._accepted = False
        self._purge_all_text_edits()
        try:
            self.releaseMouse()
        except Exception:
            pass
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        try:
            self.finished_cancel.emit()
        except Exception:
            pass
        self._remove_width_filter()
        self.close()

    def _save_as(self) -> None:
        def _do() -> None:
            pix = self._compose_result()
            if pix is None or pix.isNull():
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "保存截图", "screenshot.png", "PNG (*.png);;JPEG (*.jpg)"
            )
            if path:
                pix.save(path)

        self._with_keyboard_released(_do)

    def _on_text_tools_menu(self) -> None:
        """OCR / 翻译合并为一个按钮，减少工具栏拥挤。"""
        menu = QMenu(self)
        act_ocr = QAction("图转文 OCR（复制原文）", menu)
        act_tr = QAction("截图翻译（OCR → 译文）", menu)
        menu.addAction(act_ocr)
        menu.addAction(act_tr)
        btn = self.sender()
        pos = btn.mapToGlobal(btn.rect().bottomLeft()) if btn is not None else self.cursor().pos()
        chosen = menu.exec(pos)
        if chosen is act_ocr:
            self._on_ocr_only()
        elif chosen is act_tr:
            self._on_translate()

    def _on_ocr_only(self) -> None:
        """截图工具栏：框选区域 OCR → 复制原文（所见即所得出文）。"""

        def _do() -> None:
            pix = self._compose_result()
            if pix is None or pix.isNull():
                return
            try:
                import tempfile
                from pathlib import Path

                from services.integrations import get_client
                from services.screenshot_translate_dialog import TranslateResultDialog

                tmp = Path(tempfile.gettempdir()) / "toa3_shot_ocr.png"
                if not pix.save(str(tmp), "PNG"):
                    raise RuntimeError("临时图保存失败")
                client = get_client("ocr")
                result = client.recognize_image(str(tmp))
                text = str(result.get("text") or "").strip()
                if not text:
                    from core.user_messages import show_warning

                    show_warning(self, "未识别到文字。请在系统设置中配置 OCR。")
                    return
                from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
                from modules.clipboard_history.history_store import push_text

                get_clipboard_watcher().suppress_once()
                QGuiApplication.clipboard().setText(text)
                push_text(text, source="ocr")
                dlg = TranslateResultDialog(
                    self,
                    source=text,
                    translated="（原文已复制。点下方「翻译原文」生成译文。）",
                    offer_translate=True,
                )
                dlg.setWindowTitle("截图转文字")
                dlg.exec()
            except Exception as exc:
                from core.error_handler import report_error

                report_error(self, exc, title="截图转文字失败", context="screenshot_ocr")

        self._with_keyboard_released(_do)

    def _on_translate(self) -> None:
        """先 OCR 出对照窗，再由用户点「翻译原文」（避免一上来就连打 LLM 限流）。"""

        def _do() -> None:
            pix = self._compose_result()
            if pix is None or pix.isNull():
                return
            try:
                from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
                from modules.clipboard_history.history_store import push_text
                from services.screenshot_translate import ocr_only
                from services.screenshot_translate_dialog import TranslateResultDialog

                source = ocr_only(pix)
                if not source:
                    from core.user_messages import show_warning

                    show_warning(self, "未识别到文字。请确认 OCR 已在系统设置中配置。")
                    return
                get_clipboard_watcher().suppress_once()
                QGuiApplication.clipboard().setText(source)
                push_text(source, source="ocr")
                dlg = TranslateResultDialog(
                    self,
                    source=source,
                    translated="（原文已复制。点下方「翻译原文」生成译文。）",
                    offer_translate=True,
                )
                dlg.exec()
            except Exception as exc:
                from core.error_handler import report_error

                report_error(self, exc, title="截图翻译失败", context="screenshot_translate")

        self._with_keyboard_released(_do)
    def _on_ok(self) -> None:
        if self._text_edit is not None:
            self._finish_text_edit()
            return
        pix = self._compose_result()
        if pix is None or pix.isNull():
            self._abort_overlay()
            return
        path = _save_pixmap(pix)
        try:
            from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
            from modules.clipboard_history.history_store import push_image

            # 抑制监听一轮，避免与显式入库重复
            get_clipboard_watcher().suppress_once()
            QGuiApplication.clipboard().setPixmap(pix)
            push_image(pix, source="screenshot")
        except Exception:
            try:
                QGuiApplication.clipboard().setPixmap(pix)
            except Exception:
                logger.debug("clipboard failed", exc_info=True)
        try:
            from services.screenshot_history import record_screenshot

            record_screenshot(path, source="annotate")
        except Exception:
            pass
        try:
            from services.notify_bus import NotifyLevel, notify

            notify(
                NotifyLevel.SUCCESS,
                title="截图已复制",
                body=f"{path.name} · 剪贴板历史可找回",
                channel="status",
            )
        except Exception:
            pass
        self._result_path = path
        self._accepted = True
        self.finished_ok.emit(path)
        self._remove_width_filter()
        self.close()

    def _force_abort(self) -> None:
        """外部强制结束（失焦/重复热键）：松开抢键并关闭，不弹保存。"""
        self._abort_overlay()

    def _on_cancel(self) -> None:
        """工具栏 × / 兼容旧调用 → 与 Esc 同级处理。"""
        self._handle_escape()

    def _remove_width_filter(self) -> None:
        self._release_toolbar_keyboard()
        try:
            self.releaseMouse()
        except Exception:
            pass
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._purge_all_text_edits()
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass

    def _with_keyboard_released(self, fn) -> None:
        """弹窗期间松开键盘抢占，关闭后再抢回（若仍在标注）。"""
        self._release_toolbar_keyboard()
        try:
            fn()
        finally:
            self._restore_toolbar_keyboard()

    def closeEvent(self, event) -> None:  # noqa: N802
        global _active_overlay
        if _active_overlay is self:
            _active_overlay = None
        try:
            self.releaseMouse()
        except Exception:
            pass
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._purge_all_text_edits()
        self._remove_width_filter()
        try:
            release_screenshot_session()
        except Exception:
            pass
        super().closeEvent(event)


def open_screenshot_overlay(
    bg: QPixmap,
    *,
    interactive_select: bool = False,
    parent=None,
    session_token: int = 0,
) -> Path | None:
    """全屏框选 + 标注。session_token 与当前令牌不一致则丢弃（取消后的过期抓屏）。"""
    global _active_overlay, _ignore_focus_loss_until, _session_busy
    if bg is None or bg.isNull():
        release_screenshot_session()
        return None

    # 页面按钮等未带令牌：自行抢锁；已占用则拒绝叠层
    if not session_token:
        if is_screenshot_session_active():
            return None
        session_token = try_acquire_screenshot_session()
        if not session_token:
            return None
    elif session_token != _session_token:
        logger.info("drop stale screenshot open token=%s current=%s", session_token, _session_token)
        return None

    # 已有叠加层：只取消，绝不新开第二层
    if _active_overlay is not None or _any_overlay_alive():
        cancel_active_screenshot(reason="duplicate_open")
        return None

    import time

    _session_busy = True
    _hook_app_state_once()
    _ignore_focus_loss_until = time.monotonic() + 0.45
    held: list[Path | None] = [None]

    def _ok(path: object) -> None:
        held[0] = path if isinstance(path, Path) else None

    overlay = ScreenshotOverlay(bg, interactive_select=interactive_select, parent=None)
    _ = parent
    _active_overlay = overlay
    overlay.finished_ok.connect(_ok)
    loop = QEventLoop()
    overlay.destroyed.connect(loop.quit)
    overlay.finished_cancel.connect(loop.quit)
    overlay.finished_ok.connect(lambda *_: loop.quit())
    left, top, w, h = virtual_screen_geometry()
    overlay.setGeometry(left, top, w, h)
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    if interactive_select:
        overlay._claim_input()
    else:
        try:
            overlay.grabKeyboard()
        except Exception:
            pass
    try:
        loop.exec()
    finally:
        if _active_overlay is overlay:
            _active_overlay = None
        if session_token == _session_token:
            release_screenshot_session()
    return held[0]
