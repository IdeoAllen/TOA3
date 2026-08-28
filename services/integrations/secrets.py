# -*- coding: utf-8 -*-
"""本地密钥（不进仓库）：data/user/integrations_secrets.json。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from services.config_service import project_root

logger = logging.getLogger(__name__)


def _secrets_path() -> Path:
    path = project_root() / "data" / "user" / "integrations_secrets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_secrets() -> dict[str, Any]:
    path = _secrets_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.debug("load secrets failed", exc_info=True)
        return {}


def save_secrets(data: dict[str, Any]) -> Path:
    path = _secrets_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def get_secret(integration: str, key: str = "api_key") -> str:
    block = load_secrets().get(integration) or {}
    if isinstance(block, dict):
        return str(block.get(key) or "").strip()
    return ""


_LEGACY_TEXT_LLM_PROFILE = "moonshot_kimi"


def _text_llm_allows_legacy_fallback(profile_id: str) -> bool:
    """旧版 integrations_secrets 仅 llm 桶 → 只绑定 Moonshot 默认配置。"""
    pid = (profile_id or "").strip()
    return not pid or pid == _LEGACY_TEXT_LLM_PROFILE


def get_profile_secret(
    capability: str,
    profile_id: str,
    key: str = "api_key",
    *,
    allow_legacy_fallback: bool | None = None,
) -> str:
    """按能力+配置 id 读取密钥（profiles 桶）。"""
    data = load_secrets()
    profiles = data.get("profiles") or {}
    if not isinstance(profiles, dict):
        profiles = {}
    slot = f"{capability}:{profile_id}"
    block = profiles.get(slot) or {}
    if isinstance(block, dict):
        val = str(block.get(key) or "").strip()
        if val:
            return val
    if capability == "text_llm":
        use_legacy = (
            allow_legacy_fallback
            if allow_legacy_fallback is not None
            else _text_llm_allows_legacy_fallback(profile_id)
        )
        if use_legacy:
            return get_secret("llm", key)
        return ""
    if capability == "image_gen":
        return get_secret("image_gen", key)
    return ""


def set_profile_secret(capability: str, profile_id: str, key: str, value: str) -> Path:
    data = load_secrets()
    profiles = dict(data.get("profiles") or {}) if isinstance(data.get("profiles"), dict) else {}
    slot = f"{capability}:{profile_id}"
    block = dict(profiles.get(slot) or {}) if isinstance(profiles.get(slot), dict) else {}
    val = str(value or "").strip()
    if val:
        block[key] = val
    else:
        block.pop(key, None)
    if block:
        profiles[slot] = block
    else:
        profiles.pop(slot, None)
    if profiles:
        data["profiles"] = profiles
    else:
        data.pop("profiles", None)
    return save_secrets(data)


def set_secret(integration: str, key: str, value: str) -> Path:
    data = load_secrets()
    block = dict(data.get(integration) or {}) if isinstance(data.get(integration), dict) else {}
    val = str(value or "").strip()
    if val:
        block[key] = val
    else:
        block.pop(key, None)
    if block:
        data[integration] = block
    else:
        data.pop(integration, None)
    return save_secrets(data)
