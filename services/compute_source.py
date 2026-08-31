# -*- coding: utf-8 -*-
"""算力来源 · 支付卡隐喻：选默认卡、自动兜底、解绑。"""
from __future__ import annotations

from typing import Any

from services.integrations.secrets import set_profile_secret, set_secret
from services.model_catalog import (
    get_active_profile_id,
    list_profiles,
    resolve_profile,
    set_active_profile_id,
)
from services.model_ready_registry import ReadyStatus, evaluate_profile

_TIER_ORDER = {"simple": 0, "advanced": 1, "cloud": 2}

_CAPABILITY_USER_LABELS: dict[str, str] = {
    "text_llm": "写字",
    "image_gen": "生图",
}


def capability_user_label(capability: str) -> str:
    return _CAPABILITY_USER_LABELS.get(capability, capability)


def list_ready_catalog_profiles(capability: str) -> list[dict[str, Any]]:
    """同能力下 catalog 且 status=ready 的来源列表。"""
    rows: list[dict[str, Any]] = []
    for prof in list_profiles(capability):
        pid = str(prof.get("id") or "")
        if not pid:
            continue
        ev = evaluate_profile(capability, pid, prof)
        if ev.get("status") != ReadyStatus.READY:
            continue
        row = dict(prof)
        row.update(ev)
        rows.append(row)
    rows.sort(
        key=lambda p: (
            _TIER_ORDER.get(str(p.get("tier") or ""), 9),
            str(p.get("label") or p.get("id") or ""),
        )
    )
    return rows


def pick_effective_profile_id(
    capability: str,
    *,
    persist: bool = True,
    exclude: str | None = None,
) -> str:
    """
    任务页用：优先 active 且 Ready；否则自动选第一张 Ready（优先 simple）。
    persist=True 时写回 active（静默设默认卡）。
    """
    ready = list_ready_catalog_profiles(capability)
    if exclude:
        ready = [r for r in ready if str(r.get("id") or "") != exclude]
    if not ready:
        return ""

    active = get_active_profile_id(capability)

    # 生图任务页：小白路径始终优先 simple（本机生图），不因 ComfyUI 在线误用专业档
    if capability == "image_gen":
        simple_ready = [
            r
            for r in ready
            if str(r.get("tier") or "") == "simple" or str(r.get("provider") or "") == "sdcpp"
        ]
        if simple_ready:
            for row in simple_ready:
                if str(row.get("id") or "") == active:
                    return active
            chosen = str(simple_ready[0].get("id") or "")
            if persist and chosen:
                set_active_profile_id(capability, chosen)
            return chosen
        # 本机简易未就绪：不自动把 ComfyUI 专业档设为默认，避免误触报错
        for row in ready:
            if str(row.get("id") or "") != active:
                continue
            tier = str(row.get("tier") or "")
            provider = str(row.get("provider") or "")
            if tier == "advanced" and provider in ("comfyui", "sd_webui"):
                return ""
            return active
        return ""

    for row in ready:
        if str(row.get("id") or "") == active:
            return active

    chosen = str(ready[0].get("id") or "")
    if persist and chosen:
        set_active_profile_id(capability, chosen)
    return chosen


def unbind_profile(capability: str, profile_id: str) -> tuple[bool, str]:
    """
    解绑算力来源：
    - 云端：清 Key
    - 本机专业：取消默认（服务需用户自行停止）
    - 本机简易：取消默认（不删权重文件）
    若解绑的是默认卡，自动切换到下一张可用卡。
    """
    pid = str(profile_id or "").strip()
    if not pid:
        return False, "未选择算力来源。"

    try:
        prof = resolve_profile(capability, pid)
    except KeyError:
        return False, "找不到该算力来源。"

    provider = str(prof.get("provider") or "").strip().lower()
    tier = str(prof.get("tier") or "").strip().lower()
    was_default = get_active_profile_id(capability) == pid

    if tier == "cloud" or provider in ("openai_compatible", "openai_images"):
        set_profile_secret(capability, pid, "api_key", "")
        if capability == "text_llm" and pid == "moonshot_kimi":
            set_secret("llm", "api_key", "")
        detail = "已解绑云端密钥。"
    elif provider == "sdcpp":
        detail = "已取消默认。本机模型文件仍保留，不需要时可手动删除。"
    elif provider in ("comfyui", "sd_webui"):
        detail = "已取消默认。停止本机服务后该来源不再可用。"
    elif provider == "ollama" or tier == "advanced":
        set_profile_secret(capability, pid, "api_key", "")
        detail = "已解绑本机端点配置。"
    else:
        set_profile_secret(capability, pid, "api_key", "")
        detail = "已解绑。"

    if was_default:
        nxt = pick_effective_profile_id(capability, persist=True, exclude=pid)
        if nxt:
            detail += f" 已自动切换默认：{nxt}。"
        else:
            detail += " 当前能力暂无其它可用来源，请到算力来源绑定。"

    return True, detail
