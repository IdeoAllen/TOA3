# -*- coding: utf-8 -*-
"""统一异常记录与用户提示。"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import TypeVar

from PySide6.QtWidgets import QWidget

from core.audit_log import audit
from core.exceptions import TOAError, format_exception
from core.status_service import StatusLevel, report_error_status, report_status, report_warning_status
from core.user_messages import ask_confirm, show_error, show_info, show_warning

logger = logging.getLogger(__name__)

T = TypeVar("T")


def log_exception(exc: BaseException, *, context: str = "") -> None:
    prefix = f"[{context}] " if context else ""
    if isinstance(exc, TOAError):
        logger.error(
            "%s%s code=%s detail=%s",
            prefix,
            exc.__class__.__name__,
            exc.code,
            exc.detail or exc,
        )
        audit("异常", module=context, detail=f"{exc.code}: {exc.detail or exc}", level=logging.ERROR)
    else:
        logger.exception("%s%s", prefix, exc)
        audit("异常", module=context, detail=str(exc), level=logging.ERROR)


def report_error(
    parent: QWidget | None,
    exc: BaseException,
    *,
    title: str | None = None,
    context: str = "",
    log: bool = True,
    status: bool = True,
) -> None:
    if log:
        log_exception(exc, context=context)
    msg = format_exception(exc)
    show_error(parent, msg, title=title)
    if status and parent is not None:
        report_error_status(parent, msg, module_id=context)


def report_info(parent: QWidget | None, text: str, *, title: str | None = None) -> None:
    show_info(parent, text, title=title)
    report_status(parent, text, level=StatusLevel.INFO)


def report_warning(parent: QWidget | None, text: str, *, title: str | None = None) -> None:
    show_warning(parent, text, title=title)
    report_warning_status(parent, text)


def confirm(parent: QWidget | None, text: str, *, title: str | None = None) -> bool:
    return ask_confirm(parent, text, title=title)


def run_safe(
    fn: Callable[[], T],
    parent: QWidget | None = None,
    *,
    title: str | None = None,
    context: str = "",
    success_status: str | None = None,
    on_success: Callable[[T], None] | None = None,
) -> T | None:
    ctx = context or "run_safe"
    try:
        result = fn()
        if on_success:
            on_success(result)
        if success_status:
            report_status(parent, success_status, level=StatusLevel.SUCCESS, module_id=ctx)
        return result
    except TOAError as e:
        report_error(parent, e, title=title, context=ctx)
    except Exception as e:
        report_error(parent, e, title=title, context=ctx)
    return None


def install_qt_exception_hook() -> None:
    import sys

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        # Guest / 回调里 sys.exit 不得拖垮主进程
        if issubclass(exc_type, SystemExit):
            text = "".join(traceback.format_exception(exc_type, exc, tb))
            logger.critical("拦截 SystemExit（保持主窗）: %s\n%s", exc, text)
            audit("拦截SystemExit", detail=str(exc), level=logging.CRITICAL)
            return
        # WebEngine / shiboken 悬空：降级 warning，避免致命框刷屏拖垮体感
        msg = str(exc or "")
        if issubclass(exc_type, RuntimeError) and (
            "already deleted" in msg.lower()
            or "Internal C++ object" in msg
            or "wrapped C/C++ object" in msg
        ):
            text = "".join(traceback.format_exception(exc_type, exc, tb))
            logger.warning("已忽略失效 Qt 对象访问: %s\n%s", exc, text)
            audit("忽略失效Qt对象", detail=str(exc), level=logging.WARNING)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logger.critical("未捕获异常: %s\n%s", exc, text)
        audit("未捕获异常", detail=str(exc), level=logging.CRITICAL)

    sys.excepthook = _hook
