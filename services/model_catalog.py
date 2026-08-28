# -*- coding: utf-8 -*-
"""能力模型目录：同一能力多配置、任务页切换。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from services.config_service import project_root

_CACHE: dict[str, Any] | None = None

_TEXT_LLM = "text_llm"
_IMAGE_GEN = "image_gen"


def _user_catalog_path() -> Path:
    p = project_root() / "data" / "user" / "model_catalog.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_base_catalog() -> dict[str, Any]:
    path = project_root() / "config" / "model_catalog.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _load_user_catalog() -> dict[str, Any]:
    path = _user_catalog_path()
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_model_catalog(force: bool = False) -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    base = deepcopy(_load_base_catalog())
    user = _load_user_catalog()
    caps = dict(base.get("capabilities") or {})
    user_caps = user.get("capabilities") or {}
    if isinstance(user_caps, dict):
        for cap_id, block in user_caps.items():
            if not isinstance(block, dict):
                continue
            merged = dict(caps.get(cap_id) or {})
            profiles = dict(merged.get("profiles") or {})
            user_profiles = block.get("profiles") or {}
            if isinstance(user_profiles, dict):
                for pid, prof in user_profiles.items():
                    if isinstance(prof, dict):
                        cur = dict(profiles.get(pid) or {})
                        cur.update(prof)
                        profiles[pid] = cur
            merged["profiles"] = profiles
            if block.get("default_profile"):
                merged["default_profile"] = block["default_profile"]
            if block.get("label"):
                merged["label"] = block["label"]
            caps[cap_id] = merged
    active = dict(user.get("active") or {})
    _CACHE = {"capabilities": caps, "active": active}
    return _CACHE


def list_capabilities() -> list[str]:
    caps = load_model_catalog().get("capabilities") or {}
    return sorted(caps.keys())


def list_profiles(capability: str) -> list[dict[str, Any]]:
    cap = _cap_block(capability)
    profiles = cap.get("profiles") or {}
    out: list[dict[str, Any]] = []
    if isinstance(profiles, dict):
        for pid, prof in profiles.items():
            if not isinstance(prof, dict):
                continue
            row = dict(prof)
            row["id"] = str(pid)
            row.setdefault("label", pid)
            out.append(row)
    out.sort(key=lambda x: str(x.get("label") or x.get("id")))
    return out


def get_active_profile_id(capability: str) -> str:
    cat = load_model_catalog()
    active = cat.get("active") or {}
    if isinstance(active, dict) and active.get(capability):
        return str(active[capability]).strip()
    cap = _cap_block(capability)
    return str(cap.get("default_profile") or "").strip()


def set_active_profile_id(capability: str, profile_id: str) -> Path:
    pid = str(profile_id or "").strip()
    if not pid:
        raise ValueError("profile_id 为空")
    user = _load_user_catalog()
    active = dict(user.get("active") or {})
    active[capability] = pid
    user["active"] = active
    path = _user_catalog_path()
    path.write_text(
        yaml.safe_dump(user, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    load_model_catalog(force=True)
    return path


def resolve_profile(capability: str, profile_id: str | None = None) -> dict[str, Any]:
    pid = str(profile_id or "").strip() or get_active_profile_id(capability)
    cap = _cap_block(capability)
    profiles = cap.get("profiles") or {}
    if not isinstance(profiles, dict) or pid not in profiles:
        raise KeyError(f"未找到模型配置：{capability}/{pid}")
    prof = dict(profiles[pid])
    prof["id"] = pid
    prof["capability"] = capability
    return prof


def resolve_text_llm_profile(profile_id: str | None = None) -> dict[str, Any]:
    return resolve_profile(_TEXT_LLM, profile_id)


def resolve_image_gen_profile(profile_id: str | None = None) -> dict[str, Any]:
    return resolve_profile(_IMAGE_GEN, profile_id)


def _cap_block(capability: str) -> dict[str, Any]:
    caps = load_model_catalog().get("capabilities") or {}
    block = caps.get(capability) or {}
    return block if isinstance(block, dict) else {}


def save_user_profile_patch(
    capability: str,
    profile_id: str,
    patch: dict[str, Any],
) -> Path:
    """合并写入用户自定义 profile 字段（不含密钥）。"""
    pid = str(profile_id or "").strip()
    if not pid:
        raise ValueError("profile_id 为空")
    user = _load_user_catalog()
    caps = dict(user.get("capabilities") or {})
    cap_block = dict(caps.get(capability) or {})
    profiles = dict(cap_block.get("profiles") or {})
    cur = dict(profiles.get(pid) or {})
    clean = {k: v for k, v in patch.items() if k not in ("api_key", "id")}
    cur.update(clean)
    profiles[pid] = cur
    cap_block["profiles"] = profiles
    caps[capability] = cap_block
    user["capabilities"] = caps
    path = _user_catalog_path()
    path.write_text(
        yaml.safe_dump(user, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    load_model_catalog(force=True)
    return path
