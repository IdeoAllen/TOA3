# -*- coding: utf-8 -*-
"""单实例：避免多开互相抢配置/托盘；可转发拖入文件路径。"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from services.drop_handoff import decode_ipc_message, encode_ipc_message

logger = logging.getLogger("TOA3.single_instance")

_SERVER: QLocalServer | None = None
_WIN_MUTEX = None

# on_second(paths: list[str]) — paths 为空表示仅激活
SecondInstanceHandler = Callable[[list[str]], None]


def _instance_key() -> str:
    try:
        from services.edition_isolation import instance_key

        return instance_key()
    except Exception:
        return "TOA3_YCZH_SINGLE_INSTANCE"


def _try_win_mutex() -> bool:
    """Windows 正式版：CreateMutex 防止双开（比 QLocalServer 更可靠）。"""
    global _WIN_MUTEX
    if sys.platform != "win32":
        return True
    try:
        from services.edition_isolation import app_mutex_name
        from services.runtime_paths import is_frozen

        if not is_frozen():
            return True
        import ctypes

        name = app_mutex_name()
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        err = ctypes.windll.kernel32.GetLastError()
        _WIN_MUTEX = handle
        if err == 183:  # ERROR_ALREADY_EXISTS
            logger.info("检测到已有 TOA3 正式版实例 (mutex=%s)", name)
            return False
        return True
    except Exception:
        logger.debug("Windows mutex 单实例不可用", exc_info=True)
        return True


def _ping_running_instance(key: str, *, paths: list[str] | None = None) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(key)
    if not sock.waitForConnected(400):
        return False
    try:
        payload = encode_ipc_message(paths)
        sock.write(payload)
        sock.flush()
        sock.waitForBytesWritten(800)
    except Exception:
        pass
    sock.disconnectFromServer()
    return True


def try_acquire_single_instance(
    app: QApplication,
    *,
    on_second: SecondInstanceHandler | Callable[[], None] | None = None,
    launch_paths: list[str] | None = None,
) -> bool:
    """
    若已有实例在跑：向其发激活/打开路径信号并返回 False。
    否则占用本地 server，返回 True。
    """
    global _SERVER
    key = _instance_key()
    path_list = [str(p) for p in (launch_paths or []) if str(p).strip()]

    if not _try_win_mutex():
        _ping_running_instance(key, paths=path_list or None)
        return False

    if _ping_running_instance(key, paths=path_list or None):
        logger.info("检测到已运行的 TOA3 实例，已请求激活/打开")
        return False

    server = QLocalServer()
    if not server.listen(key):
        # 仅 listen 失败时清理陈旧 socket（勿在「无实例」时 removeServer，会导致双开）
        QLocalServer.removeServer(key)
        if not server.listen(key):
            logger.warning("单实例监听失败: %s", server.errorString())
            return True
    _SERVER = server

    def _on_connection() -> None:
        client = server.nextPendingConnection()
        if client is None:
            return
        client.waitForReadyRead(600)
        data = bytes(client.readAll())
        # 大路径列表：再读一轮
        if data.startswith(b"open") and client.waitForReadyRead(200):
            data += bytes(client.readAll())
        client.close()
        cmd, paths = decode_ipc_message(data)
        if on_second is None:
            return
        try:
            # 兼容旧回调：无参仅激活
            import inspect

            try:
                n = len(inspect.signature(on_second).parameters)
            except (TypeError, ValueError):
                n = 1
            if n == 0:
                on_second()  # type: ignore[call-arg]
            else:
                on_second(paths if cmd == "open" else [])  # type: ignore[call-arg]
        except Exception:
            logger.debug("on_second failed", exc_info=True)

    server.newConnection.connect(_on_connection)
    return True


def release_single_instance() -> None:
    """退出/重启前释放本地锁，避免新进程误判「已有实例」。"""
    global _SERVER, _WIN_MUTEX
    if _SERVER is not None:
        key = _instance_key()
        try:
            _SERVER.close()
        except Exception:
            pass
        try:
            QLocalServer.removeServer(key)
        except Exception:
            pass
        _SERVER = None
    if _WIN_MUTEX is not None and sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(_WIN_MUTEX)
        except Exception:
            pass
        _WIN_MUTEX = None
