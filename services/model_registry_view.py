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

_REGION_LABELS: dict[str, str] = {
    "cn": "国内",
    "intl": "国外",
    "local": "本机",
}

_ORIGIN_LABELS: dict[str, str] = {
    "cloud": "云端 API",
    "local": "本机平台",
}

_LOCAL_PROVIDERS = frozenset({"sd_webui", "ollama", "local_weight", "sdcpp", "comfyui"})


def _supplier_label(
    provider: str,
    api_base: str,
    profile_id: str = "",
    label: str = "",
    *,
    vendor: str = "",
) -> str:
    """供应商展示：优先 catalog vendor 字段。"""
    if str(vendor or "").strip():
        return str(vendor).strip()
    p = str(provider or "").strip().lower()
    base = str(api_base or "").strip().lower()
    pid = str(profile_id or "").strip().lower()
    lab = str(label or "").strip().lower()

    if p in ("sdcpp", "comfyui", "sd_webui", "local_weight") or p in _LOCAL_PROVIDERS:
        if p == "comfyui":
            return "ComfyUI"
        if p == "sd_webui":
            return "SD WebUI"
        if p == "sdcpp":
            return "本机 SDCPP"
        return "本地"
    if base and _is_local_endpoint(api_base):
        return "Ollama" if "11434" in base else "本地"

    if p in ("evolink_images", "evolink_seedance") or "evolink.ai" in base:
        return "Evolink"
    if "deepseek" in base or "deepseek" in pid or "deepseek" in lab:
        return "DeepSeek"
    if "moonshot" in base or "moonshot" in pid or "kimi" in pid or "kimi" in lab:
        return "Moonshot"
    if (
        "volces.com" in base
        or "doubao" in pid
        or "seedream" in pid
        or "seedance" in pid
        or "doubao" in lab
        or "seedream" in lab
        or "seedance" in lab
    ):
        return "火山方舟"
    if "mxapi.org" in base or pid.startswith("mxapi_") or "mxapi" in lab:
        return "MXAPI"
    if p == "openai_images" or "openai.com" in base or "openai" in pid:
        return "OpenAI"
    if p == "openai_compatible":
        if "deepseek" in base:
            return "DeepSeek"
        if "moonshot" in base:
            return "Moonshot"
        if "openai" in base:
            return "OpenAI"
        return "OpenAI 兼容"

    if base:
        return "OpenAI 兼容"
    return "—"


def _region_code(prof: dict[str, Any], *, provider: str, api_base: str, pid: str, label: str) -> str:
    explicit = str(prof.get("region") or "").strip().lower()
    if explicit in _REGION_LABELS:
        return explicit
    p = str(provider or "").lower()
    base = str(api_base or "").lower()
    if p in _LOCAL_PROVIDERS or prof.get("origin") == "local" or _is_local_endpoint(api_base):
        return "local"
    if "evolink.ai" in base or p.startswith("evolink") or "openai.com" in base:
        return "intl"
    if (
        "volces.com" in base
        or "moonshot" in base
        or "deepseek" in base
        or "doubao" in str(pid).lower()
    ):
        return "cn"
    return "intl"


def _origin_code(prof: dict[str, Any], *, provider: str) -> str:
    explicit = str(prof.get("origin") or "").strip().lower()
    if explicit in _ORIGIN_LABELS:
        return explicit
    p = str(provider or "").lower()
    tier = str(prof.get("tier") or "").lower()
    if p in _LOCAL_PROVIDERS or tier in ("simple", "advanced") or p == "local_weight":
        return "local"
    return "cloud"


def _has_key(capability: str, profile_id: str) -> bool:
    if get_profile_secret(capability, profile_id, "api_key"):
        return True
    if capability == "image_gen" and str(profile_id).startswith("mxapi_"):
        from services.model_ready_registry import _mxapi_key_present

        return _mxapi_key_present()
    if capability == "image_gen" and profile_id == "evolink_grok_imagine":
        return bool(get_profile_secret("video_gen", "evolink_seedance_2", "api_key"))
    if capability == "video_gen" and profile_id == "evolink_seedance_2":
        return bool(get_profile_secret("image_gen", "evolink_grok_imagine", "api_key"))
    return False


def _skip_profile(provider: str, profile_id: str) -> bool:
    return False


def build_registry_rows(
    *,
    capability_filter: str | None = None,
    origin_filter: str | None = None,
    region_filter: str | None = None,
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
            region = _region_code(prof, provider=provider, api_base=api_base, pid=pid, label=label)
            origin = _origin_code(prof, provider=provider)
            if origin_filter and origin != origin_filter:
                continue
            if region_filter and region != region_filter:
                continue
            vendor = _supplier_label(
                provider,
                api_base,
                pid,
                label,
                vendor=str(prof.get("vendor") or ""),
            )
            endpoint = api_base
            if origin == "local" and not endpoint:
                wf = str(prof.get("workflow") or "").strip()
                endpoint = wf or str(prof.get("note") or "本机")[:40]
            rows.append(
                {
                    "capability": cap,
                    "profile_id": pid,
                    "label": label,
                    "vendor": vendor,
                    "region": _REGION_LABELS.get(region, region),
                    "region_code": region,
                    "origin": _ORIGIN_LABELS.get(origin, origin),
                    "origin_code": origin,
                    "type": type_label,
                    "url": endpoint,
                    "model": model or str(prof.get("workflow") or "—"),
                    "status": str(evaluated.get("status_label") or ""),
                    "status_code": status,
                    "key": "已配置" if _has_key(cap, pid) else "未配置",
                    "is_default": pid == active_id,
                    "provider": provider,
                    "tier": str(prof.get("tier") or ""),
                    "hint": str(evaluated.get("hint") or prof.get("note") or ""),
                    "catalog": True,
                    "price_hint": str(prof.get("price_hint") or ""),
                }
            )

        if cap == "image_gen":
            for item in scan_local_weight_files():
                if ready_only and item.get("status") != ReadyStatus.READY:
                    continue
                if origin_filter == "cloud":
                    continue
                if region_filter == "intl":
                    continue
                rows.append(
                    {
                        "capability": "image_gen",
                        "profile_id": str(item.get("id") or ""),
                        "label": str(item.get("label") or "本机权重"),
                        "vendor": "本机文件",
                        "region": "本机",
                        "region_code": "local",
                        "origin": "本机平台",
                        "origin_code": "local",
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
                        "price_hint": "",
                    }
                )

    rows.sort(
        key=lambda r: (
            r.get("origin_code") or "",
            r.get("region_code") or "",
            r.get("type") or "",
            r.get("label") or "",
        )
    )
    return rows


def ready_count_by_capability() -> dict[str, int]:
    out: dict[str, int] = {}
    for cap in list_capabilities():
        out[cap] = len(list_ready(cap, ready_only=True))
    return out
