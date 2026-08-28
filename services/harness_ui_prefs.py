# -*- coding: utf-8 -*-
"""编码智能体页 UI 偏好（不碰 Harness 业务）。"""
from __future__ import annotations

import json
from pathlib import Path

from services.storage_paths import module_data_dir

_PREFS_FILE = "ui_prefs.json"


def _path() -> Path:
    return module_data_dir("harness_agent", create=True) / _PREFS_FILE


def load_ui_prefs() -> dict:
    p = _path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_ui_prefs(**updates: bool) -> None:
    cur = load_ui_prefs()
    for k, v in updates.items():
        cur[k] = bool(v)
    _path().write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
