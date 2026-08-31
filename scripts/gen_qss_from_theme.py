# -*- coding: utf-8 -*-
"""从 config/themes/<id>.json 生成 resources/qss/<id>.qss。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

THEMES = ROOT / "config" / "themes"
OUT = ROOT / "resources" / "qss"


def _p(pal: dict, key: str, default: str) -> str:
    v = pal.get(key)
    return str(v) if v else default


def _lum(hex_c: str) -> float:
    h = hex_c.lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _ensure_contrast(fg: str, bg: str, target: float) -> str:
    """生成期抬升对比度，防止靠色看不见。"""
    if not fg or not bg or _contrast(fg, bg) >= target:
        return fg
    end = "#000000" if _lum(bg) > 0.45 else "#FFFFFF"
    h1, h2 = fg.lstrip("#"), end.lstrip("#")
    rgb1 = [int(h1[i : i + 2], 16) for i in (0, 2, 4)]
    rgb2 = [int(h2[i : i + 2], 16) for i in (0, 2, 4)]
    for i in range(0, 101):
        t = i / 100
        out = [int(rgb1[j] * (1 - t) + rgb2[j] * t) for j in range(3)]
        c = "#" + "".join(f"{x:02X}" for x in out)
        if _contrast(c, bg) >= target:
            return c
    return end


def write_arrow_svgs(theme_id: str, color: str) -> dict[str, Path]:
    """按主题色写出箭头图。优先 PNG（QSS 在 Windows 上对 SVG 箭头不稳定）。"""
    arrow_dir = OUT / "arrows" / theme_id
    arrow_dir.mkdir(parents=True, exist_ok=True)
    stroke = color.strip() or "#6B7C94"

    # 保留 SVG 便于人工查看
    (arrow_dir / "chevron_down.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<path d="M2.2 4.2 L6 8 L9.8 4.2" fill="none" stroke="{stroke}" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>\n',
        encoding="utf-8",
    )
    (arrow_dir / "chevron_up.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<path d="M2.2 7.8 L6 4 L9.8 7.8" fill="none" stroke="{stroke}" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>\n',
        encoding="utf-8",
    )
    (arrow_dir / "chevron_left.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<path d="M7.8 2.2 L4 6 L7.8 9.8" fill="none" stroke="{stroke}" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>\n',
        encoding="utf-8",
    )
    (arrow_dir / "chevron_right.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<path d="M4.2 2.2 L8 6 L4.2 9.8" fill="none" stroke="{stroke}" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>\n',
        encoding="utf-8",
    )

    down_png = arrow_dir / "chevron_down.png"
    up_png = arrow_dir / "chevron_up.png"
    left_png = arrow_dir / "chevron_left.png"
    right_png = arrow_dir / "chevron_right.png"
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPen

        def _paint(path: Path, points: list[tuple[float, float]]) -> None:
            img = QImage(24, 24, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(stroke))
            pen.setWidthF(2.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QPointF(x, y) for x, y in points])
            painter.end()
            img.save(str(path), "PNG")

        _paint(down_png, [(4.0, 8.0), (12.0, 16.5), (20.0, 8.0)])
        _paint(up_png, [(4.0, 16.0), (12.0, 7.5), (20.0, 16.0)])
        _paint(left_png, [(16.0, 4.0), (8.0, 12.0), (16.0, 20.0)])
        _paint(right_png, [(8.0, 4.0), (16.0, 12.0), (8.0, 20.0)])
        return {"down": down_png, "up": up_png, "left": left_png, "right": right_png}
    except Exception:
        return {
            "down": arrow_dir / "chevron_down.svg",
            "up": arrow_dir / "chevron_up.svg",
            "left": arrow_dir / "chevron_left.svg",
            "right": arrow_dir / "chevron_right.svg",
        }


def write_check_indicators(
    theme_id: str, *, primary: str, on_primary: str, surface: str, border: str
) -> dict[str, Path]:
    """复选对勾 / 单选圆点（PNG，避免选中只剩色块无标记）。"""
    ind_dir = OUT / "arrows" / theme_id
    ind_dir.mkdir(parents=True, exist_ok=True)
    check_on = ind_dir / "check_on.png"
    radio_on = ind_dir / "radio_on.png"
    try:
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPen

        # 对勾图：透明底 + 白色勾（底色由 QSS background 提供）
        size = 40
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(on_primary))
        pen.setWidthF(3.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(
            [
                QPointF(9.0, 20.0),
                QPointF(17.0, 28.0),
                QPointF(31.0, 12.0),
            ]
        )
        p.end()
        img.save(str(check_on), "PNG")

        img2 = QImage(size, size, QImage.Format.Format_ARGB32)
        img2.fill(Qt.GlobalColor.transparent)
        p2 = QPainter(img2)
        p2.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p2.setBrush(QColor(primary))
        p2.setPen(Qt.PenStyle.NoPen)
        p2.drawEllipse(QRectF(1, 1, size - 2, size - 2))
        p2.setBrush(QColor(on_primary))
        p2.drawEllipse(QRectF(12, 12, 16, 16))
        p2.end()
        img2.save(str(radio_on), "PNG")
        return {"check_on": check_on, "radio_on": radio_on}
    except Exception:
        # 无 Qt 时退回空文件占位，QSS 仍有色底
        check_on.write_bytes(b"")
        radio_on.write_bytes(b"")
        return {"check_on": check_on, "radio_on": radio_on}


def build_qss(pal: dict) -> str:
    primary = _p(pal, "primary", "#2563EB")
    primary_hover = _p(pal, "primary_hover", primary)
    primary_pressed = _p(pal, "primary_pressed", primary)
    on_primary = _ensure_contrast(_p(pal, "text_on_primary", "#FFFFFF"), primary, 4.0)
    bg = _p(pal, "background", "#EEF1F6")
    surface = _p(pal, "surface", "#FFFFFF")
    text = _ensure_contrast(_p(pal, "text_primary", "#0F1C33"), surface, 4.5)
    # 辅助说明须足够清晰（截图页提示等），对 surface 与页面底双向抬升
    text2 = _ensure_contrast(_p(pal, "text_secondary", "#45566F"), surface, 6.0)
    text2 = _ensure_contrast(text2, bg, 5.5)
    text_dis = _ensure_contrast(_p(pal, "text_disabled", "#6B7C94"), surface, 3.0)
    border = _p(pal, "border_default", "#D2DBE8")
    tip_bg = _p(pal, "tooltip_bg", surface)
    tip_fg = _ensure_contrast(_p(pal, "tooltip_fg", text), tip_bg, 7.0)
    tip_border = _p(pal, "tooltip_border", border)
    input_bg = _p(pal, "input_bg", surface)
    input_border = _p(pal, "border_input", border)
    focus = _p(pal, "border_focus", primary)
    row_sel = _p(pal, "row_selected", "#DBEAFE")
    row_sel_text = _ensure_contrast(_p(pal, "row_selected_text", text), row_sel, 4.5)
    header_bg = _p(pal, "header_bg", "#0F2744")
    header_fg = _ensure_contrast(_p(pal, "header_fg", "#F0F7FF"), header_bg, 4.5)
    progress_fill = _p(pal, "progress_fill", primary)
    progress_bg = _p(pal, "progress_bg", "#F0F3F8")
    danger = _p(pal, "danger", "#B91C1C")
    success_bg = _p(pal, "success_bg", "#DCFCE7")
    success = _ensure_contrast(_p(pal, "success", "#15803D"), success_bg, 4.5)
    warning_bg = _p(pal, "warning_bg", "#FFEDD5")
    warning = _ensure_contrast(_p(pal, "warning", "#B45309"), warning_bg, 4.5)
    danger_bg = _p(pal, "danger_bg", "#FEE2E2")
    info_bg = _p(pal, "info_bg", "#DBEAFE")
    info = _ensure_contrast(_p(pal, "info", primary), info_bg, 4.5)
    sidebar = _p(pal, "nav_bg", _p(pal, "surface_sidebar", header_bg))
    nav_fg = _ensure_contrast(_p(pal, "nav_fg", "#EAF0F8"), sidebar, 4.5)
    nav_active_bg = _p(pal, "nav_active_bg", primary)
    nav_active_fg = _ensure_contrast(_p(pal, "nav_active_fg", on_primary), nav_active_bg, 4.5)
    nav_hover_bg = _p(pal, "nav_hover_bg", _p(pal, "row_hover", nav_active_bg))
    nav_hover_fg = _ensure_contrast(
        _p(pal, "nav_hover_fg", _p(pal, "text_primary", nav_fg)), nav_hover_bg, 4.5
    )
    nav_indicator = _p(pal, "nav_indicator", primary)
    row_hover = _p(pal, "row_hover", "#F0F3F8")
    row_hover_fg = _ensure_contrast(text, row_hover, 4.5)
    menu_sel_bg = _p(pal, "selection", primary)
    menu_sel_fg = _ensure_contrast(on_primary, menu_sel_bg, 4.5)
    disabled_bg = _p(pal, "primary_disabled_bg", "#F0F3F8")
    surface_raised = _p(pal, "surface_raised", surface)
    surface_alt = _p(pal, "surface_alt", surface_raised)
    cal_nav_bg = _p(pal, "header_bg", primary)
    cal_nav_fg = _ensure_contrast(_p(pal, "header_fg", on_primary), cal_nav_bg, 4.5)

    return f"""
