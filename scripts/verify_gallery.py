# -*- coding: utf-8 -*-
"""控件库 / QSS 自动化验收（对标 TOA2 verify_theme_preview.py）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []
WARNINGS: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"WARN: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def _hex_norm(h: str) -> str:
    h = (h or "").strip().upper()
    if h.startswith("#"):
        h = h[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return h


def _hex_dist(a: str, b: str) -> float:
    def parse(h: str) -> tuple[int, int, int]:
        h = _hex_norm(h)
        if len(h) != 6:
            return (0, 0, 0)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    pa, pb = parse(a), parse(b)
    return sum(abs(x - y) for x, y in zip(pa, pb)) ** 0.5


def _qss_contains_color(qss: str, token_hex: str, label: str) -> None:
    norm = _hex_norm(token_hex)
    patterns = [
        token_hex,
        f"#{norm}",
        f"#{norm[:2]}{norm[2:4]}{norm[4:6]}",
    ]
    if any(p.lower() in qss.lower() for p in patterns if p):
        ok(f"QSS contains {label} ({token_hex})")
    else:
        fail(f"QSS missing {label} color {token_hex}")


def main() -> int:
    from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPushButton, QProgressBar

    from app.theme_loader import apply_theme, load_palette, qss_path, read_qss
    from modules.gallery.control_library_content import build_control_library_content
    from services.theme_catalog import selectable_themes
    from widgets.metrics import BUTTON_MIN_HEIGHT

    theme_id = "dms_blue"
    qss_file = qss_path(theme_id)
    if not qss_file.is_file():
        fail(f"QSS not found: {qss_file}")
        return 1

    qss = read_qss(theme_id)
    pal = load_palette(theme_id)
    primary = pal.get("primary", "#2563EB")
    row_sel = pal.get("row_selected", "#DBEAFE")
    progress = pal.get("progress_fill", primary)

    _qss_contains_color(qss, primary, "primary")
    _qss_contains_color(qss, row_sel, "row_selected")
    _qss_contains_color(qss, progress, "progress_fill")

    for cls in ("page-title", "section-title", "hint", "semantic-success"):
        if f'class="{cls}"' in qss or f"class='{cls}'" in qss:
            ok(f"QSS selector class={cls}")
        else:
            fail(f"QSS missing QLabel class={cls}")

    if "QPushButton[class=\"primary\"]" in qss or "QPushButton[class='primary']" in qss:
        ok("QSS primary button")
    else:
        fail("QSS missing QPushButton[class=primary]")

    # 全部官方主题可加载
    app = QApplication([])
    for tid, _label in selectable_themes():
        try:
            apply_theme(app, tid)
        except Exception as e:
            fail(f"apply_theme {tid}: {e}")

    apply_theme(app, theme_id)

    # 控件最小高度（全局 QSS 生效后）
    btn = QPushButton("测")
    btn.setProperty("class", "primary")
    btn.style().polish(btn)
    btn_h = max(btn.minimumSizeHint().height(), btn.sizeHint().height())
    if btn_h < BUTTON_MIN_HEIGHT - 4:
        warn(f"primary button height {btn_h} < {BUTTON_MIN_HEIGHT}")
    else:
        ok(f"button min height ~{btn_h}px (>= {BUTTON_MIN_HEIGHT - 4})")

    entry = QLineEdit()
    entry.style().polish(entry)
    ent_h = max(entry.minimumSizeHint().height(), entry.sizeHint().height())
    if ent_h < BUTTON_MIN_HEIGHT - 4:
        warn(f"lineedit height {ent_h} < {BUTTON_MIN_HEIGHT}")
    else:
        ok(f"lineedit min height ~{ent_h}px")

    cb = QCheckBox("测")
    cb.setChecked(True)
    cb.style().polish(cb)
    ok("checkbox construct + polish")

    pb = QProgressBar()
    pb.setValue(50)
    pb.style().polish(pb)
    ok("progressbar construct + polish")

    # 控件库内容可构建
    try:
        scroll = build_control_library_content()
        if scroll.widget():
            scroll.widget().deleteLater()
        scroll.deleteLater()
        ok("control_library_content builds")
    except Exception as e:
        fail(f"control_library_content: {e}")

    from widgets import CONTROL_CLASSES
    if len(CONTROL_CLASSES) >= 20:
        ok(f"widget library registered ({len(CONTROL_CLASSES)} controls)")
    else:
        warn(f"widget library only {len(CONTROL_CLASSES)} controls")

    from core.message_dialog import MessageDialog
    ok("MessageDialog available")

    # 语义条 QSS 四色
    for cls, key in (
        ("semantic-success", "success_bg"),
        ("semantic-warning", "warning_bg"),
        ("semantic-danger", "danger_bg"),
        ("semantic-info", "info_bg"),
    ):
        hex_v = pal.get(key, "")
        if hex_v and cls in qss:
            ok(f"semantic {cls}")
        elif cls in qss:
            ok(f"semantic class {cls} in QSS")
        else:
            warn(f"semantic {cls} not verified")

    if WARNINGS:
        print(f"\nWarnings: {len(WARNINGS)}")
    if FAILURES:
        print("\nGALLERY VERIFY FAILED")
        for f in FAILURES:
            print(f" - {f}")
        return 1

    print("\nGALLERY VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
