# -*- coding: utf-8 -*-
"""统一通知总线：状态栏 / 对话框 / 托盘 / 扩展通道。"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("TOA3.notify")

_HISTORY_MAX = 80
_HISTORY: deque[dict[str, str]] = deque(maxlen=_HISTORY_MAX)


class NotifyLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotifyBus(QObject):
    """进程内通知；壳与托盘订阅信号。"""

    license_changed = Signal()
    nav_rebuild_requested = Signal()
    status = Signal(str, str)  # text, level
    toast = Signal(str, str, str)  # title, body, level
    job_progress = Signal(str, str)  # job_id, message


_BUS: NotifyBus | None = None
_HANDLERS: list[Callable[..., Any]] = []


def get_bus() -> NotifyBus:
    global _BUS
    if _BUS is None:
        _BUS = NotifyBus()
    return _BUS


def recent_notifications(limit: int = 40) -> list[dict[str, str]]:
    """本会话最近通知（新→旧）；进程内缓冲，不落盘。"""
    n = max(0, int(limit or 0))
    items = list(_HISTORY)
    items.reverse()
    return items[:n] if n else items


def _record(level: str, title: str, body: str, channel: str) -> None:
    _HISTORY.append(
        {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "title": title or "",
            "body": body or "",
            "channel": channel or "status",
        }
    )


def notify(
    level: str | NotifyLevel = NotifyLevel.INFO,
    title: str = "",
    body: str = "",
    *,
    channel: str = "status",
    parent=None,
) -> None:
    """
    统一入口。
    channel: status | dialog | tray | email | all
    """
    lvl = level.value if isinstance(level, NotifyLevel) else str(level or "info")
    text = body or title
    bus = get_bus()
    _record(lvl, title, body, channel)

    if channel in ("status", "all"):
        bus.status.emit(text or title, lvl)
        try:
            from core.status_service import StatusLevel, report_status

            sl = {
                "info": StatusLevel.INFO,
                "success": StatusLevel.SUCCESS,
                "warning": StatusLevel.WARNING,
                "error": StatusLevel.ERROR,
            }.get(lvl, StatusLevel.INFO)
            report_status(parent, text or title, level=sl)
        except Exception:
            logger.debug("status bridge failed", exc_info=True)

    if channel in ("dialog", "all") and (title or body):
        try:
            from core.user_messages import show_error, show_info, show_warning

            msg = body or title
            if lvl == "error":
                show_error(parent, msg, title=title or None)
            elif lvl == "warning":
                show_warning(parent, msg, title=title or None)
            else:
                show_info(parent, msg, title=title or None)
        except Exception:
            logger.debug("dialog bridge failed", exc_info=True)

    if channel in ("tray", "all"):
        bus.toast.emit(title or "TOA", body or title, lvl)
        for h in list(_HANDLERS):
            try:
                h(title=title, body=body, level=lvl)
            except Exception:
                logger.debug("tray handler failed", exc_info=True)

    if channel in ("email", "all"):
        try:
            from services.notify_channels import send_email_notification

            # all：仅 warning/error 发邮件；channel=email：始终尝试
            if channel == "email" or lvl in ("error", "warning"):
                send_email_notification(title or "TOA", body or title)
        except Exception:
            logger.debug("email channel failed", exc_info=True)


def register_tray_handler(fn: Callable[..., Any]) -> None:
    if fn not in _HANDLERS:
        _HANDLERS.append(fn)


def emit_license_changed() -> None:
    bus = get_bus()
    bus.license_changed.emit()
    bus.nav_rebuild_requested.emit()


def request_nav_rebuild() -> None:
    get_bus().nav_rebuild_requested.emit()