/* TOA3 generated QSS — do not edit; edit JSON + regen */

* {{
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: {text};
}}

/* 必须显式覆盖：否则 Windows 白底 ToolTip 会继承 * 的浅色字 → 看不见 */
QToolTip {{
    background-color: {tip_bg};
    color: {tip_fg};
    border: 1px solid {tip_border};
    padding: 6px 10px;
    border-radius: 4px;
}}

QMainWindow, QWidget#PageRoot {{
    background: {bg};
}}

QDialog, QDialog#ThemedDialog {{
    background: {surface};
    color: {text};
}}

QDialog QLabel {{
    color: {text};
}}

QDialog QLabel[class="hint"] {{
    color: {text2};
}}

QLabel[class="page-title"] {{
    font-size: 14pt;
    font-weight: 700;
    color: {text};
}}

QLabel[class="section-title"] {{
    font-size: 12pt;
    font-weight: 700;
    color: {text};
}}

QLabel[class="hint"] {{
    font-size: 9pt;
    color: {text2};
}}

QLabel[class="semantic-success"] {{
    background: {success_bg};
    color: {success};
    padding: 8px 12px;
    border-radius: 4px;
}}

QLabel[class="semantic-warning"] {{
    background: {warning_bg};
    color: {warning};
    padding: 8px 12px;
    border-radius: 4px;
}}

QLabel[class="semantic-danger"] {{
    background: {danger_bg};
    color: {danger};
    padding: 8px 12px;
    border-radius: 4px;
}}

QLabel[class="semantic-info"] {{
    background: {info_bg};
    color: {info};
    padding: 8px 12px;
    border-radius: 4px;
}}

QLabel[class="semantic-success"][compact="true"],
QLabel[class="semantic-warning"][compact="true"],
QLabel[class="semantic-danger"][compact="true"],
QLabel[class="semantic-info"][compact="true"] {{
    padding: 2px 8px;
    font-size: 9pt;
    min-height: 18px;
}}

QPushButton {{
    min-height: 28px;
    padding: 4px 12px;
    border: 1px solid {border};
    border-radius: 4px;
    background: {surface};
    color: {text};
    outline: none;
}}

QPushButton:focus {{
    outline: none;
}}

QPushButton:hover {{
    background: {row_hover};
    border-color: {primary};
    color: {row_hover_fg};
}}

QPushButton:pressed {{
    background: {_p(pal, "row_active", "#E8ECF2")};
}}

QPushButton:disabled {{
    background: {disabled_bg};
    color: {text_dis};
    border-color: {border};
}}

/* 带菜单的按钮：右侧三角垂直居中（修复默认偏下） */
QPushButton[hasMenu="true"] {{
    padding-right: 22px;
}}

QPushButton::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 10px;
    height: 10px;
    right: 8px;
    top: 50%;
    margin-top: -5px;
}}

QToolButton {{
    outline: none;
}}

QToolButton:focus {{
    outline: none;
}}

