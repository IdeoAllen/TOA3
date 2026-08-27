# -*- coding: utf-8 -*-
"""用户可维护的系统信息（覆盖 app.yml 默认值）。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from services.config_service import resolve_path

logger = logging.getLogger(__name__)

MAINTAINABLE_FIELDS = (
    "brand_name",
    "brand_alias",
    "brand_abbreviation",
    "brand_name_en",
    "author",
    "author_email",
    "slogan",
    "slogan_subtitle",
    "app_logo_path",
)


def user_system_info_path() -> Path:
    return resolve_path("data_dir") / "user" / "system_info.json"


def load_user_overrides() -> dict[str, Any]:
    path = user_system_info_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {k: raw[k] for k in MAINTAINABLE_FIELDS if k in raw and raw[k] is not None}
    except Exception as e:
        logger.warning("读取用户系统信息失败: %s", e)
    return {}


def save_user_overrides(data: dict[str, Any]) -> Path:
    path = user_system_info_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {k: str(data.get(k) or "").strip() for k in MAINTAINABLE_FIELDS}
    # 去掉空字符串键，保留显式清空需另处理；此处空串表示不覆盖
    payload = {k: v for k, v in cleaned.items() if v}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已保存用户系统信息: %s", path)
    return path


def clear_user_overrides() -> None:
    path = user_system_info_path()
    if path.is_file():
        path.unlink()
