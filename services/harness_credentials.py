# -*- coding: utf-8 -*-
"""DSH 本机 API Key（.credentials.yaml）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from services.harness_config import dsh_home_path

_KEY_NAMES = ("DEEPSEEK_API_KEY", "deepseek_api_key", "api_key")


def credentials_path() -> Path:
    return dsh_home_path() / ".credentials.yaml"


def _read_raw() -> dict[str, Any]:
    path = credentials_path()
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _extract_key(data: dict[str, Any]) -> str:
    for name in _KEY_NAMES:
        val = data.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def has_api_key() -> bool:
    key = _extract_key(_read_raw())
    return len(key) >= 8


def mask_api_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "（未配置）"
    return k[:4] + "…" + k[-4:]


def masked_status() -> str:
    if not has_api_key():
        return "未配置"
    return mask_api_key(_extract_key(_read_raw()))


def save_api_key(key: str) -> tuple[bool, str]:
    k = (key or "").strip()
    if len(k) < 8:
        return False, "密钥太短，请粘贴完整的 DeepSeek API Key。"
    home = dsh_home_path()
    home.mkdir(parents=True, exist_ok=True)
    path = credentials_path()
    data = _read_raw()
    data["DEEPSEEK_API_KEY"] = k
    for alt in _KEY_NAMES:
        if alt != "DEEPSEEK_API_KEY" and alt in data:
            del data[alt]
    try:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        return False, str(exc)
    return True, "API Key 已保存到本机 DSH 配置目录。"


def open_credentials_hint() -> str:
    return str(credentials_path())