/* 通用 ToolButton 菜单三角居中（壳层/更多等） */
QToolButton::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 10px;
    height: 10px;
    right: 6px;
    top: 50%;
    margin-top: -5px;
}}

QAbstractButton:focus {{
    outline: none;
}}

QPushButton[class="primary"] {{
    background: {primary};
    color: {on_primary};
    border: 1px solid {primary};
    font-weight: 600;
}}

QPushButton[class="primary"]:hover {{
    background: {primary_hover};
    border-color: {primary_hover};
}}

QPushButton[class="primary"]:pressed {{
    background: {primary_pressed};
}}

QPushButton[class="danger"] {{
    background: {danger};
    color: {on_primary};
    border: 1px solid {danger};
    font-weight: 600;
}}

QPushButton[class="msg-info"],
QPushButton[class="msg-confirm"] {{
    background: #0078D4;
    color: #FFFFFF;
    border: 1px solid #0078D4;
    font-weight: 600;
}}

QPushButton[class="msg-warning"] {{
    background: #F0A020;
    color: #FFFFFF;
    border: 1px solid #F0A020;
    font-weight: 600;
}}

QPushButton[class="msg-error"] {{
    background: #E81123;
    color: #FFFFFF;
    border: 1px solid #E81123;
    font-weight: 600;
}}

QPushButton[class="msg-success"] {{
    background: #107C10;
    color: #FFFFFF;
    border: 1px solid #107C10;
    font-weight: 600;
}}

QLineEdit {{
    min-height: 32px;
    padding: 4px 10px;
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    selection-background-color: {row_sel};
}}

QComboBox, QSpinBox, QDateEdit {{
    min-height: 32px;
    padding: 4px 10px;
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    selection-background-color: {row_sel};
}}

QComboBox {{
    padding-right: 36px;
}}

QComboBox:hover {{
    border: 1px solid {focus};
}}

QSpinBox, QDateEdit {{
    padding-right: 36px;
}}

QSpinBox, QDateEdit {{
    padding-right: 36px;
}}

QSpinBox#ThemedSpinBoxField {{
    min-height: 26px;
    max-height: 32px;
    padding: 0;
    margin: 0;
    border: none;
    background: transparent;
    color: {text};
    font-weight: 500;
}}

QSpinBox#ThemedSpinBoxField:focus {{
    border: none;
}}

QWidget#ThemedSpinBox {{
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    min-height: 32px;
    max-height: 36px;
}}

QWidget#ThemedSpinBox:hover {{
    border: 1px solid {focus};
}}

QWidget#ThemedSpinBox[focusRing="true"] {{
    border: 1px solid {focus};
}}

QToolButton#SpinBoxUpButton, QToolButton#SpinBoxDownButton {{
    background: {surface_raised};
    border: none;
    border-radius: 2px;
    padding: 0;
    margin: 0;
    min-width: 22px;
    max-width: 22px;
}}

QToolButton#SpinBoxUpButton:hover, QToolButton#SpinBoxDownButton:hover {{
    background: {_p(pal, "row_hover", "#F0F3F8")};
}}

QToolButton#SpinBoxUpButton:pressed, QToolButton#SpinBoxDownButton:pressed {{
    background: {_p(pal, "row_active", border)};
}}

QSpinBox {{
    padding-right: 44px;
    color: {text};
    font-weight: 500;
}}

QSpinBox::line-edit, QSpinBox QLineEdit {{
    background: transparent;
    color: {text};
    border: none;
    padding: 2px 8px;
    selection-background-color: {row_sel};
    selection-color: {text};
}}

QSpinBox:hover {{
    border: 1px solid {focus};
}}

QSpinBox:focus {{
    border: 1px solid {focus};
    color: {text};
}}

QSpinBox::up-button {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    height: 12px;
    margin-top: 4px;
    margin-right: 4px;
    border: none;
    border-radius: 3px;
    background: {surface_raised};
}}

QSpinBox::down-button {{
    subcontrol-origin: padding;
    subcontrol-position: bottom right;
    width: 30px;
    height: 12px;
    margin-bottom: 4px;
    margin-right: 4px;
    border: none;
    border-radius: 3px;
    background: {surface_raised};
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {_p(pal, "row_hover", "#F0F3F8")};
}}

QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
    background: {_p(pal, "row_active", border)};
}}

QSpinBox::up-arrow {{
    image: url(__TOA3_ARROW_UP__);
    width: 12px;
    height: 12px;
}}

QSpinBox::down-arrow {{
    image: url(__TOA3_ARROW_DOWN__);
    width: 12px;
    height: 12px;
}}

QDateEdit:hover {{
    border: 1px solid {focus};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border: none;
    background: transparent;
}}

QComboBox::drop-down:hover {{
    background: transparent;
}}

QComboBox QAbstractItemView {{
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    selection-background-color: {row_sel};
    selection-color: {text};
    outline: 0;
    padding: 4px;
}}

QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 6px 10px;
}}

QComboBox::down-arrow {{
    image: url(__TOA3_ARROW_DOWN__);
    width: 12px;
    height: 12px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 8px;
    top: 50%;
    margin-top: -6px;
}}

/* 一体式 DateEdit：外框像输入框，内嵌无边日期字 + 日历图标 */
QWidget#DateEdit {{
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    min-height: 32px;
    max-height: 36px;
}}

QWidget#DateEdit:hover,
QWidget#DateEdit:focus {{
    border: 1px solid {focus};
}}

QLineEdit#DateEditField {{
    background: transparent;
    border: none;
    padding: 2px 4px;
    min-height: 26px;
    color: {text};
    selection-background-color: {row_sel};
}}

QLineEdit#DateEditField:focus,
QLineEdit#DateEditField:hover {{
    border: none;
    background: transparent;
}}

QToolButton#DateEditButton {{
    background: transparent;
    border: none;
    padding: 0;
    margin: 0 2px 0 0;
    min-width: 28px;
    max-width: 30px;
    min-height: 26px;
    max-height: 28px;
}}

QToolButton#DateEditButton:hover,
QToolButton#DateEditButton:pressed {{
    background: transparent;
    border: none;
}}

