# -*- coding: utf-8 -*-
"""应用生命周期：完全退出 / 重启自身。"""
from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication

logger = logging.getLogger("TOA3.lifecycle")


def restart_process() -> bool:
    """拉起新进程；冻结包 cwd 必须为 exe 所在目录。"""
    try:
        from services.runtime_paths import get_app_root, is_frozen

        cwd = str(get_app_root())
        program = sys.executable
        if is_frozen():
            ok, pid = QProcess.startDetached(program, [], cwd)
        else:
            ok, pid = QProcess.startDetached(program, ["-m", "app.main"], cwd)
        if not ok:
            logger.error("重启启动失败: exe=%s cwd=%s", program, cwd)
            return False
        logger.info("已拉起新进程 pid=%s cwd=%s exe=%s", pid, cwd, program)
        return True
    except Exception:
        logger.exception("重启失败")
        return False


def quit_application(*, delay_ms: int = 0) -> None:
    """退出；delay_ms>0 时稍候再退，给新进程抢锁时间。"""
    app = QApplication.instance()

    def _do() -> None:
        if app is not None:
            app.quit()
        else:
            os._exit(0)

    if delay_ms > 0 and app is not None:
        QTimer.singleShot(delay_ms, _do)
    else:
        _do()
