# -*- coding: utf-8 -*-
"""本地买家信息缓存：减少重复填写手机号。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from services.runtime_paths import get_user_data_root


def _profile_path() -> Path:
    return get_user_data_root() / "commerce_profile.yml"


def load_profile() -> dict[str, str]:
    path = _profile_path()
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "name": str(data.get("name") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
    }


def save_profile(*, name: str = "", phone: str = "") -> None:
    name = str(name or "").strip()
    phone = str(phone or "").strip()
    if not name and not phone:
        return
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_profile()
    if name:
        current["name"] = name
    if phone:
        current["phone"] = phone
    path.write_text(
        yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def merge_buyer_profile(info: dict[str, Any] | None = None) -> dict[str, str]:
    """license 信息 + 本地缓存 → 姓名/手机号。"""
    from services.subscription_renew import renew_profile

    base = renew_profile(info if isinstance(info, dict) else None)
    cached = load_profile()
    if not base.get("name") and cached.get("name"):
        base["name"] = cached["name"]
    if not base.get("phone") and cached.get("phone"):
        base["phone"] = cached["phone"]
    if not base.get("name"):
        base["name"] = "用户"
    return base