QDateEdit::up-button, QDateEdit::down-button {{
    subcontrol-origin: padding;
    width: 26px;
    border: none;
    background: transparent;
}}

QDateEdit::up-button {{
    subcontrol-position: top right;
    height: 50%;
    border-top-right-radius: 3px;
}}

QDateEdit::down-button {{
    subcontrol-position: bottom right;
    height: 50%;
    border-bottom-right-radius: 3px;
}}

QDateEdit::up-button:hover, QDateEdit::down-button:hover,
QDateEdit::up-button:pressed, QDateEdit::down-button:pressed {{
    background: transparent;
}}

QDateEdit::up-arrow {{
    image: url(__TOA3_ARROW_UP__);
    width: 10px;
    height: 10px;
}}

QDateEdit::down-arrow {{
    image: url(__TOA3_ARROW_DOWN__);
    width: 10px;
    height: 10px;
}}

QDateEdit::drop-down {{
    subcontrol-origin: border;
    subcontrol-position: center right;
    width: 28px;
    border: none;
    background: transparent;
}}

QLineEdit:focus {{
    border: 1px solid {focus};
}}

QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {focus};
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled, QWidget#DateEdit:disabled, QWidget#ThemedSpinBox:disabled {{
    background: {disabled_bg};
    color: {text_dis};
}}

QTextEdit, QPlainTextEdit {{
    min-height: 80px;
    padding: 8px 10px;
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    selection-background-color: {row_sel};
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {focus};
}}

QTextEdit:disabled, QPlainTextEdit:disabled {{
    background: {disabled_bg};
    color: {text_dis};
}}

QListWidget {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
}}

QListWidget::item:selected {{
    background: {row_sel};
    color: {row_sel_text};
}}

QListWidget::item:hover {{
    background: {row_hover};
    color: {row_hover_fg};
}}

QTreeWidget {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    alternate-background-color: {_p(pal, "row_alt", bg)};
    outline: none;
}}

QTreeWidget::item {{
    min-height: 28px;
    padding: 2px 4px;
}}

QTreeWidget::item:selected {{
    background: {row_sel};
    color: {row_sel_text};
}}

QTreeWidget::item:hover {{
    background: {row_hover};
    color: {row_hover_fg};
}}

/* 记事大纲：卡片容器 + 轻选中，层级线更清晰 */
QWidget#OutlineTreePanel {{
    background: {surface_alt};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 2px;
}}

QWidget#OutlineTreeHeader {{
    padding: 0 2px 2px 2px;
}}

QTreeWidget#OutlineTree {{
    alternate-background-color: transparent;
    background: transparent;
    border: none;
    outline: none;
    show-decoration-selected: 1;
}}

QTreeWidget#OutlineTree::item {{
    min-height: 34px;
    padding: 5px 10px;
    border-left: 3px solid transparent;
    border-radius: 6px;
    margin: 2px 4px;
}}

QTreeWidget#OutlineTree::item:hover {{
    background: {row_hover};
    color: {text};
    border-left: 3px solid {border};
}}

QTreeWidget#OutlineTree::item:selected,
QTreeWidget#OutlineTree::item:selected:hover,
QTreeWidget#OutlineTree::item:selected:active {{
    background: {nav_active_bg};
    color: {nav_active_fg};
    border-left: 3px solid {nav_indicator};
    font-weight: 600;
}}

QWidget#NotepadToolbar {{
    background: {surface_alt};
    border: 1px solid {border};
    border-radius: 10px;
}}

LineEdit#NotepadSearchEdit {{
    min-height: 32px;
    border-radius: 8px;
}}

QWidget#NotepadEditorChrome {{
    background: {surface_alt};
    border: 1px solid {border};
    border-radius: 10px;
}}

QWidget#NotepadEditorSurface {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
}}

QWidget#NotepadFmtToolbar {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 8px;
}}

QWidget#NotepadEditorFooter {{
    border-top: 1px solid {border};
    padding-top: 2px;
}}

PlainTextEdit#MarkdownSourceEdit,
TextEdit#MarkdownPreviewEdit,
TextEdit#MarkdownDesignEdit {{
    border: none;
    border-radius: 6px;
    padding: 10px 12px;
    background: transparent;
}}

QWidget#EditorViewTabs {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 999px;
    padding: 2px;
}}

QTabBar#EditorViewTabBar {{
    background: transparent;
}}

QTabBar#EditorViewTabBar::tab {{
    min-width: 56px;
    min-height: 28px;
    max-height: 30px;
    padding: 4px 16px;
    margin: 1px;
    background: transparent;
    color: {text2};
    border: none;
    border-radius: 999px;
}}

QTabBar#EditorViewTabBar::tab:selected {{
    background: {surface};
    color: {primary};
    font-weight: 600;
    border: 1px solid {border};
}}

QTabBar#EditorViewTabBar::tab:hover:!selected {{
    background: {nav_hover_bg};
    color: {text};
}}

QTreeWidget#OutlineTree::branch {{
    background: transparent;
}}

QTreeWidget#OutlineTree::branch:has-siblings:!adjoins-item {{
    border-image: none;
    border-left: 1px solid {border};
}}

QTreeWidget#OutlineTree::branch:has-siblings:adjoins-item {{
    border-image: none;
    border-left: 1px solid {border};
}}

QTreeWidget#OutlineTree::branch:!has-children:!has-siblings:adjoins-item {{
    border-image: none;
    border-left: 1px solid {border};
}}

QDialog#MessageDialog {{
    background: {surface};
    color: {text};
}}

QCheckBox, QRadioButton {{
    spacing: 8px;
    min-height: 28px;
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {input_border};
    border-radius: 4px;
    background: {surface};
}}

QCheckBox::indicator:hover {{
    border-color: {primary};
}}

QCheckBox::indicator:checked {{
    border: 2px solid {primary};
    background: {primary};
    image: url(__TOA3_CHECK_ON__);
}}

QCheckBox::indicator:disabled {{
    border-color: {border};
    background: {progress_bg};
}}

QCheckBox::indicator:checked:disabled {{
    border-color: {border};
    background: {progress_bg};
    image: url(__TOA3_CHECK_ON__);
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {input_border};
    border-radius: 9px;
    background: {surface};
}}

