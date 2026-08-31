# -*- coding: utf-8 -*-
"""模型展示：区域分组、下拉标签、摘要统计。"""
from __future__ import annotations

from typing import Any

_REGION_ORDER = ("cn", "intl", "local")
_REGION_HEADERS = {
    "cn": "国内 · 云端",
    "intl": "国外 · 云端",
    "local": "本机 · 平台",
}


def profile_region_code(prof: dict[str, Any]) -> str:
    explicit = str(prof.get("region") or "").strip().lower()
    if explicit in _REGION_HEADERS:
        return explicit
    origin = str(prof.get("origin") or "").strip().lower()
    provider = str(prof.get("provider") or "").strip().lower()
    tier = str(prof.get("tier") or "").strip().lower()
    api_base = str(prof.get("api_base") or "").lower()
    if origin == "local" or tier in ("simple", "advanced") or provider in (
        "sdcpp",
        "comfyui",
        "sd_webui",
    ):
        return "local"
    if "evolink" in provider or "openai.com" in api_base:
        return "intl"
    if (
        "volces.com" in api_base
        or "moonshot" in api_base
        or "deepseek" in api_base
        or "doubao" in str(prof.get("id") or "").lower()
    ):
        return "cn"
    return "intl"


def profile_combo_label(prof: dict[str, Any]) -> str:
    label = str(prof.get("label") or prof.get("id") or "")
    vendor = str(prof.get("vendor") or "").strip()
    if vendor and vendor not in label:
        return f"{label}（{vendor}）"
    return label


def group_profiles_for_combo(profiles: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any] | None]]:
    """返回 (display, profile|None)；profile=None 表示分组标题行。"""
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in _REGION_ORDER}
    for p in profiles:
        code = profile_region_code(p)
        buckets.setdefault(code, []).append(p)
    out: list[tuple[str, dict[str, Any] | None]] = []
    for code in _REGION_ORDER:
        rows = buckets.get(code) or []
        if not rows:
            continue
        out.append((_REGION_HEADERS.get(code, code), None))
        for prof in sorted(rows, key=lambda x: str(x.get("label") or "")):
            out.append((profile_combo_label(prof), prof))
    return out


def registry_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无模型条目。"
    ready = sum(1 for r in rows if str(r.get("status_code") or "") == "ready")
    cn = sum(1 for r in rows if r.get("region_code") == "cn")
    intl = sum(1 for r in rows if r.get("region_code") == "intl")
    local = sum(1 for r in rows if r.get("region_code") == "local")
    return (
        f"共 {len(rows)} 条 · 可用 {ready} · "
        f"国内 {cn} · 国外 {intl} · 本机 {local}"
    )


def is_evolink_image_profile(prof: dict[str, Any] | None, profile_id: str = "") -> bool:
    if not prof and not profile_id:
        return False
    pid = str(profile_id or prof.get("id") or "")
    provider = str((prof or {}).get("provider") or "")
    if pid == "evolink_grok_imagine" or provider == "evolink_images":
        return True
    return "evolink.ai" in str((prof or {}).get("api_base") or "")


def is_volcengine_image_profile(prof: dict[str, Any] | None, profile_id: str = "") -> bool:
    if not prof and not profile_id:
        return False
    base = str((prof or {}).get("api_base") or "").lower()
    model = str((prof or {}).get("model") or "").lower()
    return "volces.com" in base or "seedream" in model or "doubao" in model
