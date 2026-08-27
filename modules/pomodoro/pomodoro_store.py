# -*- coding: utf-8 -*-
"""番茄钟：应用场景预设与个性化配色。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

_CACHE: dict[str, Any] | None = None

_BUILTIN_SCENARIOS: list[dict[str, Any]] = [
    {"id": "standard", "name": "标准专注", "work_min": 25, "break_min": 5, "builtin": True},
    {"id": "deep", "name": "深度工作", "work_min": 50, "break_min": 10, "builtin": True},
    {"id": "light", "name": "轻阅读", "work_min": 15, "break_min": 3, "builtin": True},
    {"id": "meeting", "name": "会议准备", "work_min": 10, "break_min": 2, "builtin": True},
]

_COLOR_PRESETS: list[tuple[str, str, str | None]] = [
    ("theme", "跟随主题", None),
    ("teal", "青绿", "#0D9488"),
    ("blue", "蓝色", "#2563EB"),
    ("purple", "紫色", "#7C3AED"),
    ("orange", "橙色", "#EA580C"),
    ("pink", "粉色", "#DB2777"),
    ("green", "绿色", "#16A34A"),
]


def color_presets() -> list[tuple[str, str, str | None]]:
    return list(_COLOR_PRESETS)


def _path() -> Path:
    return module_data_dir("pomodoro", create=True) / "settings.json"


def _normalize_scenario(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    sid = str(raw.get("id") or uuid.uuid4().hex[:10])
    work = max(1, min(120, int(raw.get("work_min") or 25)))
    brk = max(1, min(60, int(raw.get("break_min") or 5)))
    return {
        "id": sid,
        "name": name,
        "work_min": work,
        "break_min": brk,
        "builtin": bool(raw.get("builtin")),
    }


def load_settings() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = _path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                user = [
                    _normalize_scenario(x)
                    for x in raw.get("scenarios") or []
                    if isinstance(x, dict) and not x.get("builtin")
                ]
                user = [x for x in user if x]
                scenarios = [dict(x) for x in _BUILTIN_SCENARIOS] + user
                active = str(raw.get("active_scenario_id") or "standard")
                if not any(s["id"] == active for s in scenarios):
                    active = "standard"
                accent_key = str(raw.get("accent_key") or "theme")
                custom = str(raw.get("custom_accent") or "").strip()
                _CACHE = {
                    "scenarios": scenarios,
                    "active_scenario_id": active,
                    "accent_key": accent_key,
                    "custom_accent": custom,
                    "sessions_today": int(raw.get("sessions_today") or 0),
                    "sessions_date": str(raw.get("sessions_date") or ""),
                }
                return _CACHE
        except Exception:
            pass
    _CACHE = {
        "scenarios": [dict(x) for x in _BUILTIN_SCENARIOS],
        "active_scenario_id": "standard",
        "accent_key": "theme",
        "custom_accent": "",
        "sessions_today": 0,
        "sessions_date": "",
    }
    save_settings(_CACHE)
    return _CACHE


def save_settings(data: dict[str, Any]) -> None:
    global _CACHE
    user = [
        _normalize_scenario(x)
        for x in data.get("scenarios") or []
        if isinstance(x, dict) and not x.get("builtin")
    ]
    user = [x for x in user if x]
    payload = {
        "scenarios": [dict(x) for x in _BUILTIN_SCENARIOS] + user,
        "active_scenario_id": str(data.get("active_scenario_id") or "standard"),
        "accent_key": str(data.get("accent_key") or "theme"),
        "custom_accent": str(data.get("custom_accent") or "").strip(),
        "sessions_today": int(data.get("sessions_today") or 0),
        "sessions_date": str(data.get("sessions_date") or ""),
    }
    _CACHE = payload
    _path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_scenarios() -> list[dict[str, Any]]:
    return list(load_settings().get("scenarios") or [])


def get_scenario(scenario_id: str) -> dict[str, Any] | None:
    sid = str(scenario_id or "").strip()
    for s in list_scenarios():
        if str(s.get("id")) == sid:
            return s
    return None


def set_active_scenario(scenario_id: str) -> None:
    data = load_settings()
    sid = str(scenario_id or "").strip()
    if not get_scenario(sid):
        return
    data["active_scenario_id"] = sid
    save_settings(data)


def add_scenario(name: str, work_min: int, break_min: int) -> dict[str, Any]:
    data = load_settings()
    entry = _normalize_scenario(
        {
            "id": uuid.uuid4().hex[:10],
            "name": name,
            "work_min": work_min,
            "break_min": break_min,
            "builtin": False,
        }
    )
    if entry is None:
        raise ValueError("场景名称不能为空")
    scenarios = list(data.get("scenarios") or [])
    scenarios.append(entry)
    data["scenarios"] = scenarios
    data["active_scenario_id"] = entry["id"]
    save_settings(data)
    return entry


def update_scenario(scenario_id: str, *, name: str, work_min: int, break_min: int) -> None:
    sid = str(scenario_id or "").strip()
    data = load_settings()
    found = False
    out: list[dict[str, Any]] = []
    for item in data.get("scenarios") or []:
        if str(item.get("id")) != sid:
            out.append(item)
            continue
        if item.get("builtin"):
            raise ValueError("内置场景不可编辑")
        found = True
        out.append(
            _normalize_scenario(
                {
                    "id": sid,
                    "name": name,
                    "work_min": work_min,
                    "break_min": break_min,
                    "builtin": False,
                }
            )
            or item
        )
    if not found:
        raise ValueError("场景不存在")
    data["scenarios"] = out
    save_settings(data)


def delete_scenario(scenario_id: str) -> None:
    sid = str(scenario_id or "").strip()
    data = load_settings()
    target = get_scenario(sid)
    if target is None:
        return
    if target.get("builtin"):
        raise ValueError("内置场景不可删除")
    data["scenarios"] = [s for s in data.get("scenarios") or [] if str(s.get("id")) != sid]
    if str(data.get("active_scenario_id")) == sid:
        data["active_scenario_id"] = "standard"
    save_settings(data)


def set_accent(accent_key: str, *, custom_hex: str = "") -> None:
    data = load_settings()
    data["accent_key"] = str(accent_key or "theme")
    data["custom_accent"] = str(custom_hex or "").strip()
    save_settings(data)


def resolve_accent_hex() -> str | None:
    """None = 跟随主题 primary。"""
    data = load_settings()
    key = str(data.get("accent_key") or "theme")
    if key == "custom":
        custom = str(data.get("custom_accent") or "").strip()
        return custom if custom.startswith("#") and len(custom) >= 4 else None
    for kid, _label, hex_color in _COLOR_PRESETS:
        if kid == key:
            return hex_color
    return None


def bump_session_today() -> int:
    from datetime import date

    data = load_settings()
    today = date.today().isoformat()
    if str(data.get("sessions_date") or "") != today:
        data["sessions_today"] = 0
        data["sessions_date"] = today
    data["sessions_today"] = int(data.get("sessions_today") or 0) + 1
    save_settings(data)
    return int(data["sessions_today"])


def sessions_today() -> int:
    from datetime import date

    data = load_settings()
    today = date.today().isoformat()
    if str(data.get("sessions_date") or "") != today:
        return 0
    return int(data.get("sessions_today") or 0)