QRadioButton::indicator:hover {{
    border-color: {primary};
}}

QRadioButton::indicator:checked {{
    border: none;
    background: transparent;
    image: url(__TOA3_RADIO_ON__);
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {progress_bg};
    border: 1px solid {border};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {progress_fill};
    border-radius: 3px;
}}

QSlider::add-page:horizontal {{
    background: {progress_bg};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: {primary};
    border: 1px solid {primary};
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {primary_hover};
    border-color: {primary_hover};
}}

QSlider::groove:vertical {{
    width: 6px;
    background: {progress_bg};
    border: 1px solid {border};
    border-radius: 3px;
}}

QSlider::handle:vertical {{
    width: 16px;
    height: 16px;
    margin: 0 -6px;
    background: {primary};
    border-radius: 8px;
}}

QProgressBar {{
    min-height: 12px;
    border: 1px solid {border};
    border-radius: 4px;
    background: {progress_bg};
    text-align: center;
}}

QProgressBar::chunk {{
    background: {progress_fill};
    border-radius: 3px;
}}

/* 日历 / 日期弹层：与主题同色，禁止系统白底浅字 */
QCalendarWidget {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
}}

QCalendarWidget QWidget {{
    alternate-background-color: {surface_raised};
}}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {cal_nav_bg};
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    min-height: 36px;
}}

QCalendarWidget QToolButton {{
    color: {cal_nav_fg};
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-weight: 600;
    min-width: 28px;
}}

QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 2px 4px;
    min-width: 26px;
    max-width: 26px;
    min-height: 28px;
    max-height: 28px;
    icon-size: 14px 14px;
}}

QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {{
    background: {nav_hover_bg};
    color: {nav_hover_fg};
}}

QCalendarWidget QToolButton:hover {{
    background: {nav_hover_bg};
    color: {nav_hover_fg};
}}

QCalendarWidget QToolButton::menu-indicator {{
    image: none;
    width: 0;
}}

QCalendarWidget QSpinBox {{
    background: {input_bg};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    selection-background-color: {row_sel};
}}

QCalendarWidget QAbstractItemView {{
    background: {surface};
    color: {text};
    outline: none;
    selection-background-color: {primary};
    selection-color: {menu_sel_fg};
    font-size: 10pt;
}}

QCalendarWidget#ThemedCalendar QTableView {{
    border: 1px solid {border};
    margin: 4px 6px 6px 6px;
    gridline-color: {border};
    background: {surface};
}}

QCalendarWidget#ThemedCalendar QAbstractItemView {{
    selection-background-color: {primary};
    selection-color: {menu_sel_fg};
}}

QCalendarWidget QAbstractItemView:enabled {{
    color: {text};
}}

QCalendarWidget QAbstractItemView:disabled {{
    color: {text_dis};
}}

QCalendarWidget QMenu {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
}}

QCalendarWidget QMenu::item:selected {{
    background: {menu_sel_bg};
    color: {menu_sel_fg};
}}

QTableWidget {{
    gridline-color: {border};
    background: {surface};
    alternate-background-color: {_p(pal, "row_odd", "#F6F8FB")};
    selection-background-color: {row_sel};
    selection-color: {row_sel_text};
}}

QHeaderView::section {{
    background: {header_bg};
    color: {header_fg};
    padding: 8px;
    border: none;
    font-weight: 600;
}}

QTabWidget::pane {{
    border: 1px solid {border};
    background: {surface};
}}

QTabBar {{
    outline: none;
}}

QTabBar::tab {{
    min-height: 26px;
    max-height: 28px;
    padding: 3px 12px;
    background: {bg};
    color: {text2};
    border: 1px solid {border};
    margin-right: 2px;
    outline: none;
}}

QTabBar::tab:selected {{
    background: {surface};
    color: {primary};
    border-bottom: 2px solid {primary};
}}

QTabBar::tab:focus,
QTabBar::tab:focus:selected {{
    outline: none;
    border: 1px solid {border};
}}

QTabBar::tab:focus:selected {{
    border-bottom: 2px solid {primary};
}}

QGroupBox {{
    font-size: 12px;
    font-weight: 600;
    border: 1px solid {border};
    border-radius: 6px;
    margin-top: 18px;
    padding: 14px 10px 10px 10px;
    background: {surface};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 6px;
    background-color: {surface};
    color: {text2};
}}

QScrollBar:vertical {{
    width: 12px;
    background: {bg};
}}

QScrollBar::handle:vertical {{
    background: {_p(pal, "scrollbar_thumb", border)};
    min-height: 24px;
    border-radius: 4px;
}}

/* Shell chrome */
QWidget#ShellHeader {{
    background: {header_bg};
    color: {header_fg};
}}

QLabel#ShellBrand {{
    font-size: 13pt;
    font-weight: 700;
    color: {header_fg};
}}

QPushButton#ShellLicenseChip {{
    min-height: 24px;
    max-height: 26px;
    padding: 2px 10px;
    font-size: 12px;
    border-radius: 4px;
}}

QLabel#ShellLogo {{
    background: transparent;
    qproperty-alignment: AlignCenter;
}}

QToolButton#ShellHeaderBtn::menu-indicator {{
    image: none;
    width: 0;
    height: 0;
}}

QLabel#ShellUser,
QToolButton#ShellUser {{
    color: {header_fg};
    background: transparent;
    border: none;
    padding: 2px 10px;
    min-height: 22px;
    max-height: 28px;
    font-size: 12px;
}}

QToolButton#ShellUser:hover {{
    background: rgba(255, 255, 255, 0.14);
    border-radius: 4px;
}}

QWidget#ShellNav {{
    background: {sidebar};
}}

QScrollArea#ShellNavScroll {{
    background: {sidebar};
    border: none;
}}

QScrollArea#ShellNavScroll QWidget {{
    background: {sidebar};
}}

QScrollArea#ShellNavScroll QScrollBar:vertical {{
    width: 8px;
    background: {sidebar};
    margin: 0px;
}}

QScrollArea#ShellNavScroll QScrollBar::handle:vertical {{
    background: {_p(pal, "scrollbar_thumb", "rgba(255,255,255,0.22)")};
    min-height: 24px;
    border-radius: 4px;
}}

