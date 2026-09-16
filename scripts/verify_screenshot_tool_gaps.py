#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screenshot_tool 可代码 gaps：钉图 HiDPI 尺寸、loupe 逻辑取样、热键延后开层。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def _check_hotkey_deferred() -> None:
    path = ROOT / "services" / "screenshot_service.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_screenshot_hotkey":
            src = ast.get_source_segment(text, node) or ""
            if "QTimer.singleShot" not in src:
                fail("run_screenshot_hotkey 未 QTimer.singleShot 延后抓屏")
                return
            # 函数体顶层不应直接 capture_*（应在回调内）
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    pass
                chunk = ast.get_source_segment(text, stmt) or ""
                if chunk.strip().startswith("capture_region(") or chunk.strip().startswith(
                    "capture_fullscreen("
                ):
                    fail("run_screenshot_hotkey 仍同步直接调用 capture_*")
                    return
            ok("热键入口延后开层（QTimer.singleShot）")
            return
    fail("未找到 run_screenshot_hotkey")


def _check_loupe_helpers() -> None:
    from services.screenshot_overlay import loupe_source_rect

    x0, y0, cw, ch = loupe_source_rect(100, 80, 400, 300, src_r=7)
    assert x0 == 93 and y0 == 73 and cw == 15 and ch == 15, (x0, y0, cw, ch)
    # 贴边不越界
    x0, y0, cw, ch = loupe_source_rect(0, 0, 200, 100, src_r=7)
    assert x0 == 0 and y0 == 0 and cw == 8 and ch == 8, (x0, y0, cw, ch)
    x0, y0, cw, ch = loupe_source_rect(199, 99, 200, 100, src_r=7)
    assert x0 + cw <= 200 and y0 + ch <= 100
    ok("loupe_source_rect 逻辑取样边界")

    overlay = (ROOT / "services" / "screenshot_overlay.py").read_text(encoding="utf-8")
    if "loupe_source_rect(" not in overlay or "_pixmap_logical_size" not in overlay:
        fail("overlay 未使用逻辑像素 loupe 路径")
    else:
        ok("overlay loupe 走逻辑像素路径")


def _check_pin_hidpi_size() -> None:
    from PySide6.QtGui import QColor, QImage, QPixmap
    from PySide6.QtWidgets import QApplication

    from services.screenshot_pin import pin_display_size, pin_screenshot

    app = QApplication.instance() or QApplication(sys.argv)

    # 模拟 crop_logical 导出：400x240 逻辑选区 @2x → 800x480 物理 + dpr=1
    img = QImage(800, 480, QImage.Format.Format_ARGB32)
    img.fill(QColor("#3D7EFF"))
    pix = QPixmap.fromImage(img)
    pix.setDevicePixelRatio(1.0)

    lw, lh = pin_display_size(pix, logical_size=(400, 240))
    if (lw, lh) != (400, 240):
        fail(f"pin_display_size 未尊重 logical_size: {lw}x{lh}")
        return
    ok("pin_display_size 尊重选区逻辑尺寸")

    win = pin_screenshot(pix, logical_size=(400, 240))
    if win is None:
        fail("pin_screenshot 返回 None")
        return
    if win.width() != 400 or win.height() != 240:
        fail(f"钉图窗尺寸应为 400x240，实际 {win.width()}x{win.height()}")
        win.close()
        return
    win.close()
    app.processEvents()
    ok("钉图 HiDPI 贴屏尺寸与选区一致")


def _check_overlay_pin_passes_logical() -> None:
    text = (ROOT / "services" / "screenshot_overlay.py").read_text(encoding="utf-8")
    if "logical_size=logical_size" not in text and "logical_size=" not in text:
        fail("_on_pin 未传 logical_size")
    elif "pin_screenshot(pix, anchor=anchor, logical_size=logical_size)" not in text:
        # 宽松：只要 pin 调用带 logical_size
        if "pin_screenshot(" in text and "logical_size" in text.split("_on_pin")[1][:800]:
            ok("_on_pin 传递 logical_size")
        else:
            fail("_on_pin 未向 pin_screenshot 传 logical_size")
    else:
        ok("_on_pin 传递 logical_size")


def main() -> int:
    _check_hotkey_deferred()
    _check_loupe_helpers()
    _check_pin_hidpi_size()
    _check_overlay_pin_passes_logical()
    if FAILURES:
        print("VERIFY screenshot_tool_gaps FAILED:", "; ".join(FAILURES))
        return 1
    print("VERIFY screenshot_tool_gaps OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
