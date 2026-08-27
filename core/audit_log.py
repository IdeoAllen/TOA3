# -*- coding: utf-8 -*-
"""结构化操作日志（人机排错）。"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

_audit = logging.getLogger("TOA3.audit")


def audit(action: str, *, module: str = "", detail: str = "", level: int = logging.INFO) -> None:
    parts = [p for p in (module, action, detail) if p]
    _audit.log(level, " | ".join(parts))


@contextmanager
def log_action(module: str, action: str, *, detail: str = "") -> Iterator[None]:
    audit(action, module=module, detail=detail or "开始")
    try:
        yield
        audit(action, module=module, detail="完成")
    except Exception as e:
        audit(action, module=module, detail=f"失败: {e}", level=logging.ERROR)
        raise