QScrollArea#ShellNavScroll QScrollBar::add-line:vertical,
QScrollArea#ShellNavScroll QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}

QScrollArea#ShellNavScroll QScrollBar::add-page:vertical,
QScrollArea#ShellNavScroll QScrollBar::sub-page:vertical {{
    background: {sidebar};
}}

QCheckBox#Switch {{
    spacing: 0;
    min-height: 28px;
}}

QCheckBox#Switch::indicator {{
    width: 0;
    height: 0;
    border: none;
    margin: 0;
    padding: 0;
}}

QCheckBox#Switch::indicator:checked {{
    image: none;
}}

QCheckBox#Switch::indicator:disabled {{
    image: none;
}}

QToolButton#NavCollapseBtn {{
    background: transparent;
    color: {nav_fg};
    border: none;
    padding: 0;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}

QToolButton#NavCollapseBtn:hover {{
    background: {nav_hover_bg};
}}

QToolButton#NavExpandRail {{
    background: {sidebar};
    color: {nav_fg};
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.10);
    padding: 0;
    min-width: 4px;
    max-width: 4px;
}}

QToolButton#NavExpandRail:hover {{
    background: {nav_hover_bg};
}}

QWidget#FinderToolbarBar {{
    background: {_p(pal, "surface", bg)};
    border: 1px solid {border};
    border-radius: 8px;
}}

QWidget#FinderToolbarModeGroup {{
    background: transparent;
}}

QWidget#FinderToolbarActionGroup {{
    background: transparent;
    border-left: 1px solid {border};
    padding-left: 8px;
    margin-left: 2px;
}}

QToolButton#FinderToolBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    color: {text2};
    min-height: 28px;
}}

QToolButton#FinderToolBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
    color: {text};
}}

QToolButton#FinderToolBtn:checked {{
    background: {nav_active_bg};
    color: {nav_active_fg};
}}

QToolButton#FinderTagBtn {{
    background: transparent;
    border: none;
    border-radius: 17px;
    padding: 4px;
}}

QToolButton#FinderTagBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
}}

QToolButton#FinderTagFilterBtn,
QToolButton#FinderQuickFilterBtn {{
    background: {_p(pal, "surface", bg)};
    border: 1px solid {_p(pal, "border", "#D0D5DD")};
    border-radius: 11px;
    padding: 0 7px;
    min-height: 20px;
    max-height: 22px;
    font-size: 12px;
    color: {text2};
}}

QToolButton#FinderTagFilterBtn {{
    padding: 0;
    min-width: 22px;
    max-width: 22px;
    border-radius: 11px;
}}

QToolButton#FinderTagFilterBtn:hover,
QToolButton#FinderQuickFilterBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
    color: {text};
}}

QToolButton#FinderTagFilterBtn:checked,
QToolButton#FinderQuickFilterBtn:checked {{
    background: {_p(pal, "surface_hover", bg)};
    border-color: {primary};
    color: {primary};
    font-weight: 500;
}}

QToolButton#FinderQuickFilterBtn:disabled {{
    color: {text2};
    opacity: 0.45;
}}

QWidget#FinderFilterBar {{
    background: transparent;
    padding: 0 0 2px 0;
}}

QWidget#FinderBreadcrumbBar {{
    background: transparent;
    padding: 0 0 2px 0;
}}

QScrollArea#FinderColumnScroll {{
    border: 1px solid {border};
    border-radius: 8px;
    background: {bg};
}}

QWidget#FinderColumnHost {{
    background: {bg};
}}

QListWidget#FinderColumn {{
    background: {surface};
    border: none;
    border-right: 1px solid {border};
    outline: none;
    padding: 6px 0;
}}

QListWidget#FinderColumn::item {{
    padding: 4px 10px 4px 8px;
    border-radius: 6px;
    min-height: 22px;
    color: {text};
}}

QListWidget#FinderColumn::item:selected {{
    background: {primary};
    color: #FFFFFF;
}}

QListWidget#FinderColumn::item:hover:!selected {{
    background: {_p(pal, "surface_hover", bg)};
}}

QListWidget#FinderFlatList {{
    background: transparent;
    border: none;
    outline: none;
    padding: 10px;
}}

QListWidget#FinderFlatList::item {{
    border-radius: 8px;
    padding: 2px 4px;
    margin: 2px;
    color: {text};
}}

QListWidget#FinderFlatList::item:selected {{
    background: {row_sel};
    color: {row_sel_text};
}}

QListWidget#FinderFlatList::item:hover:!selected {{
    background: {_p(pal, "surface_hover", bg)};
}}

QToolButton#FinderBreadcrumbBtn {{
    background: transparent;
    border: none;
    border-radius: 4px;
    color: {primary};
    padding: 2px 6px;
    min-height: 24px;
    font-weight: 500;
}}

QToolButton#FinderBreadcrumbBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
    text-decoration: underline;
}}

QLabel#FinderBreadcrumbSep {{
    color: {text2};
    padding: 0 2px;
    background: transparent;
}}

QLabel#FinderBreadcrumbCurrent {{
    color: {text};
    font-weight: 600;
    padding: 2px 4px;
    background: transparent;
}}

QToolButton#FinderBreadcrumbRootBtn {{
    background: transparent;
    border: 1px dashed {border};
    border-radius: 4px;
    color: {primary};
    padding: 2px 8px;
    min-height: 24px;
    font-weight: 600;
}}

QToolButton#FinderBreadcrumbRootBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
}}

QTableWidget#FinderDetailsTable {{
    border: 1px solid {border};
    border-radius: 8px;
    background: {surface};
    alternate-background-color: {_p(pal, "surface_alt", bg)};
    gridline-color: transparent;
    selection-background-color: {row_sel};
    selection-color: {row_sel_text};
}}

QTableWidget#FinderDetailsTable::item:selected {{
    background-color: {row_sel};
    color: {row_sel_text};
}}

QTableWidget#FinderDetailsTable::item:selected:active {{
    background-color: {row_sel};
    color: {row_sel_text};
}}

QTableWidget#FinderDetailsTable::item {{
    padding: 4px 8px;
    border: none;
}}

