#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEBUG 诊断：引擎 → 业务闪退路径，写满 breadcrumb 到日志。

另断言：
  - 切引擎后 painted_url 与目标引擎一致（防「侧栏 Harness、画面 Draw」）
  - Draw 注入 beforeunload 后再切 Harness 不被离开确认卡住

用法：
  python scripts/debug_engines_to_business.py

日志：
  common/logs/toa3.log
  common/logs/toa3_faulthandler.log
  common/logs/toa3_debug_session.log  （本脚本专拷）
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 在 import Qt 前打开 Chromium 啰嗦日志
os.environ.setdefault("QT_LOGGING_RULES", "qt.webenginecontext.debug=true")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--enable-logging --v=1 --disable-gpu --disable-gpu-compositing",
)

# 引擎 painted URL 须含对应端口（与 local_web_engines / harness 默认一致）
_ENGINE_PORT = {
    "harness_agent": "3082",
    "open_pencil": "1420",
    "drawio_web": "8080",
}


def _pump(app, ms: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(max(0, int(ms)), loop.quit)
    loop.exec()


def _assert_engine_paint(log, mid: str, errors: list[str]) -> None:
    from services.shared_local_webengine import current_owner_id, has_live_view, painted_url

    port = _ENGINE_PORT.get(mid)
    if not port:
        return
    if not has_live_view():
        # 服务未起时允许无 View；有 owner 却无 paint 则记警告
        log.warning("assert paint skip mid=%s no live view owner=%s", mid, current_owner_id())
        return
    painted = painted_url()
    owner = current_owner_id()
    log.info("assert paint mid=%s owner=%s painted=%s", mid, owner, painted)
    if owner != mid:
        errors.append(f"owner mismatch want={mid} got={owner}")
    if port not in (painted or ""):
        errors.append(
            f"painted URL 串引擎：want port {port} for {mid}, painted={painted!r}"
        )


def main() -> int:
    from app.logging_setup import setup_logging

    log_file = setup_logging(level=logging.DEBUG)
    session = Path(log_file).parent / "toa3_debug_session.log"
    # 会话副本 handler
    sess_h = logging.FileHandler(session, mode="w", encoding="utf-8")
    sess_h.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.getLogger().addHandler(sess_h)

    import faulthandler

    crash = Path(log_file).parent / "toa3_faulthandler.log"
    crash_fp = open(crash, "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(file=crash_fp, all_threads=True)

    log = logging.getLogger("TOA3.debug_session")
    log.info("======== DEBUG SESSION START pid=%s ========", os.getpid())
    log.info("log=%s session=%s fault=%s", log_file, session, crash)

    from core.error_handler import install_qt_exception_hook

    install_qt_exception_hook()

    from PySide6.QtWidgets import QApplication

    from app.shell import MainShell
    from services.shared_local_webengine import current_owner_id, has_live_view, painted_url

    app = QApplication(sys.argv)
    shell = MainShell()
    shell.show()
    _pump(app, 800)
    log.info("shell ready current=%s", shell._current_id)

    errors: list[str] = []
    steps = [
        ("harness_agent", 2000),
        ("open_pencil", 1800),
        ("drawio_web", 1800),
        ("schedule_reminder", 2500),
        ("deduction_note_formatter", 1000),
        ("drawio_web", 1500),
        ("schedule_reminder", 2500),
        ("home", 600),
    ]
    try:
        for mid, wait in steps:
            log.info(
                "STEP navigate→%s owner=%s live=%s leaving=%s",
                mid,
                current_owner_id(),
                has_live_view(),
                shell._current_id,
            )
            shell.navigate(mid)
            _pump(app, wait)
            log.info(
                "STEP done mid=%s current=%s owner=%s live=%s painted=%s",
                mid,
                shell._current_id,
                current_owner_id(),
                has_live_view(),
                painted_url(),
            )
            if mid in _ENGINE_PORT:
                _assert_engine_paint(log, mid, errors)

        # Draw 未保存离开确认：注入 beforeunload 再切 Harness，不得串画面
        log.info("STEP beforeunload trap drawio→harness")
        shell.navigate("drawio_web")
        _pump(app, 1800)
        try:
            from services.shared_local_webengine import has_live_view as _live
            from services.webengine_host import ToaWebEnginePage

            # 经 page 注入；无 View 则跳过（服务未起）
            if _live():
                from services.shared_local_webengine import live_view

                view = live_view()
                page = view.page() if view is not None else None
                if page is not None:
                    page.runJavaScript(
                        "window.onbeforeunload=function(e){"
                        "e.returnValue='unsaved';return 'unsaved';};"
                    )
                    _pump(app, 200)
                    if isinstance(page, ToaWebEnginePage):
                        # 下一拍 acquire 会 begin_forced；此处预检 API 存在
                        assert hasattr(page, "begin_forced_navigation")
        except Exception:
            log.exception("inject beforeunload failed")
            errors.append("inject beforeunload failed")

        shell.navigate("harness_agent")
        _pump(app, 2200)
        log.info(
            "STEP after beforeunload trap current=%s owner=%s painted=%s",
            shell._current_id,
            current_owner_id(),
            painted_url(),
        )
        if shell._current_id != "harness_agent":
            errors.append(f"after trap current={shell._current_id}")
        _assert_engine_paint(log, "harness_agent", errors)

        if errors:
            for e in errors:
                log.error("ASSERT FAIL: %s", e)
            log.info("======== DEBUG SESSION FAIL ========")
            rc = 1
        else:
            log.info("======== DEBUG SESSION OK ========")
            rc = 0
    except Exception:
        log.exception("DEBUG SESSION EXCEPTION")
        rc = 1
    finally:
        try:
            from services.shared_local_webengine import shutdown

            log.info("shutdown shared…")
            shutdown()
            _pump(app, 600)
            shell.close()
            _pump(app, 300)
        except Exception:
            log.exception("cleanup failed")
        log.info("======== DEBUG SESSION END rc=%s ========", rc)
        crash_fp.flush()

    print(f"session log: {session}")
    print(f"faulthandler: {crash}")
    return rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        raise
