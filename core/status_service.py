# -*- coding: utf-8 -*-
"""统一状态提示：状态栏分级 + 日志。"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QWidget

logger = logging.getLogger("TOA3.status")


class StatusLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    READY = "ready"


_PREFIX = {
    StatusLevel.INFO: "",
    StatusLevel.SUCCESS: "✓ ",
    StatusLevel.WARNING: "⚠ ",
    StatusLevel.ERROR: "✗ ",
    StatusLevel.READY: "",
}


def _find_shell(widget: QWidget | None):
    if widget is None:
        return None
    win = widget.window()
    if win is not None and hasattr(win, "show_status"):
        return win
    return None


def report_status(
    source: QWidget | None,
    message: str,
    *,
    level: StatusLevel = StatusLevel.INFO,
    module_id: str = "",
    log: bool = True,
) -> None:
    text = str(message or "").strip()
    if not text:
        return
    display = f"{_PREFIX.get(level, '')}{text}"
    ctx = module_id or (source.__class__.__name__ if source else "")
    if log:
        lvl = logging.INFO
        if level == StatusLevel.WARNING:
            lvl = logging.WARNING
        elif level == StatusLevel.ERROR:
            lvl = logging.ERROR
        logger.log(lvl, "[%s] %s", ctx, text)

    shell = _find_shell(source)
    if shell is not None:
        shell.show_status(display, level=level)
    elif log:
        logger.info("无壳状态栏: %s", display)


def report_success(source: QWidget | None, message: str, **kwargs) -> None:
    report_status(source, message, level=StatusLevel.SUCCESS, **kwargs)


def report_warning_status(source: QWidget | None, message: str, **kwargs) -> None:
    report_status(source, message, level=StatusLevel.WARNING, **kwargs)


def report_error_status(source: QWidget | None, message: str, **kwargs) -> None:
    report_status(source, message, level=StatusLevel.ERROR, **kwargs)
