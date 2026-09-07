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
    """先清理同款旧实例，再拉起新进程；冻结包 cwd 必须为 exe 所在目录。

    禁止「只启不杀」：否则会叠多个 python -m app.main / 多窗看旧配置。
    """
    try:
        from services.runtime_paths import get_app_root, is_frozen

        frozen = is_frozen()
        _kill_sibling_app_instances(frozen=frozen)
        cwd = str(get_app_root())
        program = sys.executable
        if frozen:
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


def _kill_sibling_app_instances(*, frozen: bool) -> int:
    """结束其它 TOA 主进程（保留当前 pid）。开发态杀 python -m app.main；冻结包杀同名 exe。"""
    me = os.getpid()
    killed = 0
    if sys.platform != "win32":
        return 0
    try:
        import subprocess

        if frozen:
            exe_name = os.path.basename(sys.executable)
            where = f"name='{exe_name}'"
        else:
            where = "name='python.exe' or name='pythonw.exe'"
        out = subprocess.check_output(
            [
                "wmic",
                "process",
                "where",
                where,
                "get",
                "ProcessId,CommandLine",
                "/FORMAT:LIST",
            ],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=15,
        )
    except Exception:
        logger.debug("枚举 TOA 进程失败", exc_info=True)
        return 0

    def _flush(pid: int | None, cmd: str) -> int:
        if not pid or pid == me:
            return 0
        if not frozen:
            low = (cmd or "").lower().replace(" ", "")
            if "-m" not in (cmd or "").lower() or "app.main" not in low:
                return 0
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=12,
            )
            logger.info("重启前结束旧 TOA 实例 pid=%s", pid)
            return 1
        except Exception:
            logger.debug("无法结束 pid=%s", pid, exc_info=True)
            return 0

    cur_pid: int | None = None
    cur_cmd = ""
    for raw in out.splitlines():
        line = raw.strip()
        if not line:
            killed += _flush(cur_pid, cur_cmd)
            cur_pid = None
            cur_cmd = ""
            continue
        if line.startswith("CommandLine="):
            cur_cmd = line[len("CommandLine=") :]
        elif line.startswith("ProcessId="):
            try:
                cur_pid = int(line[len("ProcessId=") :].strip() or "0")
            except ValueError:
                cur_pid = None
    killed += _flush(cur_pid, cur_cmd)
    return killed


# 兼容旧调用名
def _kill_sibling_app_mains() -> int:
    from services.runtime_paths import is_frozen

    return _kill_sibling_app_instances(frozen=is_frozen())


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
