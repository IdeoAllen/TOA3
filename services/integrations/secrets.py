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
