# -*- coding: utf-8 -*-
"""DeepSeek Harness 本地 Sidecar 配置加载。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from services.config_service import project_root

_CACHE: dict | None = None


def _user_harness_path() -> Path:
    try:
        from services.runtime_paths import get_user_data_root, prefer_user_writable_paths

        if prefer_user_writable_paths():
            p = get_user_data_root() / "config" / "harness.yml"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return project_root() / "data" / "user" / "harness.yml"


def load_harness_config(force: bool = False) -> dict:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    merged: dict[str, Any] = {}
    path = project_root() / "config" / "harness.yml"
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            block = data.get("harness") or data
            if isinstance(block, dict):
                merged.update(block)
    user_path = _user_harness_path()
    if user_path.is_file():
        data = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            block = data.get("harness") or data
            if isinstance(block, dict):
                merged.update(block)
    _CACHE = merged
    return _CACHE


def harness_enabled() -> bool:
    return bool(load_harness_config().get("enabled", True))


def save_harness_config(updates: dict[str, Any]) -> Path:
    """写入用户 harness.yml（仅非密钥字段）。"""
    global _CACHE
    user_path = _user_harness_path()
    user_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_harness_config(force=True)
    current.update({k: v for k, v in updates.items() if v is not None})
    user_path.write_text(
        yaml.safe_dump({"harness": current}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _CACHE = None
    return user_path


def resolve_harness_path(key: str, default: str = "") -> Path:
    raw = str(load_harness_config().get(key) or default).strip()
    if not raw:
        return Path()
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    try:
        return p.resolve()
    except OSError:
        return p


def web_url() -> str:
    port = int(load_harness_config().get("web_port") or 3081)
    return f"http://127.0.0.1:{port}"


def dshm_script_path() -> Path:
    return resolve_harness_path("dshm_script", "vendor/dshm/bin/dshm.js")


def node_exe_path() -> Path:
    return resolve_harness_path("node_exe", "")


def dsh_bin_path() -> Path:
    return resolve_harness_path("dsh_bin", "")


def dsh_home_path() -> Path:
    return resolve_harness_path("dsh_home", "")
