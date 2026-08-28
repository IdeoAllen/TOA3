# -*- coding: utf-8 -*-
"""Harness token 用量与费用估算（小白可读）。"""
from __future__ import annotations

from typing import Any

from services.harness_config import load_harness_config, save_harness_config
from services.harness_store import status_snapshot


def _prices() -> tuple[float, float]:
    cfg = load_harness_config()
    try:
        inp = float(cfg.get("cost_input_per_million") or 2.0)
        out = float(cfg.get("cost_output_per_million") or 8.0)
    except (TypeError, ValueError):
        inp, out = 2.0, 8.0
    return inp, out


def save_price_config(input_per_m: float, output_per_m: float) -> None:
    save_harness_config(
        {
            "cost_input_per_million": round(float(input_per_m), 4),
            "cost_output_per_million": round(float(output_per_m), 4),
        }
    )


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    inp_p, out_p = _prices()
    return (max(0, input_tokens) / 1_000_000.0) * inp_p + (max(0, output_tokens) / 1_000_000.0) * out_p


def usage_summary() -> dict[str, Any]:
    snap = status_snapshot()
    usage = snap.get("usage") or {}
    inp = int(usage.get("inputTokens") or 0)
    out = int(usage.get("outputTokens") or 0)
    inp_p, out_p = _prices()
    cost = estimate_cost(inp, out)
    return {
        "status": snap,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read": int(usage.get("cacheReadTokens") or 0),
        "cache_write": int(usage.get("cacheWriteTokens") or 0),
        "max_context_pct": usage.get("maxContextPct"),
        "sessions": snap.get("sessions"),
        "workspaces": snap.get("workspaces"),
        "model": snap.get("model"),
        "cost_estimate": round(cost, 4),
        "input_price_per_m": inp_p,
        "output_price_per_m": out_p,
        "currency_label": str(load_harness_config().get("cost_currency") or "元"),
    }
