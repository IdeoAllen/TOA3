# -*- coding: utf-8 -*-
"""Harness 仪表格式化（时间、token 条形）。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any


def _to_epoch_ms(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e12:
            return v
        if v > 1e9:
            return v * 1000.0
        return v
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.isdigit():
            v = float(text)
            return v if v > 1e12 else v * 1000.0
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.timestamp() * 1000.0
    except (ValueError, OSError):
        return None


def human_ago(value: Any) -> str:
    ms = _to_epoch_ms(value)
    if ms is None:
        return ""
    delta = max(0.0, time.time() * 1000.0 - ms)
    if delta < 60_000:
        return "刚刚"
    if delta < 3600_000:
        return f"{int(delta / 60_000)} 分钟前"
    if delta < 86400_000:
        return f"{int(delta / 3600_000)} 小时前"
    return f"{int(delta / 86400_000)} 天前"


def spark_tokens(inp: int | float | None, out: int | float | None, width: int = 8) -> str:
    i = max(0, int(inp or 0))
    o = max(0, int(out or 0))
    total = i + o
    if total <= 0:
        return "·"
    fill = min(width, max(1, int(round((total / max(total, 1)) * width)))
    bar = "█" * fill + "░" * (width - fill)
    return f"{bar} ↑{i} ↓{o}"


def context_pct(session: dict[str, Any]) -> float | None:
    pct = session.get("contextPct")
    if pct is not None:
        try:
            return float(pct)
        except (TypeError, ValueError):
            pass
    cp = session.get("contextPressure")
    if isinstance(cp, dict):
        try:
            return float(cp.get("pct") or cp.get("percent") or 0)
        except (TypeError, ValueError):
            return None
    try:
        used = float(session.get("contextUsed") or 0)
        window = float(session.get("contextWindow") or 0)
        if window > 0:
            return round(used / window * 100.0, 1)
    except (TypeError, ValueError):
        pass
    return None
