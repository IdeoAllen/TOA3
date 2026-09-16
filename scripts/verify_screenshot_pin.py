#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""截图钉图冒烟：能建窗、有正确 DPR 几何。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from PySide6.QtGui import QColor, QImage, QPixmap
    from PySide6.QtWidgets import QApplication

    from services.screenshot_pin import pin_screenshot

    app = QApplication.instance() or QApplication(sys.argv)
    img = QImage(200, 120, QImage.Format.Format_ARGB32)
    img.fill(QColor("#3D7EFF"))
    pix = QPixmap.fromImage(img)
    pix.setDevicePixelRatio(1.0)
    win = pin_screenshot(pix)
    if win is None:
        print("FAIL: pin_screenshot returned None")
        return 1
    if win.width() < 10 or win.height() < 10:
        print(f"FAIL: bad size {win.width()}x{win.height()}")
        return 1
    win.close()
    app.processEvents()

    # 导出图（物理像素 + dpr=1）+ logical_size → 贴屏不翻倍
    img2 = QImage(400, 240, QImage.Format.Format_ARGB32)
    img2.fill(QColor("#22AA66"))
    pix2 = QPixmap.fromImage(img2)
    pix2.setDevicePixelRatio(1.0)
    win2 = pin_screenshot(pix2, logical_size=(200, 120))
    if win2 is None or win2.width() != 200 or win2.height() != 120:
        print(f"FAIL: logical_size pin got {None if win2 is None else (win2.width(), win2.height())}")
        if win2 is not None:
            win2.close()
        return 1
    win2.close()
    app.processEvents()
    print("VERIFY screenshot_pin OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
