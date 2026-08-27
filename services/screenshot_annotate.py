# -*- coding: utf-8 -*-
"""微信风格截图标注层（PySide6）。

从抓取的 QPixmap 进入无边框标注窗：矩形 / 椭圆 / 箭头 / 画笔 / 马赛克 / 文字，
撤销重做，完成时保存 PNG + 剪贴板。

纯几何与马赛克参数可无显示器单元测试；UI 需 QApplication。
# 控件库例外：截图全屏标注层（深色工具栏 chrome，不走业务页 Themed*）
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QEventLoop, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.storage_paths import module_output_dir

logger = logging.getLogger(__name__)

# —— 与 TOA2 wechat_screenshot 对齐的令牌 ——
_WX_GREEN = "#07C160"
_TOOL_BG = "#2C2C2C"
_TOOL_BTN = "#2C2C2C"
_TOOL_BTN_HOVER = "#3A3A3A"
_TOOL_BTN_ACTIVE = "#07C160"
_TOOL_FG = "#F5F5F5"
_TOOL_BORDER = "#3F3F3F"

_COLORS = (
    "#FA5151",
    "#FFC300",
    "#07C160",
    "#10AEFF",
    "#1485EE",
    "#6467F0",
    "#FFFFFF",
    "#191919",
)
_DEFAULT_COLOR = "#FA5151"
_DEFAULT_WIDTH = 2  # 默认小（1/2/3 → 2/5/10）
_WIDTHS = (2, 5, 10)
# 马赛克色块：越小越密（用户反馈不够密集）
_MOSAIC_CELL_BY_WIDTH = {2: 4, 5: 6, 10: 10}
# 小/中/大三档字号（逻辑像素）；较上一版整体降一档
_FONT_BY_WIDTH = {2: 22, 5: 28, 10: 36}
_FONT_MIN = 16
_TEXT_EDIT_PAD = 2
_ANNOT_FONT_FAMILY = "Microsoft YaHei UI"
_SHOT_TEXT_EDIT_OBJECT = "ShotAnnotTextEdit"

_ICON = 28
_SUB_ICON = 20
_STYLE_ICON = 20
_BAR_H = 34
_SUB_H = 28
_ICON_DESIGN = 72
_HANDLE = 6
_HIT_PAD = 8
_SEL_BORDER = "#07C160"


def _screen_dpr(widget=None) -> float:
    """取控件所在屏 DPR；无控件时取主屏。禁止写死 2.0。"""
    scr = None
    if widget is not None:
        scr = widget.screen()
    if scr is None:
        scr = QGuiApplication.primaryScreen()
    if scr is not None:
        return max(1.0, float(scr.devicePixelRatio()))
    return 1.0


# ---------------------------------------------------------------------------
# 纯函数（无 GUI / 无显示器依赖）
# ---------------------------------------------------------------------------


def mosaic_params(width: int, *, dpr: float = 1.0) -> tuple[int, float]:
    """逻辑线宽 → (设备像素色块边长, 笔刷半径)。格点按 cell 对齐，保证均匀。"""
    w = int(width)
    # 只认档位键，避免 width×dpr 落在 map 外导致粒度漂移
    logical = int(w)
    if logical not in _MOSAIC_CELL_BY_WIDTH:
        # 就近档位
        logical = min(_WIDTHS, key=lambda x: abs(x - logical))
    cell_逻辑 = int(_MOSAIC_CELL_BY_WIDTH.get(logical, 10))
    scale = max(1.0, float(dpr) or 1.0)
    cell = max(2, int(round(cell_逻辑 * scale)))
    radius = cell * 1.35
    return cell, radius


def densify_points(
    points: list[tuple[float, float]], spacing: float = 2.0
) -> list[tuple[float, float]]:
    """折线插值，保证马赛克/画笔连续。"""
    if not points:
        return []
    if len(points) == 1:
        return list(points)
    out: list[tuple[float, float]] = [points[0]]
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist < 1e-6:
            continue
        steps = max(1, int(dist / max(0.5, spacing)))
        for s in range(1, steps + 1):
            t = s / steps
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def chaikin_smooth(
    points: list[tuple[float, float]], iterations: int = 2
) -> list[tuple[float, float]]:
    """Chaikin 切角：去掉折线棱角，手写更丝滑。"""
    if len(points) < 3 or iterations <= 0:
        return list(points)
    pts = list(points)
    for _ in range(int(iterations)):
        nxt: list[tuple[float, float]] = [pts[0]]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            nxt.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            nxt.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        nxt.append(pts[-1])
        pts = nxt
    return pts


def refine_pen_points(
    points: list[tuple[float, float]], *, spacing: float = 1.2
) -> list[tuple[float, float]]:
    """手写笔定稿：平滑后再密采样，导出与预览一致。"""
    if len(points) < 2:
        return list(points)
    return densify_points(chaikin_smooth(points, iterations=2), spacing=spacing)


def pen_painter_path(points: list[tuple[float, float]]) -> QPainterPath:
    """平滑折线 → QPainterPath（圆角连接由笔刷 RoundJoin 承接）。"""
    pts = chaikin_smooth(points, iterations=2) if len(points) >= 3 else list(points)
    path = QPainterPath()
    if not pts:
        return path
    path.moveTo(QPointF(pts[0][0], pts[0][1]))
    for i in range(1, len(pts)):
        path.lineTo(QPointF(pts[i][0], pts[i][1]))
    return path


def paint_pen_stroke(
    painter: QPainter,
    points: list[tuple[float, float]],
    *,
    color: QColor,
    width: int,
    smooth: bool = True,
) -> None:
    """绘制手写笔迹；smooth=True 时走 Chaikin 路径。"""
    if not points:
        return
    w = max(1, int(width))
    pen = QPen(
        color,
        w,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if len(points) == 1:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(points[0][0], points[0][1]), w / 2.0, w / 2.0)
        return
    if smooth and len(points) >= 3:
        painter.drawPath(pen_painter_path(points))
        return
    for i in range(1, len(points)):
        painter.drawLine(QPointF(*points[i - 1]), QPointF(*points[i]))


def arrow_geometry(
    x1: float, y1: float, x2: float, y2: float, width: int, style: str = "classic"
) -> tuple[Any, list[tuple[float, float]], list[tuple[float, float]] | None]:
    """返回 (shaft_end, head_pts, tail_pts|None)。"""
    style = style or "classic"
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return (x2, y2), [(x2, y2)], None
    ux, uy = dx / dist, dy / dist
    head_len = max(10.0, width * 3.4 + 4.0)
    if style == "stealth":
        head_len *= 1.12
        half_w = max(4.0, width * 1.55)
    elif style == "open":
        head_len = max(9.0, width * 3.0 + 3.0)
        half_w = max(4.0, width * 1.8)
    else:
        half_w = max(4.5, width * 1.85)
    tip_x, tip_y = float(x2), float(y2)
    root_x = tip_x - ux * head_len
    root_y = tip_y - uy * head_len
    px, py = -uy, ux
    if style == "stealth":
        inset = head_len * 0.28
        mid_x = tip_x - ux * inset
        mid_y = tip_y - uy * inset
        head = [
            (tip_x, tip_y),
            (root_x + px * half_w, root_y + py * half_w),
            (mid_x, mid_y),
            (root_x - px * half_w, root_y - py * half_w),
        ]
        shaft_end: Any = (mid_x, mid_y)
    elif style == "open":
        wing1 = (tip_x - ux * head_len + px * half_w, tip_y - uy * head_len + py * half_w)
        wing2 = (tip_x - ux * head_len - px * half_w, tip_y - uy * head_len - py * half_w)
        head = [(tip_x, tip_y), wing1, wing2]
        shaft_end = (tip_x, tip_y)
    else:
        head = [
            (tip_x, tip_y),
            (root_x + px * half_w, root_y + py * half_w),
            (root_x - px * half_w, root_y - py * half_w),
        ]
        shaft_end = (root_x, root_y)
    tail = None
    if style == "double":
        t_tip_x, t_tip_y = float(x1), float(y1)
        t_root_x = t_tip_x + ux * head_len
        t_root_y = t_tip_y + uy * head_len
        tail = [
            (t_tip_x, t_tip_y),
            (t_root_x + px * half_w, t_root_y + py * half_w),
            (t_root_x - px * half_w, t_root_y - py * half_w),
        ]
        return (shaft_end, (t_root_x, t_root_y)), head, tail
    return shaft_end, head, tail


def normalize_color(color: str | None, fallback: str = _DEFAULT_COLOR) -> str:
    c = (color or "").strip()
    if not c.startswith("#"):
        return fallback
    h = c[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return fallback
    try:
        int(h, 16)
    except ValueError:
        return fallback
    return f"#{h.upper()}"


def font_size_for_width(width: int) -> int:
    return int(_FONT_BY_WIDTH.get(int(width), 42))


def build_annot_text_font(
    size_px: int,
    *,
    bold: bool = False,
    italic: bool = False,
    strike: bool = False,
) -> QFont:
    """标注文字字体：输入框与画布绘制共用，保证 1:1 像素字号。"""
    font = QFont(_ANNOT_FONT_FAMILY)
    font.setPixelSize(max(_FONT_MIN, int(size_px)))
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    font.setStrikeOut(bool(strike))
    return font


def shot_text_edit_stylesheet(color: str, font: QFont) -> str:
    """文字输入框样式：显式 px 字号，覆盖全局 QLineEdit QSS，与画布 _paint_text 1:1。"""
    fs = int(font.pixelSize())
    if fs <= 0:
        fs = max(_FONT_MIN, int(round(font.pointSizeF() * 96.0 / 72.0)))
    weight = "700" if font.bold() else "400"
    italic = "italic" if font.italic() else "normal"
    strike = "line-through" if font.strikeOut() else "none"
    return f"""
        QLineEdit#{_SHOT_TEXT_EDIT_OBJECT} {{
            background: rgba(0,0,0,120);
            color: {normalize_color(color)};
            border: 1px dashed #8C8C8C;
            padding: {_TEXT_EDIT_PAD}px;
            min-height: 0px;
            font-family: "{_ANNOT_FONT_FAMILY}";
            font-size: {fs}px;
            font-weight: {weight};
            font-style: {italic};
            text-decoration: {strike};
            selection-background-color: rgba(255,255,255,40);
        }}
    """


def text_edit_chrome_stylesheet(color: str, font: QFont | None = None) -> str:
    """兼容旧调用；须传入 font 以保证字号一致。"""
    f = font or build_annot_text_font(_FONT_MIN)
    return shot_text_edit_stylesheet(color, f)


def text_edit_box_height(font: QFont) -> int:
    return QFontMetrics(font).height() + _TEXT_EDIT_PAD * 2


def text_paint_baseline(box_x: float, box_y: float, font: QFont) -> tuple[float, float]:
    """与 QLineEdit 左上角对齐时的绘制基线坐标。"""
    fm = QFontMetrics(font)
    return box_x + _TEXT_EDIT_PAD, box_y + _TEXT_EDIT_PAD + fm.ascent()


def style_icon_font_px(sub_icon: int = _STYLE_ICON) -> int:
    """B/I/S 绘制字号。"""
    return max(12, int(round(sub_icon * 0.55)))


def _paint_style_glyph(key: str, color: str = "#FFFFFF", logical: int = _STYLE_ICON) -> QPixmap:
    """QPainter 绘制 B/I/S，避免 QSS text-decoration 失效。"""
    dpr = _screen_dpr()
    phys = max(1, int(round(logical * dpr)))
    pm = QPixmap(phys, phys)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont("Segoe UI")
    font.setPixelSize(style_icon_font_px(logical))
    font.setBold(True)
    if key == "italic":
        font.setItalic(True)
    painter.setFont(font)
    painter.setPen(QColor(color))
    label = {"bold": "B", "italic": "I", "strike": "S"}.get(key, "?")
    rect = QRectF(0, 0, logical, logical)
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)
    if key == "strike":
        pen = QPen(QColor(color))
        pen.setWidth(max(2, logical // 18))
        painter.setPen(pen)
        y = logical * 0.52
        painter.drawLine(int(logical * 0.22), int(y), int(logical * 0.78), int(y))
    painter.end()
    return pm


def _paint_fill_glyph(
    color: str = "#FA5151", logical: int = _STYLE_ICON, *, filled: bool = True
) -> QPixmap:
    """副栏「填充色块」：圆角矩形描边 + 可选实心填充（勿画成小圆点）。"""
    dpr = _screen_dpr()
    phys = max(1, int(round(logical * dpr)))
    pm = QPixmap(phys, phys)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    k = logical / float(_STYLE_ICON)
    margin = 3.5 * k
    outer = QRectF(margin, margin, logical - 2 * margin, logical - 2 * margin)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#D0D0D0"))
    pen.setWidth(max(1, int(round(1.6 * k))))
    painter.setPen(pen)
    if filled:
        painter.setBrush(QColor(color))
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(outer, 3 * k, 3 * k)
    painter.end()
    return pm


def _paint_color_swatch(color: str, logical: int = _SUB_ICON) -> QPixmap:
    """副栏色点：物理像素实心圆 + 描边，HiDPI 清晰。"""
    dpr = _screen_dpr()
    phys = max(1, int(round(logical * dpr)))
    pm = QPixmap(phys, phys)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color)
    margin = max(1.5, logical * 0.12)
    r = (logical - 2 * margin) / 2
    center = QPointF(logical / 2, logical / 2)
    painter.setBrush(c)
    pen = QPen(QColor(255, 255, 255, 200))
    pen.setWidthF(max(1.0, logical * 0.08))
    painter.setPen(pen)
    painter.drawEllipse(center, r, r)
    painter.end()
    return pm


def _paint_width_glyph(kind: str, width: int, color: str, logical: int = _SUB_ICON) -> QPixmap:
    """线宽圆点 / 马赛克粒度格（副栏）。"""
    dpr = _screen_dpr()
    phys = max(1, int(round(logical * dpr)))
    pm = QPixmap(phys, phys)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color)
    if kind == "mosaic":
        cells = {2: 2, 5: 3, 10: 4}.get(int(width), 3)
        gap = max(1.0, logical * 0.06)
        cell = (logical - gap * (cells + 1)) / cells
        for r in range(cells):
            for col in range(cells):
                x = gap + col * (cell + gap)
                y = gap + r * (cell + gap)
                fill = c if (r + col) % 2 == 0 else QColor(38, 38, 38)
                painter.fillRect(QRectF(x, y, cell, cell), fill)
    elif kind == "shape_border":
        margin = logical * 0.16
        rect = QRectF(margin, margin, logical - 2 * margin, logical - 2 * margin)
        pen = QPen(c)
        pen.setWidthF(max(1.0, {2: 1.4, 5: 2.6, 10: 4.0}.get(int(width), 2.0) * (logical / 20.0)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 2.5, 2.5)
    else:
        r = {2: 0.18, 5: 0.28, 10: 0.38}.get(int(width), 0.28) * logical
        painter.setBrush(c)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(logical / 2, logical / 2), r, r)
    painter.end()
    return pm


def _paint_tool_glyph(key: str, color: str = "#FFFFFF", logical: int = _ICON) -> QPixmap:
    """主工具栏矢量图标（与 TOA2 wechat_screenshot _render_toolbar_icon 几何一致）。"""
    if key == "undo":
        return _paint_history_glyph(undo=True, color=color, logical=logical)
    if key == "redo":
        return _paint_history_glyph(undo=False, color=color, logical=logical)

    dpr = _screen_dpr()
    phys = max(1, int(round(logical * dpr)))
    pm = QPixmap(phys, phys)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    k = logical / float(_ICON_DESIGN)
    c = QColor(color)

    def xy(x: float, y: float) -> tuple[float, float]:
        return x * k, y * k

    def stroke(base: float = 3.0) -> int:
        return max(1, int(round(base * k)))

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    pen = QPen(c)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    if key == "rect":
        pen.setWidth(stroke(3))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x1, y1 = xy(20, 22)
        x2, y2 = xy(52, 50)
        painter.drawRoundedRect(QRectF(x1, y1, x2 - x1, y2 - y1), 2 * k, 2 * k)
    elif key == "ellipse":
        pen.setWidth(stroke(3))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x1, y1 = xy(20, 22)
        x2, y2 = xy(52, 50)
        painter.drawEllipse(QRectF(x1, y1, x2 - x1, y2 - y1))
    elif key == "arrow":
        pen.setWidth(stroke(3))
        painter.setPen(pen)
        painter.drawLine(QPointF(*xy(22, 48)), QPointF(*xy(48, 22)))
        painter.setBrush(c)
        painter.drawPolygon(
            QPolygonF([QPointF(*xy(48, 22)), QPointF(*xy(34, 24)), QPointF(*xy(46, 36))])
        )
    elif key == "pen":
        ax, ay = 22.0 * k, 52.0 * k
        dx, dy = 32.0 * k, -34.0 * k
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        px, py = -uy, ux
        body_len, tip_len, half = 26.0 * k, 14.0 * k, 6.5 * k
        bx, by = ax + ux * body_len, ay + uy * body_len
        tx, ty = ax + ux * (body_len + tip_len), ay + uy * (body_len + tip_len)
        pen.setWidth(stroke(6))
        painter.setPen(pen)
        painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
        painter.setBrush(c)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(tx, ty),
                    QPointF(bx + px * half, by + py * half),
                    QPointF(bx - px * half, by - py * half),
                ]
            )
        )
        pen.setWidth(stroke(3))
        painter.setPen(pen)
        painter.drawLine(QPointF(*xy(16, 56)), QPointF(*xy(28, 56)))
    elif key == "mosaic":
        side = 14.0 * k
        bg_c = QColor(_TOOL_BTN)
        for i, (x0, y0) in enumerate(((20, 20), (36, 20), (20, 36), (36, 36))):
            x0, y0 = xy(x0, y0)
            fill = c if i % 2 == 0 else bg_c
            pen.setWidth(stroke(2))
            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawRect(QRectF(x0, y0, side, side))
    elif key == "text":
        font = QFont("Segoe UI")
        font.setPixelSize(max(12, int(round(36 * k))))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(c)
        painter.drawText(QRectF(0, 0, logical, logical), int(Qt.AlignmentFlag.AlignCenter), "A")
    elif key == "ocr":
        # 文档框 + 扫描线：与「文字 A」区分
        pen.setWidth(stroke(2.5))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x1, y1 = xy(22, 16)
        x2, y2 = xy(50, 56)
        painter.drawRoundedRect(QRectF(x1, y1, x2 - x1, y2 - y1), 2 * k, 2 * k)
        for yy in (28, 36, 44):
            painter.drawLine(QPointF(*xy(28, yy)), QPointF(*xy(44, yy)))
        # 底部小扫描条
        painter.setBrush(c)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(*xy(24, 50), 24 * k, 4 * k), 1 * k, 1 * k)
    elif key == "translate":
        # 「文」+「A」并排，明确翻译而非文字工具
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(11, int(round(22 * k))))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(c)
        painter.drawText(
            QRectF(*xy(8, 18), 28 * k, 36 * k),
            int(Qt.AlignmentFlag.AlignCenter),
            "文",
        )
        font2 = QFont("Segoe UI")
        font2.setPixelSize(max(12, int(round(26 * k))))
        font2.setBold(True)
        painter.setFont(font2)
        painter.drawText(
            QRectF(*xy(34, 16), 30 * k, 40 * k),
            int(Qt.AlignmentFlag.AlignCenter),
            "A",
        )
        pen.setWidth(stroke(2))
        painter.setPen(pen)
        painter.drawLine(QPointF(*xy(34, 36)), QPointF(*xy(40, 36)))
    elif key == "pin":
        head = QColor("#FA5151")
        painter.setBrush(head)
        pen.setWidth(stroke(2))
        painter.setPen(pen)
        x1, y1 = xy(28, 14)
        x2, y2 = xy(48, 34)
        painter.drawEllipse(QRectF(x1, y1, x2 - x1, y2 - y1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        hx1, hy1 = xy(34, 20)
        hx2, hy2 = xy(42, 28)
        painter.drawEllipse(QRectF(hx1, hy1, hx2 - hx1, hy2 - hy1))
        pen.setColor(c)
        pen.setWidth(stroke(3.5))
        painter.setPen(pen)
        painter.drawLine(QPointF(*xy(38, 32)), QPointF(*xy(38, 54)))
        painter.drawLine(QPointF(*xy(30, 40)), QPointF(*xy(46, 40)))
    elif key == "save":
        pen.setWidth(stroke(3))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        sx1, sy1 = xy(24, 18)
        sx2, sy2 = xy(48, 28)
        painter.drawRect(QRectF(sx1, sy1, sx2 - sx1, sy2 - sy1))
        painter.drawLine(QPointF(*xy(36, 24)), QPointF(*xy(36, 50)))
        painter.drawLine(QPointF(*xy(26, 40)), QPointF(*xy(36, 52)))
        painter.drawLine(QPointF(*xy(46, 40)), QPointF(*xy(36, 52)))
    elif key == "ok":
        green = QColor(_WX_GREEN)
        painter.setBrush(green)
        painter.setPen(Qt.PenStyle.NoPen)
        ox1, oy1 = xy(14, 14)
        ox2, oy2 = xy(58, 58)
        painter.drawEllipse(QRectF(ox1, oy1, ox2 - ox1, oy2 - oy1))
        pen.setColor(QColor(255, 255, 255))
        pen.setWidth(stroke(4))
        painter.setPen(pen)
        painter.drawLine(QPointF(*xy(24, 36)), QPointF(*xy(32, 46)))
        painter.drawLine(QPointF(*xy(32, 46)), QPointF(*xy(50, 26)))
    elif key == "cancel":
        pen.setWidth(stroke(3.5))
        painter.setPen(pen)
        painter.drawLine(QPointF(*xy(24, 24)), QPointF(*xy(48, 48)))
        painter.drawLine(QPointF(*xy(48, 24)), QPointF(*xy(24, 48)))
    else:
        painter.setPen(c)
        painter.drawText(QRectF(0, 0, logical, logical), int(Qt.AlignmentFlag.AlignCenter), "?")

    painter.end()
    return pm


def _paint_history_glyph(*, undo: bool, color: str = "#FFFFFF", logical: int = _ICON) -> QPixmap:
    """撤销 / 重做弧形箭头。"""
    dpr = _screen_dpr()
    phys = max(1, int(round(logical * dpr)))
    pm = QPixmap(phys, phys)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)

    k = logical / float(_ICON_DESIGN)
    cx, cy, r = 36.0 * k, 37.0 * k, 15.5 * k
    ah, aw = 11.0 * k, 6.8 * k
    if undo:
        a0, a1, step = 40.0, 200.0, 1.5
        tip_dir = (-1.0, 0.15)
    else:
        a0, a1, step = 140.0, -20.0, -1.5
        tip_dir = (1.0, 0.15)
    dang = math.degrees(ah / max(r, 1e-6)) * 0.75
    arc_end = (a1 - dang) if undo else (a1 + dang)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.8, 3.5 * k))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    pts: list[QPointF] = []
    ang = a0
    for _ in range(260):
        rad = math.radians(ang)
        pts.append(QPointF(cx + r * math.cos(rad), cy - r * math.sin(rad)))
        if undo:
            if ang >= arc_end:
                break
            ang = min(ang + step, arc_end)
        else:
            if ang <= arc_end:
                break
            ang = max(ang + step, arc_end)
    if len(pts) >= 2:
        path = QPainterPath(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        painter.drawPath(path)

    a_tip = math.radians(a1)
    tip_x = cx + r * math.cos(a_tip)
    tip_y = cy - r * math.sin(a_tip)
    tx, ty = tip_dir
    tn = math.hypot(tx, ty) or 1.0
    tx, ty = tx / tn, ty / tn
    tip_x += tx * 2.0 * k
    tip_y += ty * 2.0 * k
    bx, by = tip_x - tx * ah, tip_y - ty * ah
    px, py = -ty, tx
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(
        QPolygonF(
            [
                QPointF(tip_x, tip_y),
                QPointF(bx + px * aw, by + py * aw),
                QPointF(bx - px * aw, by - py * aw),
            ]
        )
    )
    painter.end()
    return pm


def iter_brush_cells(x: float, y: float, radius: float, cell: int):
    r2 = radius * radius
    x0 = int(math.floor((x - radius) / cell)) * cell
    y0 = int(math.floor((y - radius) / cell)) * cell
    x1 = int(math.ceil((x + radius) / cell)) * cell + cell
    y1 = int(math.ceil((y + radius) / cell)) * cell + cell
    half = cell * 0.5
    for by in range(y0, y1, cell):
        for bx in range(x0, x1, cell):
            if (bx + half - x) ** 2 + (by + half - y) ** 2 <= r2:
                yield bx, by


def pixelate_rect(img: QImage, rect: QRect, cell: int) -> None:
    """就地像素化矩形区域（需 Format_ARGB32 类可写图）。"""
    if img.isNull() or cell < 2:
        return
    r = rect.intersected(img.rect())
    if r.width() < 2 or r.height() < 2:
        return
    x0, y0, x1, y1 = r.left(), r.top(), r.right() + 1, r.bottom() + 1
    for y in range(y0, y1, cell):
        for x in range(x0, x1, cell):
            w = min(cell, x1 - x)
            h = min(cell, y1 - y)
            if w <= 0 or h <= 0:
                continue
            # 采样中心色
            sx = min(img.width() - 1, x + w // 2)
            sy = min(img.height() - 1, y + h // 2)
            color = img.pixelColor(sx, sy)
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    img.setPixelColor(xx, yy, color)


def apply_mosaic_stroke(
    img: QImage,
    points: list[tuple[float, float]],
    width: int,
    *,
    dpr: float = 1.0,
    seen: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """沿路径像素化；格点对齐 cell 网格，所见与导出一致。"""
    cell, radius = mosaic_params(width, dpr=dpr)
    densified = densify_points(points, spacing=max(1.0, cell * 0.28))
    if seen is None:
        seen = set()
    for x, y in densified:
        for bx, by in iter_brush_cells(x, y, radius, cell):
            key = (bx, by)
            if key in seen:
                continue
            seen.add(key)
            pixelate_rect(img, QRect(bx, by, cell, cell), cell)
    return seen


# ---------------------------------------------------------------------------
# 标注数据
# ---------------------------------------------------------------------------


@dataclass
class AnnotStyle:
    color: str = _DEFAULT_COLOR
    width: int = _DEFAULT_WIDTH
    filled: bool = False
    bold: bool = False
    italic: bool = False
    strike: bool = False

    @property
    def font_size(self) -> int:
        return max(_FONT_MIN, font_size_for_width(self.width))


@dataclass
class AnnotSession:
    annots: list[dict[str, Any]] = field(default_factory=list)
    redo: list[dict[str, Any]] = field(default_factory=list)

    def push(self, a: dict[str, Any]) -> None:
        self.annots.append(a)
        self.redo.clear()

    def undo(self) -> bool:
        if not self.annots:
            return False
        self.redo.append(self.annots.pop())
        return True

    def redo_one(self) -> bool:
        if not self.redo:
            return False
        self.annots.append(self.redo.pop())
        return True


def compose_annotated_pixmap(base: QPixmap, annots: list[dict[str, Any]]) -> QPixmap:
    """把标注按绘制顺序叠到 base 上，返回新 pixmap（保留 devicePixelRatio）。

    标注坐标一律为逻辑像素（与覆盖层鼠标坐标一致）；马赛克位操作换算到设备像素。
    """
    if base.isNull():
        return QPixmap()
    dpr = float(base.devicePixelRatio() or 1.0)
    img = base.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    out = QPixmap.fromImage(img)
    out.setDevicePixelRatio(dpr)
    painter: QPainter | None = None

    def _flush() -> None:
        nonlocal painter, img, out
        if painter is not None:
            painter.end()
            painter = None
            img = out.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    def _ensure() -> QPainter:
        nonlocal painter, out
        if painter is None:
            out = QPixmap.fromImage(img)
            out.setDevicePixelRatio(dpr)
            painter = QPainter(out)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        return painter

    def _dev_pt(x: float, y: float) -> tuple[float, float]:
        return float(x) * dpr, float(y) * dpr

    for a in annots:
        t = a.get("type")
        if t == "mosaic":
            _flush()
            pts = [(float(p[0]), float(p[1])) for p in (a.get("points") or [])]
            logical_w = int(a.get("width") or _DEFAULT_WIDTH)
            if pts:
                pts_dev = [_dev_pt(x, y) for x, y in pts]
                apply_mosaic_stroke(img, pts_dev, logical_w, dpr=dpr)
            elif a.get("x1") is not None:
                cell, _ = mosaic_params(logical_w, dpr=dpr)
                x1, y1 = _dev_pt(a["x1"], a["y1"])
                x2, y2 = _dev_pt(a["x2"], a["y2"])
                r = QRect(
                    int(min(x1, x2)),
                    int(min(y1, y2)),
                    max(1, int(abs(x2 - x1))),
                    max(1, int(abs(y2 - y1))),
                )
                pixelate_rect(img, r, cell)
            continue
        p = _ensure()
        color = QColor(normalize_color(a.get("color")))
        w = max(1, int(a.get("width") or _DEFAULT_WIDTH))
        if t in ("rect", "ellipse"):
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
        elif t == "pen":
            pts = a.get("points") or []
            paint_pen_stroke(
                p,
                [(float(pt[0]), float(pt[1])) for pt in pts],
                color=color,
                width=w,
                smooth=True,
            )
        elif t == "text":
            _paint_text(p, a)
    _flush()
    result = QPixmap.fromImage(img)
    result.setDevicePixelRatio(dpr)
    return result


def crop_logical(pix: QPixmap, logical_rect: QRect) -> QPixmap:
    """按逻辑选区裁剪；导出图 devicePixelRatio=1（物理像素，便于粘贴）。"""
    if pix.isNull() or not logical_rect.isValid():
        return QPixmap()
    dpr = float(pix.devicePixelRatio() or 1.0)
    if abs(dpr - 1.0) < 1e-6:
        return pix.copy(logical_rect)
    pr = QRect(
        int(round(logical_rect.x() * dpr)),
        int(round(logical_rect.y() * dpr)),
        max(1, int(round(logical_rect.width() * dpr))),
        max(1, int(round(logical_rect.height() * dpr))),
    )
    out = pix.copy(pr)
    out.setDevicePixelRatio(1.0)
    return out


def _paint_shape_box(
    p: QPainter,
    shape: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: QColor,
    width: int,
    *,
    filled: bool = False,
) -> None:
    rect = QRectF(x1, y1, x2 - x1, y2 - y1).normalized()
    pen = QPen(color, width, Qt.PenStyle.SolidLine)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if filled:
        p.setPen(pen)
        p.setBrush(color)
    else:
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
    if shape == "ellipse":
        p.drawEllipse(rect)
    else:
        p.drawRect(rect)


def _paint_arrow(p: QPainter, x1, y1, x2, y2, color: QColor, width: int) -> None:
    shaft_end, head, _tail = arrow_geometry(x1, y1, x2, y2, width, "classic")
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(color)
    if isinstance(shaft_end, tuple) and len(shaft_end) == 2 and not isinstance(shaft_end[0], tuple):
        p.drawLine(QPointF(x1, y1), QPointF(shaft_end[0], shaft_end[1]))
    poly = QPolygonF([QPointF(pt[0], pt[1]) for pt in head])
    p.drawPolygon(poly)


def _paint_text(p: QPainter, a: dict[str, Any]) -> None:
    text = str(a.get("text") or "")
    if not text:
        return
    color = QColor(normalize_color(a.get("color")))
    size = max(_FONT_MIN, int(a.get("size") or _FONT_MIN))
    font = build_annot_text_font(
        size,
        bold=bool(a.get("bold")),
        italic=bool(a.get("italic")),
        strike=bool(a.get("strike")),
    )
    p.setFont(font)
    p.setPen(color)
    bx, by = text_paint_baseline(float(a.get("x", 0)), float(a.get("y", 0)), font)
    p.drawText(QPointF(bx, by), text)


# ---------------------------------------------------------------------------
# 工具栏按钮（深色 chrome）
# ---------------------------------------------------------------------------


class _ToolBtn(QPushButton):
    def __init__(
        self,
        text: str = "",
        tip: str = "",
        *,
        icon_key: str | None = None,
        checkable: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setCheckable(checkable)
        self.setToolTip(tip)
        self.setFixedSize(_ICON, _ICON)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 不抢焦点，保证 1/2/3、R/P 等快捷键始终落到截图层
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if icon_key:
            self.setText("")
            # 物理像素位图 + 逻辑尺寸一致，避免再缩小导致锯齿
            self.setIcon(QIcon(_paint_tool_glyph(icon_key)))
            self.setIconSize(QSize(_ICON, _ICON))
        else:
            self.setText(text)
        # 覆盖全局 QPushButton 的 min-height/padding，避免工具栏按钮被撑高
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {_TOOL_BTN};
                color: {_TOOL_FG};
                border: 1px solid {_TOOL_BORDER};
                border-radius: 5px;
                font-size: 11px;
                font-weight: 600;
                min-width: {_ICON}px;
                max-width: {_ICON}px;
                min-height: {_ICON}px;
                max-height: {_ICON}px;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{ background: {_TOOL_BTN_HOVER}; }}
            QPushButton:checked {{
                background: {_TOOL_BTN_ACTIVE};
                color: #FFFFFF;
                border-color: {_WX_GREEN};
            }}
            QPushButton:disabled {{ color: #777777; }}
            """
        )