QHeaderView#qt_scrollarea_viewport::section,
QTableWidget#FinderDetailsTable QHeaderView::section {{
    background: {_p(pal, "surface_alt", bg)};
    color: {text2};
    border: none;
    border-bottom: 1px solid {border};
    padding: 6px 8px;
    font-weight: 600;
}}

QToolButton#FinderModeBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 10px;
    color: {text2};
    min-height: 28px;
    max-height: 28px;
    font-size: 12px;
}}

QToolButton#FinderModeBtn:checked {{
    background: {nav_active_bg};
    color: {nav_active_fg};
    border-color: {nav_active_bg};
    font-weight: 500;
}}

QToolButton#FinderModeBtn:hover:!checked {{
    background: {_p(pal, "surface_hover", bg)};
    color: {text};
    border-color: {border};
}}

QToolButton#FinderMenuBtn {{
    background: {_p(pal, "surface", bg)};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 10px;
    padding-right: 22px;
    color: {text2};
    min-height: 28px;
    max-height: 28px;
    font-size: 12px;
}}

QToolButton#FinderMenuBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
    color: {text};
    border-color: {_p(pal, "primary", border)};
}}

QToolButton#FinderMenuBtn:pressed {{
    background: {_p(pal, "selection", bg)};
}}

QToolButton#FinderMenuBtn[hasMenu="true"]::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 8px;
    height: 8px;
    right: 8px;
    top: 50%;
    margin-top: -4px;
}}

QPushButton#NavButton {{
    background: {sidebar};
    color: {nav_fg};
    border: none;
    min-height: 36px;
    padding: 8px 12px 8px 16px;
    text-align: left;
    outline: none;
}}

QPushButton#NavButton:focus {{
    outline: none;
}}

QPushButton#NavButton:hover {{
    background: {nav_hover_bg};
    color: {nav_hover_fg};
    border: none;
}}

QPushButton#NavGroupHeader {{
    background: {sidebar};
    color: {nav_fg};
    border: none;
    min-height: 32px;
    padding: 6px 10px;
    text-align: left;
    font-weight: 700;
    outline: none;
}}

QPushButton#NavGroupHeader:focus {{
    outline: none;
}}

QPushButton#NavGroupHeader:hover {{
    background: {nav_hover_bg};
    color: {nav_hover_fg};
}}

QPushButton#NavButton[navItem="true"] {{
    padding-left: 22px;
}}

QPushButton#NavButton:checked {{
    background: {nav_active_bg};
    color: {nav_active_fg};
}}

QPushButton#NavButton:checked:hover {{
    background: {nav_active_bg};
    color: {nav_active_fg};
}}

QPushButton#ThemePickerBtn {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    min-height: 40px;
    padding: 8px 12px;
    text-align: left;
    outline: none;
}}

QPushButton#ThemePickerBtn:focus {{
    outline: none;
}}

QPushButton#ThemePickerBtn:hover {{
    background: {_p(pal, "surface_raised", bg)};
    border-color: {_p(pal, "border_strong", border)};
}}

QPushButton#ThemePickerBtn:checked {{
    background: {_p(pal, "surface_raised", bg)};
    border: 2px solid {primary};
    color: {text};
    font-weight: 600;
    padding: 7px 11px;
}}

QPushButton#ThemePickerBtn:checked:hover {{
    background: {_p(pal, "surface_raised", bg)};
    border: 2px solid {primary};
}}

QWidget#ShellSubHeader {{
    background: {surface};
    border-bottom: 1px solid {border};
}}

QWidget#ShellFocusExitBar {{
    background: {sidebar};
    color: {nav_fg};
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}}

QWidget#ShellFocusExitBar QLabel {{
    color: {nav_fg};
    font-size: 12px;
}}

QToolButton#ShellQuickBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    color: {text2};
    font-size: 10pt;
}}

QToolButton#ShellQuickBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
    color: {text};
}}

QToolButton#ShellQuickBtn:pressed {{
    background: {_p(pal, "selection", border)};
}}

QToolButton#ShellQuickBtn[hasMenu="true"] {{
    padding-right: 24px;
}}

QToolButton#ShellQuickBtn[hasMenu="true"]::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 10px;
    height: 10px;
    right: 8px;
    top: 50%;
    margin-top: -5px;
}}

QToolButton#ShellDomainBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    color: {text2};
    font-size: 10pt;
    font-weight: 500;
}}

QToolButton#ShellDomainBtn:hover {{
    background: {_p(pal, "surface_hover", bg)};
    color: {text};
}}

QToolButton#ShellDomainBtn:checked {{
    color: {primary};
    font-weight: 600;
    border-bottom: 2px solid {primary};
    border-radius: 0px;
    padding-bottom: 4px;
}}

QToolButton#ShellDomainBtn:pressed {{
    background: {_p(pal, "selection", border)};
}}

QPushButton#ShellHeaderBtn,
QToolButton#ShellHeaderBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0;
    margin: 0;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    color: {header_fg};
    font-size: 16px;
    font-weight: 600;
}}

QPushButton#ShellHeaderBtn:hover,
QToolButton#ShellHeaderBtn:hover {{
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.22);
}}

QPushButton#ShellHeaderBtn[class="danger"]:hover {{
    background: rgba(220, 53, 69, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.35);
}}

QFrame#ToolLaunchCard {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
    min-height: 88px;
}}

QFrame#ToolLaunchCard[hover="true"] {{
    background: {_p(pal, "surface_hover", bg)};
    border: 1px solid {primary};
}}

QFrame#MediaStudioLeft {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}

QPlainTextEdit#MediaStudioPrompt {{
    min-height: 80px;
    max-height: 80px;
}}

QFrame#MediaStudioLeft QWidget#FormRow {{
    min-height: 32px;
}}

QFrame#MediaStudioLeft QLabel#FormRowLabel {{
    min-width: 44px;
}}

QLabel#MediaWorkPlayBadge {{
    background: transparent;
    color: #FFFFFF;
    font-size: 18px;
    font-weight: 600;
}}

QLabel#HarnessWebOverlay {{
    background: rgba(0, 0, 0, 0.45);
    color: #F5F5F7;
    padding: 12px 16px;
}}

