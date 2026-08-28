# -*- coding: utf-8 -*-
"""Capture key TOA3 screens for Figma acceptance review (headless-ish)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "figma_acceptance"
SCREENS = [
    ("01_home", "home"),
    ("02_theme_preview", "theme_preview"),
    ("03_system_settings", "system_settings"),
    ("04_screenshot_tool", "screenshot_tool"),
    ("05_clipboard_history", "clipboard_history"),
]


def main() -> int:
    sys.path.insert(0, str(ROOT))

    from app.bootstrap import bootstrap_runtime
    from app.logging_setup import setup_logging
    from app.login_dialog import try_restore_licensed_session
    from app.shell import MainShell
    from app.theme_loader import apply_theme, ensure_official_qss, resolve_default_theme
    from services.config_service import load_config

    setup_logging()
    bootstrap_runtime()
    ensure_official_qss()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    apply_theme(app, resolve_default_theme())

    if not try_restore_licensed_session():
        print("FAIL: no restorable local session; login required")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shell = MainShell(defer_startup=True)
    shell.resize(1280, 920)
    shell.show()
    app.processEvents()
    shell.complete_startup()

    state = {"idx": 0}

    def capture_next() -> None:
        if state["idx"] >= len(SCREENS):
            print(f"OK: saved {len(SCREENS)} screenshots to {OUT_DIR}")
            app.quit()
            return

        name, module_id = SCREENS[state["idx"]]
        shell.navigate(module_id)
        app.processEvents()

        def _shot() -> None:
            path = OUT_DIR / f"{name}.png"
            pix = shell.grab()
            if pix.isNull():
                print(f"FAIL: empty grab for {name}")
                app.quit()
                return
            pix.save(str(path))
            print(f"saved {path.name} ({pix.width()}x{pix.height()})")
            state["idx"] += 1
            QTimer.singleShot(400, capture_next)

        QTimer.singleShot(900, _shot)

    QTimer.singleShot(1200, capture_next)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
