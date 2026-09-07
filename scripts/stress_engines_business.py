#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎统一内嵌自测：Harness ↔ OpenPencil ↔ Draw.io ↔ 业务，不闪退。

用法：
  python scripts/stress_engines_business.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --disable-gpu-compositing",
)

ENGINES = ("harness_agent", "open_pencil", "drawio_web")
BUSINESS = ("schedule_reminder", "deduction_note_formatter")


def _pump(app, ms: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(max(0, int(ms)), loop.quit)
    loop.exec()


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from app.shell import MainShell
    from core.error_handler import install_qt_exception_hook
    from services.shared_local_webengine import current_owner_id, has_live_view

    install_qt_exception_hook()
    app = QApplication(sys.argv)
    shell = MainShell()
    shell.show()
    _pump(app, 600)
    errors: list[str] = []

    def visit(mid: str, wait: int = 1200) -> None:
        print(f"  → {mid}", flush=True)
        try:
            shell.navigate(mid)
        except Exception as e:
            errors.append(f"navigate({mid}): {e}")
            return
        _pump(app, wait)
        if mid in ENGINES:
            _pump(app, 800)

    try:
        print("--- engines round-robin ×2 ---")
        for _ in range(2):
            for mid in ENGINES:
                visit(mid, 1400)
            visit("system_settings", 600)

        print("--- engines → business ×3 ---")
        for _ in range(3):
            visit("drawio_web", 1200)
            visit("schedule_reminder", 1500)
            visit("harness_agent", 1400)
            visit("deduction_note_formatter", 800)

        print("--- shared owner check ---")
        visit("open_pencil", 1000)
        oid = current_owner_id()
        print(f"  owner={oid} live={has_live_view()}", flush=True)
        if oid not in ("open_pencil", "harness_agent", "drawio_web", None):
            errors.append(f"unexpected shared owner: {oid}")

        visit("home", 400)
        try:
            shell._purge_stale_web_embeds(except_mid=None)
        except Exception:
            pass
        from services.shared_local_webengine import shutdown

        shutdown()
        _pump(app, 500)
    except Exception as e:
        errors.append(f"top: {e}\n{traceback.format_exc()}")
    finally:
        try:
            shell.close()
        except Exception:
            pass
        _pump(app, 300)

    if errors:
        print("FAIL")
        for e in errors:
            print(" ", e)
        return 1
    print("STRESS ENGINES↔BUSINESS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