QScrollArea#MediaStudioLeftScroll {{
    background: transparent;
    border: none;
}}

QScrollArea#MediaStudioLeftScroll QScrollBar:vertical {{
    width: 4px;
    background: transparent;
    margin: 2px 0px;
}}

QScrollArea#MediaStudioLeftScroll QScrollBar::handle:vertical {{
    background: {_p(pal, "scrollbar_thumb", "rgba(255,255,255,0.22)")};
    min-height: 18px;
    border-radius: 2px;
}}

QScrollArea#MediaStudioLeftScroll QScrollBar::add-line:vertical,
QScrollArea#MediaStudioLeftScroll QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}

QScrollArea#MediaStudioLeftScroll QScrollBar::add-page:vertical,
QScrollArea#MediaStudioLeftScroll QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollArea#MediaStudioFilmScroll QScrollBar:horizontal {{
    height: 4px;
    background: transparent;
    margin: 0px 2px;
}}

QScrollArea#MediaStudioFilmScroll QScrollBar::handle:horizontal {{
    background: {_p(pal, "scrollbar_thumb", "rgba(255,255,255,0.22)")};
    min-width: 18px;
    border-radius: 2px;
}}

QScrollArea#MediaStudioFilmScroll QScrollBar::add-line:horizontal,
QScrollArea#MediaStudioFilmScroll QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
    border: none;
}}

QFrame#MediaStudioVHandle {{
    background: {border};
    border-radius: 2px;
    margin: 2px 16px;
}}

QFrame#MediaStudioVHandle:hover {{
    background: {primary};
}}

QFrame#MediaStudioFooter {{
    border-top: 1px solid {border};
    padding-top: 4px;
    margin-top: 2px;
}}

QFrame#MediaStudioStage {{
    background: {_p(pal, "surface_inset", bg)};
    border: 1px solid {border};
    border-radius: 12px;
}}

QLabel#MediaPreviewCanvas {{
    background: transparent;
    color: {text2};
    padding: 12px;
    font-size: 10pt;
}}

QFrame#MediaWorksBlock {{
    background: transparent;
    border-top: 1px solid {border};
    padding-top: 6px;
}}

QLabel#MediaWorkThumb, QLabel#MediaRefThumbImage {{
    background: transparent;
}}

QFrame#MediaRefThumb {{
    background: {_p(pal, "surface_raised", surface)};
    border: 1px solid {border};
    border-radius: 8px;
}}

QFrame#MediaRefThumb:hover {{
    border-color: {primary};
}}

QFrame#MediaRefThumb QPushButton#MediaRefRemoveBtn {{
    min-height: 22px;
    max-height: 24px;
    padding: 0px 6px;
    font-size: 9pt;
}}

QFrame#MediaRefAddTile {{
    background: transparent;
    border: 1px dashed {border};
    border-radius: 8px;
}}

QFrame#MediaWorkTile {{
    background: {_p(pal, "surface_raised", surface)};
    border: 1px solid {border};
    border-radius: 8px;
}}

QFrame#MediaWorkTile:hover {{
    border-color: {_p(pal, "border_strong", border)};
    background: {_p(pal, "surface_hover", surface)};
}}

QFrame#MediaWorkTile[selected="true"] {{
    border: 2px solid {primary};
    background: {_p(pal, "surface_hover", surface)};
}}

QFrame#MediaTaskPanel {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}

QFrame#MediaTaskRow {{
    background: {_p(pal, "surface_raised", surface)};
    border: 1px solid {border};
    border-radius: 8px;
}}

QFrame#MediaTaskRow QPushButton {{
    min-height: 22px;
    max-height: 22px;
    padding: 0 6px;
    font-size: 9pt;
}}

QFrame#MediaTaskRow QProgressBar#MediaTaskProgress {{
    min-height: 4px;
    max-height: 4px;
    border-radius: 2px;
}}

QFrame#MediaTaskRow QProgressBar#MediaTaskProgress::chunk {{
    border-radius: 2px;
}}

QLabel#ToolCardTitle {{
    font-size: 11pt;
    font-weight: 700;
    color: {text};
}}

QLabel#ToolCardSub, QLabel#ToolCardShortcut {{
    font-size: 9pt;
    color: {text2};
}}

QLabel#ToolCardIcon {{
    background: {_p(pal, "selection", border)};
    border-radius: 8px;
}}

QMenu {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background: {menu_sel_bg};
    color: {menu_sel_fg};
}}

QMenu::item:hover {{
    background: {menu_sel_bg};
    color: {menu_sel_fg};
}}

QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}
"""


def resolve_arrow_placeholders(qss: str, theme_id: str, pal: dict) -> str:
    """把占位符换成当前仓库下箭头 / 对勾 PNG 的绝对路径（setStyleSheet 需要）。"""
    color = _p(pal, "text_secondary", _p(pal, "text_primary", "#6B7C94"))
    arrows = write_arrow_svgs(theme_id, color)
    primary = _p(pal, "primary", "#2563EB")
    on_primary = _ensure_contrast(_p(pal, "text_on_primary", "#FFFFFF"), primary, 4.0)
    surface = _p(pal, "surface", "#FFFFFF")
    border = _p(pal, "border_default", "#D2DBE8")
    inds = write_check_indicators(
        theme_id,
        primary=primary,
        on_primary=on_primary,
        surface=surface,
        border=border,
    )
    down = arrows["down"].resolve().as_posix()
    up = arrows["up"].resolve().as_posix()
    check = inds["check_on"].resolve().as_posix()
    radio = inds["radio_on"].resolve().as_posix()
    return (
        qss.replace("__TOA3_ARROW_DOWN__", down)
        .replace("__TOA3_ARROW_UP__", up)
        .replace("__TOA3_CHECK_ON__", check)
        .replace("__TOA3_RADIO_ON__", radio)
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(THEMES.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        pal = doc.get("palette") or {}
        theme_id = path.stem
        qss = resolve_arrow_placeholders(build_qss(pal), theme_id, pal)
        out = OUT / f"{theme_id}.qss"
        out.write_text(qss.strip() + "\n", encoding="utf-8")
        print("wrote", out.name, "+ arrows")


if __name__ == "__main__":
    main()