class _SubSwatch(QPushButton):
    """副栏色块 / 粗细 / B·I·S。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(_SUB_ICON, _SUB_ICON)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kind = "color"
        self._color = _DEFAULT_COLOR
        self._label = ""
        self._style_key = ""
        self._apply_chrome(False)

    def configure_color(self, color: str) -> None:
        self._kind = "color"
        self._color = normalize_color(color)
        self.setText("")
        # HiDPI 实心圆，避免 CSS 径向渐变在小按钮上发糊
        self.setIcon(QIcon(_paint_color_swatch(self._color, _SUB_ICON)))
        self.setIconSize(QSize(_SUB_ICON, _SUB_ICON))
        self._repaint_look()

    def configure_width(self, width: int, *, mosaic: bool = False, filled_shape: bool = False) -> None:
        self._kind = "width"
        self._width_val = width
        self._mosaic = mosaic
        idx = {2: 1, 5: 2, 10: 3}.get(width)
        if mosaic:
            tip = f"马赛克粒度 · 档 {idx or '?'}（快捷键 {idx}）"
        elif filled_shape:
            tip = f"色块边线 · 档 {idx or '?'}（快捷键 {idx}，矩形/圆形填充均生效）"
        else:
            tip = (
                f"线宽/字号 · 档 {idx or '?'} "
                f"（快捷键 {idx}，矩形/椭圆/箭头/画笔/马赛克/文字均生效）"
            )
        self.setToolTip(tip)
        # 矢量点 / 马赛克格 / 填充边线，禁止用 ▦ 等系统字形（HiDPI 下锯齿）
        if mosaic:
            glyph = "mosaic"
            icon_color = "#FA5151"
        elif filled_shape:
            glyph = "shape_border"
            icon_color = _DEFAULT_COLOR
        else:
            glyph = "width_dot"
            icon_color = _DEFAULT_COLOR
        self.setText("")
        self.setIcon(QIcon(_paint_width_glyph(glyph, width, icon_color)))
        self.setIconSize(QSize(_SUB_ICON, _SUB_ICON))
        self.setStyleSheet(self._base_qss())
        self._repaint_look()

    def configure_style(self, key: str, label: str) -> None:
        self._kind = "style"
        self._style_key = key
        self._label = label
        self.setFixedSize(_STYLE_ICON, _STYLE_ICON)
        self.setText("")
        self.setIcon(QIcon(_paint_style_glyph(key, "#FFFFFF", _STYLE_ICON)))
        self.setIconSize(QSize(_STYLE_ICON, _STYLE_ICON))
        self.setStyleSheet(self._base_qss())
        self._repaint_look()

    def configure_fill(self) -> None:
        self._kind = "fill"
        self.setFixedSize(_STYLE_ICON, _STYLE_ICON)
        self.setText("")
        self.setToolTip("填充色块（矩形/圆形 · F）")
        self._refresh_fill_icon()
        self.setIconSize(QSize(_STYLE_ICON, _STYLE_ICON))
        self.setStyleSheet(self._base_qss())
        self._repaint_look()

    def _refresh_fill_icon(self) -> None:
        if self._kind != "fill":
            return
        self.setIcon(
            QIcon(_paint_fill_glyph("#FA5151", _STYLE_ICON, filled=self.isChecked()))
        )

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        if self._kind == "fill":
            self._refresh_fill_icon()

    def _base_qss(self) -> str:
        return f"""
            QPushButton {{
                background: #262626;
                color: #A0A0A0;
                border: 1px solid transparent;
                border-radius: 4px;
                min-width: {_SUB_ICON}px;
                max-width: {_SUB_ICON}px;
                min-height: {_SUB_ICON}px;
                max-height: {_SUB_ICON}px;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{ background: {_TOOL_BTN_HOVER}; }}
            QPushButton:checked {{
                background: {_TOOL_BTN_HOVER};
                color: #FFFFFF;
                border: 1px solid {_WX_GREEN};
            }}
        """

    def _apply_chrome(self, _on: bool) -> None:
        self.setStyleSheet(self._base_qss())

    def _repaint_look(self) -> None:
        if self._kind == "color":
            # 选中态用白环，未选中淡边；图标已是 HiDPI 圆
            self.setStyleSheet(
                self._base_qss()
                + f"""
                QPushButton {{
                    background: #262626;
                    border-radius: {_SUB_ICON // 2}px;
                    border: 1px solid #555555;
                }}
                QPushButton:checked {{
                    border: 2px solid #FFFFFF;
                    background: #333333;
                }}
                """
            )


# ---------------------------------------------------------------------------
# 画布
# ---------------------------------------------------------------------------


class AnnotateCanvas(QWidget):
    """显示底图 + 实时预览；坐标为图像像素。"""

    request_commit_text = Signal()

    def __init__(self, base: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self._base = base
        self._session = AnnotSession()
        self._mode = "rect"
        self._style = AnnotStyle()
        self._dragging = False
        self._origin = QPointF()
        self._current = QPointF()
        self._pen_points: list[tuple[float, float]] = []
        self._shift = False
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._preview: dict[str, Any] | None = None
        self._text_edit: QLineEdit | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(120, 80)
        self._fit()

    @property
    def session(self) -> AnnotSession:
        return self._session

    @property
    def style(self) -> AnnotStyle:
        return self._style

    def set_mode(self, mode: str) -> None:
        self._commit_text_if_any()
        self._mode = mode
        cursors = {
            "pen": Qt.CursorShape.CrossCursor,
            "mosaic": Qt.CursorShape.CrossCursor,
            "text": Qt.CursorShape.IBeamCursor,
        }
        self.setCursor(cursors.get(mode, Qt.CursorShape.CrossCursor))
        self.update()

    def set_style(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._style, k):
                setattr(self._style, k, v)
        if self._text_edit is not None:
            self._sync_text_edit_style()
        self.update()

    def undo(self) -> None:
        self._commit_text_if_any()
        if self._session.undo():
            self.update()

    def redo(self) -> None:
        self._commit_text_if_any()
        if self._session.redo_one():
            self.update()

    def result_pixmap(self) -> QPixmap:
        self._commit_text_if_any()
        return compose_annotated_pixmap(self._base, self._session.annots)

    def _fit(self) -> None:
        screen = QGuiApplication.primaryScreen()
        max_w, max_h = 1200, 800
        if screen is not None:
            g = screen.availableGeometry()
            max_w = max(400, int(g.width() * 0.92))
            max_h = max(300, int(g.height() * 0.78))
        bw, bh = self._base.width(), self._base.height()
        if bw < 1 or bh < 1:
            self._scale = 1.0
            return
        self._scale = min(1.0, max_w / bw, max_h / bh)
        self.setFixedSize(int(bw * self._scale), int(bh * self._scale))

    def _to_img(self, pos: QPointF) -> QPointF:
        return QPointF(pos.x() / self._scale, pos.y() / self._scale)

    def _constrain(self, o: QPointF, c: QPointF) -> QPointF:
        if not self._shift:
            return c
        dx, dy = c.x() - o.x(), c.y() - o.y()
        m = max(abs(dx), abs(dy))
        return QPointF(o.x() + math.copysign(m, dx or 1), o.y() + math.copysign(m, dy or 1))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        annots = list(self._session.annots)
        preview_mosaic = bool(self._preview and self._preview.get("type") == "mosaic")
        if preview_mosaic:
            annots = annots + [self._preview]
        composed = compose_annotated_pixmap(self._base, annots)
        target = QRectF(0, 0, self.width(), self.height())
        painter.drawPixmap(target.toRect(), composed)
        if self._preview and not preview_mosaic:
            painter.save()
            painter.scale(self._scale, self._scale)
            self._paint_preview(painter, self._preview)
            painter.restore()

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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        img_pt = self._to_img(event.position())
        if self._mode == "text":
            self._begin_text(img_pt)
            return
        self._dragging = True
        self._origin = img_pt
        self._current = img_pt
        self._pen_points = [(img_pt.x(), img_pt.y())]
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._mode in ("pen", "mosaic") and not (
            self._mode == "mosaic" and self._shift
        ):
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
                "x1": img_pt.x(),
                "y1": img_pt.y(),
                "x2": img_pt.x(),
                "y2": img_pt.y(),
                "color": self._style.color,
                "width": self._style.width,
                "filled": bool(self._style.filled and typ in ("rect", "ellipse")),
            }
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        img_pt = self._to_img(event.position())
        if self._mode in ("pen", "mosaic") and not (
            self._mode == "mosaic" and self._shift
        ):
            x, y = img_pt.x(), img_pt.y()
            if self._pen_points:
                lx, ly = self._pen_points[-1]
                # 过密采样会抖出小棱角；过稀则靠平滑补
                if math.hypot(x - lx, y - ly) < 1.6:
                    return
            self._pen_points.append((x, y))
            if self._preview:
                self._preview["points"] = list(self._pen_points)
        else:
            c = self._constrain(self._origin, img_pt)
            self._current = c
            if self._preview:
                self._preview["x2"] = c.x()
                self._preview["y2"] = c.y()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        img_pt = self._to_img(event.position())
        self._shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        a = self._finalize_stroke(img_pt)
        self._preview = None
        if a is not None:
            self._session.push(a)
        self.update()

    def _finalize_stroke(self, img_pt: QPointF) -> dict[str, Any] | None:
        st = self._style
        if self._mode in ("pen", "mosaic") and not (self._mode == "mosaic" and self._shift):
            self._pen_points.append((img_pt.x(), img_pt.y()))
            if self._mode == "pen":
                pts = refine_pen_points(self._pen_points)
            else:
                pts = densify_points(self._pen_points, spacing=2.0)
            if len(pts) < 1:
                return None
            return {
                "type": self._mode,
                "points": pts,
                "color": st.color,
                "width": st.width,
            }
        c = self._constrain(self._origin, img_pt)
        x1, y1, x2, y2 = self._origin.x(), self._origin.y(), c.x(), c.y()
        if abs(x2 - x1) < 3 and abs(y2 - y1) < 3:
            return None
        if self._mode == "mosaic" and self._shift:
            return {
                "type": "mosaic",
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": st.width,
            }
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

    def _begin_text(self, img_pt: QPointF) -> None:
        self._commit_text_if_any()
        edit = QLineEdit(self)
        edit.setObjectName(_SHOT_TEXT_EDIT_OBJECT)
        self._text_edit = edit
        edit.setPlaceholderText("输入文字，Enter 确认")
        edit._img_origin = img_pt  # type: ignore[attr-defined]
        self._sync_text_edit_style()
        edit.resize(max(160, int(220 * self._scale)), edit.height())
        edit.move(int(img_pt.x() * self._scale), int(img_pt.y() * self._scale))
        edit.returnPressed.connect(self._commit_text_if_any)
        edit.editingFinished.connect(self._on_text_editing_finished)
        edit.show()
        edit.setFocus()

    def _sync_text_edit_style(self) -> None:
        if self._text_edit is None:
            return
        st = self._style
        font = build_annot_text_font(
            int(st.font_size * self._scale),
            bold=st.bold,
            italic=st.italic,
            strike=st.strike,
        )
        self._text_edit.setFont(font)
        self._text_edit.setStyleSheet(shot_text_edit_stylesheet(st.color, font))
        self._text_edit.setFixedHeight(text_edit_box_height(font))

    def _on_text_editing_finished(self) -> None:
        # 失焦时提交（避免与 returnPressed 双触发：用空文本判断）
        self._commit_text_if_any()

    def _commit_text_if_any(self) -> None:
        edit = self._text_edit
        if edit is None:
            return
        text = edit.text().strip()
        origin = getattr(edit, "_img_origin", QPointF(0, 0))
        edit.hide()
        edit.deleteLater()
        self._text_edit = None
        if not text:
            return
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


# ---------------------------------------------------------------------------
# 标注窗
# ---------------------------------------------------------------------------


class AnnotateOverlay(QWidget):
    """无边框标注窗：底图 + 主工具栏 + 副栏。"""

    finished_ok = Signal(object)  # Path | None
    finished_cancel = Signal()

    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        # 控件库例外：截图全屏标注层
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(f"AnnotateOverlay {{ background: #1A1A1A; }}")
        self._result_path: Path | None = None
        self._accepted = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._canvas = AnnotateCanvas(pixmap, self)
        root.addWidget(self._canvas, 0, Qt.AlignmentFlag.AlignCenter)

        # 主工具栏
        self._bar = QWidget(self)
        self._bar.setFixedHeight(_BAR_H)
        self._bar.setStyleSheet(
            f"QWidget {{ background: {_TOOL_BG}; border-radius: 10px; border: 1px solid {_TOOL_BORDER}; }}"
        )
        bar_l = QHBoxLayout(self._bar)
        bar_l.setContentsMargins(8, 6, 8, 6)
        bar_l.setSpacing(4)

        self._tool_btns: dict[str, _ToolBtn] = {}
        tools = [
            ("rect", "矩形 (R)"),
            ("ellipse", "椭圆 (C)"),
            ("arrow", "箭头 (A)"),
            ("pen", "画笔 (P)"),
            ("mosaic", "马赛克 (M) · Shift=矩形"),
            ("text", "文字 (T)"),
        ]
        for key, tip in tools:
            btn = _ToolBtn(tip=tip, icon_key=key, checkable=True, parent=self._bar)
            btn.clicked.connect(lambda checked=False, k=key: self._select_tool(k))
            bar_l.addWidget(btn)
            self._tool_btns[key] = btn

        bar_l.addSpacing(8)
        self._btn_undo = _ToolBtn(tip="撤销 (Ctrl+Z)", icon_key="undo", parent=self._bar)
        self._btn_undo.clicked.connect(self._canvas.undo)
        bar_l.addWidget(self._btn_undo)
        self._btn_redo = _ToolBtn(tip="重做 (Ctrl+Y)", icon_key="redo", parent=self._bar)
        self._btn_redo.clicked.connect(self._canvas.redo)
        bar_l.addWidget(self._btn_redo)

        bar_l.addStretch(1)
        self._btn_ok = _ToolBtn(tip="完成并复制 (Enter)", icon_key="ok", parent=self._bar)
        self._btn_ok.setStyleSheet(
            self._btn_ok.styleSheet()
            + f"QPushButton {{ background: {_WX_GREEN}; border-color: {_WX_GREEN}; }}"
        )
        self._btn_ok.clicked.connect(self._on_ok)
        bar_l.addWidget(self._btn_ok)
        self._btn_cancel = _ToolBtn(tip="取消 (Esc)", icon_key="cancel", parent=self._bar)
        self._btn_cancel.clicked.connect(self._on_cancel)
        bar_l.addWidget(self._btn_cancel)

        root.addWidget(self._bar, 0, Qt.AlignmentFlag.AlignHCenter)

        # 副栏
        self._sub = QWidget(self)
        self._sub.setFixedHeight(_SUB_H)
        self._sub.setStyleSheet(
            "QWidget { background: #262626; border-radius: 10px; border: 1px solid #333; }"
        )
        self._sub_l = QHBoxLayout(self._sub)
        self._sub_l.setContentsMargins(8, 6, 8, 6)
        self._sub_l.setSpacing(4)
        root.addWidget(self._sub, 0, Qt.AlignmentFlag.AlignHCenter)

        hint = QLabel(
            "R/C/A/P/M/T 工具 · S 重选 · F 填充 · 1/2/3 细中粗 · Shift 正方形/矩形马赛克 · Enter 完成",
            self,
        )
        hint.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        root.addWidget(hint, 0, Qt.AlignmentFlag.AlignHCenter)

        self._color_btns: list[_SubSwatch] = []
        self._width_btns: dict[int, _SubSwatch] = {}
        self._style_btns: dict[str, _SubSwatch] = {}
        self._rebuild_subbar()
        self._select_tool("rect")

        for seq, slot in (
            ("Ctrl+Z", self._canvas.undo),
            ("Ctrl+Y", self._canvas.redo),
            ("Ctrl+Shift+Z", self._canvas.redo),
            ("Return", self._on_ok),
            ("Enter", self._on_ok),
            ("Esc", self._on_cancel),
            ("R", lambda: self._select_tool("rect")),
            ("C", lambda: self._select_tool("ellipse")),
            ("A", lambda: self._select_tool("arrow")),
            ("P", lambda: self._select_tool("pen")),
            ("M", lambda: self._select_tool("mosaic")),
            ("T", lambda: self._select_tool("text")),
            ("F", self._hotkey_fill),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            if seq == "Esc":
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            else:
                sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)

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

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.adjustSize()
        self._center_on_screen()

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride) and self.isVisible():
            if event.key() == Qt.Key.Key_Escape:
                event.accept()
                if et == QEvent.Type.KeyPress:
                    self._on_cancel()
                return True
            if self._try_width_key(event):
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _try_width_key(self, event) -> bool:
        """1/2/3 对全部标注工具改细/中/粗（含文字字号）。"""
        width_map = {
            Qt.Key.Key_1: 0,
            Qt.Key.Key_2: 1,
            Qt.Key.Key_3: 2,
            Qt.Key.Key_Keypad1: 0,
            Qt.Key.Key_Keypad2: 1,
            Qt.Key.Key_Keypad3: 2,
        }
        key = event.key()
        if key not in width_map:
            return False
        mods = event.modifiers()
        if mods & (
            Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
            | Qt.KeyboardModifier.ShiftModifier
        ):
            return False
        self._pick_width_hotkey(width_map[key], force=True)
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
            event.accept()
            return
        if self._try_width_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def _center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        g = screen.availableGeometry()
        self.adjustSize()
        geo = self.frameGeometry()
        geo.moveCenter(g.center())
        self.move(geo.topLeft())

    def _select_tool(self, mode: str) -> None:
        self._canvas.set_mode(mode)
        for k, btn in self._tool_btns.items():
            btn.setChecked(k == mode)
        self._rebuild_subbar()
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _rebuild_subbar(self) -> None:
        while self._sub_l.count():
            item = self._sub_l.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._color_btns.clear()
        self._width_btns.clear()
        self._style_btns.clear()

        mode = self._canvas._mode
        need = mode in ("rect", "ellipse", "arrow", "pen", "mosaic", "text")
        self._sub.setVisible(need)
        if not need:
            return

        st = self._canvas.style
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
                mosaic=(mode == "mosaic"),
                filled_shape=(mode in ("rect", "ellipse") and st.filled),
            )
            btn.setChecked(w == st.width)
            btn.clicked.connect(lambda _=False, ww=w: self._pick_width(ww))
            self._sub_l.addWidget(btn)
            self._width_btns[w] = btn

        if mode in ("rect", "ellipse"):
            sep_fill = QLabel("|", self._sub)
            sep_fill.setStyleSheet("color: #555; background: transparent; border: none; font-size: 18px;")
            self._sub_l.addWidget(sep_fill)
            fill_btn = _SubSwatch(self._sub)
            fill_btn.configure_fill()
            fill_btn.setChecked(bool(st.filled))
            fill_btn.clicked.connect(lambda _=False: self._toggle_filled())
            self._sub_l.addWidget(fill_btn)
            self._style_btns["filled"] = fill_btn

        if mode == "text":
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

    def _pick_color(self, color: str) -> None:
        self._canvas.set_style(color=normalize_color(color))
        for btn in self._color_btns:
            btn.setChecked(normalize_color(btn._color) == normalize_color(color))

    def _pick_width(self, width: int) -> None:
        """细/中/粗：矩形/椭圆/箭头/画笔/马赛克/文字字号共用。"""
        self._canvas.set_style(width=int(width))
        for w, btn in list(self._width_btns.items()):
            btn.setChecked(w == width)
        preview = getattr(self._canvas, "_preview", None)
        if isinstance(preview, dict):
            preview["width"] = int(width)
            self._canvas.update()
        if self._canvas._text_edit is not None:
            self._canvas._sync_text_edit_style()

    def _pick_width_hotkey(self, index: int, *, force: bool = False) -> None:
        """1/2/3 → 细/中/粗，全部标注工具。"""
        edit = self._canvas._text_edit
        if not force and edit is not None and edit.hasFocus():
            return
        if 0 <= index < len(_WIDTHS):
            self._pick_width(_WIDTHS[index])

    def _toggle_filled(self) -> None:
        st = self._canvas.style
        self._canvas.set_style(filled=not st.filled)
        btn = self._style_btns.get("filled")
        if btn is not None:
            btn.setChecked(self._canvas.style.filled)
        preview = getattr(self._canvas, "_preview", None)
        if isinstance(preview, dict) and preview.get("type") in ("rect", "ellipse"):
            preview["filled"] = self._canvas.style.filled
            self._canvas.update()
        self._rebuild_subbar()

    def _hotkey_fill(self) -> None:
        if self._canvas._text_edit is not None and self._canvas._text_edit.hasFocus():
            return
        if self._canvas._mode not in ("rect", "ellipse"):
            return
        self._toggle_filled()

    def _toggle_style(self, key: str) -> None:
        st = self._canvas.style
        cur = bool(getattr(st, key, False))
        self._canvas.set_style(**{key: not cur})
        btn = self._style_btns.get(key)
        if btn is not None:
            btn.setChecked(not cur)
        if self._canvas._text_edit is not None:
            self._canvas._sync_text_edit_style()

    def _on_ok(self) -> None:
        # 文字输入中：Enter 只提交文字，不直接完成
        if self._canvas._text_edit is not None and self._canvas._text_edit.hasFocus():
            self._canvas._commit_text_if_any()
            return
        pix = self._canvas.result_pixmap()
        if pix.isNull():
            self._on_cancel()
            return
        path = _save_annotated(pix)
        try:
            QGuiApplication.clipboard().setPixmap(pix)
        except Exception:
            logger.debug("clipboard failed", exc_info=True)
        try:
            from services.screenshot_history import record_screenshot

            record_screenshot(path, source="annotate")
        except Exception:
            logger.debug("history record failed", exc_info=True)
        try:
            from services.notify_bus import NotifyLevel, notify

            notify(
                NotifyLevel.SUCCESS,
                title="截图已保存",
                body=str(path),
                channel="status",
            )
        except Exception:
            logger.debug("notify failed", exc_info=True)
        self._result_path = path
        self._accepted = True
        self.finished_ok.emit(path)
        self._remove_width_filter()
        self.close()

    def _on_cancel(self) -> None:
        if self._canvas._text_edit is not None:
            edit = self._canvas._text_edit
            self._canvas._text_edit = None
            edit.hide()
            edit.deleteLater()
            self._canvas.update()
            return
        self._result_path = None
        self._accepted = False
        self.finished_cancel.emit()
        self._remove_width_filter()
        self.close()

    def _remove_width_filter(self) -> None:
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self._remove_width_filter()
        super().closeEvent(event)

    @property
    def result_path(self) -> Path | None:
        return self._result_path if self._accepted else None


def _save_annotated(pix: QPixmap, module_id: str = "screenshot") -> Path:
    out_dir = module_output_dir(module_id, create=True)
    name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = out_dir / name
    if path.exists():
        name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S_%f.png")
        path = out_dir / name
    pix.save(str(path), "PNG")
    return path


def open_annotate(pixmap: QPixmap, parent=None) -> Path | None:
    """打开标注层（模态事件循环）；确认返回保存路径，取消返回 None。"""
    if pixmap is None or pixmap.isNull():
        return None
    held: list[Path | None] = [None]

    def _ok(path: object) -> None:
        held[0] = path if isinstance(path, Path) else None

    overlay = AnnotateOverlay(pixmap, parent=None)
    overlay.finished_ok.connect(_ok)
    loop = QEventLoop()
    overlay.destroyed.connect(loop.quit)
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    loop.exec()
    return held[0]
