# -*- coding: utf-8 -*-
"""模型注册表视图：合并 catalog + 就绪状态，供设置页表格展示。"""
from __future__ import annotations

from typing import Any

from services.integrations.secrets import get_profile_secret
from services.model_catalog import get_active_profile_id, list_capabilities, list_profiles
from services.model_ready_registry import (
    ReadyStatus,
    _is_local_endpoint,
    evaluate_profile,
    list_ready,
    scan_local_weight_files,
)

_CAPABILITY_TYPE_LABELS: dict[str, str] = {
    "text_llm": "文本",
    "image_gen": "图片",
    "video_gen": "视频",
    "audio_gen": "音频",
    "speech": "音频",
}

_LOCAL_PROVIDERS = frozenset({"sd_webui", "ollama", "local_weight"})


def _supplier_label(
    provider: str,
    api_base: str,
    profile_id: str = "",
    label: str = "",
) -> str:
    """供应商展示：本地 / DeepSeek / OpenAI / Moonshot …"""
    p = str(provider or "").strip().lower()
    base = str(api_base or "").strip().lower()
    pid = str(profile_id or "").strip().lower()
    lab = str(label or "").strip().lower()

    if p == "comfyui" or pid == "comfyui_local":
        return "—"

    if p in _LOCAL_PROVIDERS or p == "local_weight":
        return "本地"
    if base and _is_local_endpoint(api_base):
        return "本地"

    if "deepseek" in base or "deepseek" in pid or "deepseek" in lab:
        return "DeepSeek"
    if "moonshot" in base or "moonshot" in pid or "kimi" in pid or "kimi" in lab:
        return "Moonshot"
    if p == "openai_images" or "openai.com" in base or "openai" in pid:
        return "OpenAI"
    if p == "openai_compatible":
        if "deepseek" in base:
            return "DeepSeek"
        if "moonshot" in base:
            return "Moonshot"
        if "openai" in base:
            return "OpenAI"
        return "OpenAI"

    if base:
        return "OpenAI"
    return "—"


def _has_key(capability: str, profile_id: str) -> bool:
    return bool(get_profile_secret(capability, profile_id, "api_key"))


def _skip_profile(provider: str, profile_id: str) -> bool:
    p = str(provider or "").strip().lower()
    pid = str(profile_id or "").strip().lower()
    return p == "comfyui" or pid == "comfyui_local"


def build_registry_rows(
    *,
    capability_filter: str | None = None,
    ready_only: bool = False,
) -> list[dict[str, Any]]:
    """扁平化模型行，供「模型管理」表格使用。"""
    caps = [capability_filter] if capability_filter else list_capabilities()
    rows: list[dict[str, Any]] = []

    for cap in caps:
        active_id = get_active_profile_id(cap)
        type_label = _CAPABILITY_TYPE_LABELS.get(cap, cap)
        for prof in list_profiles(cap):
            pid = str(prof.get("id") or "")
            if not pid:
                continue
            provider = str(prof.get("provider") or "")
            if _skip_profile(provider, pid):
                continue
            evaluated = evaluate_profile(cap, pid, prof)
            api_base = str(prof.get("api_base") or evaluated.get("api_base") or "")
            provider = str(prof.get("provider") or evaluated.get("provider") or "")
            model = str(prof.get("model") or evaluated.get("model") or "")
            label = str(prof.get("label") or pid)
            status = str(evaluated.get("status") or "")
            if ready_only and status != ReadyStatus.READY:
                continue
            rows.append(
                {
                    "capability": cap,
                    "profile_id": pid,
                    "label": label,
                    "vendor": _supplier_label(provider, api_base, pid, label),
                    "type": type_label,
                    "url": api_base,
                    "model": model,
                    "status": str(evaluated.get("status_label") or ""),
                    "status_code": status,
                    "key": "已配置" if _has_key(cap, pid) else "未配置",
                    "is_default": pid == active_id,
                    "provider": provider,
                    "hint": str(evaluated.get("hint") or ""),
                    "catalog": True,
                }
            )

        if cap == "image_gen":
            for item in scan_local_weight_files():
                if ready_only and item.get("status") != ReadyStatus.READY:
                    continue
                rows.append(
                    {
                        "capability": "image_gen",
                        "profile_id": str(item.get("id") or ""),
                        "label": str(item.get("label") or "本机权重"),
                        "vendor": "本地",
                        "type": "图片",
                        "url": str(item.get("local_path") or ""),
                        "model": str(item.get("label") or ""),
                        "status": str(item.get("status_label") or "可用"),
                        "status_code": str(item.get("status") or ReadyStatus.READY),
                        "key": "—",
                        "is_default": False,
                        "provider": "local_weight",
                        "hint": str(item.get("hint") or ""),
                        "catalog": False,
                    }
                )

    rows.sort(key=lambda r: (r.get("type") or "", r.get("label") or ""))
    return rows


def ready_count_by_capability() -> dict[str, int]:
    out: dict[str, int] = {}
    for cap in list_capabilities():
        out[cap] = len(list_ready(cap, ready_only=True))
    return out
