# -*- coding: utf-8 -*-
"""Harness 升级弱提示：今日不提醒落盘（按日历日 + 目标版本）。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

_MODULE = "harness_agent"
_FILE = "upgrade_nudge.json"


def _path() -> Path:
    return module_data_dir(_MODULE, create=True) / _FILE


def _load() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_snoozed_today(available_version: str) -> bool:
    """今日已选「今日不提醒」且目标版本未变 → 不再弹。"""
    ver = str(available_version or "").strip()
    if not ver:
        return False
    data = _load()
    return (
        str(data.get("snooze_date") or "") == date.today().isoformat()
        and str(data.get("available_version") or "") == ver
    )


def snooze_today(available_version: str) -> None:
    ver = str(available_version or "").strip()
    if not ver:
        return
    _save(
        {
            "snooze_date": date.today().isoformat(),
            "available_version": ver,
        }
    )


def clear_snooze() -> None:
    path = _path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
