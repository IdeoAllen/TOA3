# -*- coding: utf-8 -*-
"""Harness 会话钉选（本地 module_data）。"""
from __future__ import annotations

import json
from pathlib import Path

from services.storage_paths import module_data_dir

_PINS_FILE = "pinned_sessions.json"


def _path() -> Path:
    d = module_data_dir("harness_agent", create=True)
    return d / _PINS_FILE


def load_pins() -> list[str]:
    p = _path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_pins(ids: list[str]) -> None:
    p = _path()
    clean = []
    seen: set[str] = set()
    for raw in ids:
        sid = str(raw).strip()
        if sid and sid not in seen:
            seen.add(sid)
            clean.append(sid)
    p.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def is_pinned(session_id: str) -> bool:
    return session_id in load_pins()


def toggle_pin(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    pins = load_pins()
    if sid in pins:
        pins = [x for x in pins if x != sid]
        save_pins(pins)
        return False
    pins.insert(0, sid)
    save_pins(pins)
    return True
