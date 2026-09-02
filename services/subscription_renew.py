# -*- coding: utf-8 -*-
"""到期续费：推断 pack、一键下单支付激活。"""
from __future__ import annotations

from typing import Any, Tuple

_DEFAULT_PACK = "tiyan"
_ALL_PACK = "tiyan"


def is_activation_block(reason: str) -> bool:
    """单机/未授权/需激活 — 应引导激活，而非续费。"""
    text = str(reason or "")
    keys = (
        "付费版",
        "正式版",
        "完整版",
        "未授权",
        "授权码",
        "激活",
        "单机基础",
        "单机体验",
        "基础版",
        "local_free",
    )
    return any(k in text for k in keys)


def is_renewable_block(reason: str) -> bool:
    """已付费/体验授权到期 — 弹续费/购买窗。"""
    text = str(reason or "")
    if is_activation_block(text):
        return False
    keys = (
        "到期",
        "续费",
        "订阅",
        "expired",
        "已过期",
        "体验版已到期",
        "基础版已到期",
        "免费版体验已到期",
        "付费模块已到期",
        "请购买",
        "请续费",
    )
    return any(k in text for k in keys)


def is_trial_expired_block(reason: str) -> bool:
    text = str(reason or "")
    return (
        "体验版已到期" in text
        or "体验已到期" in text
        or "基础版已到期" in text
        or "免费版体验已到期" in text
    )


def should_prompt_renew_dialog(*, reason: str | None = None) -> bool:
    """启动/导航时是否应提供续费（排除单机与有效授权）。"""
    from services.license_manager import global_license_manager

    lm = global_license_manager
    if lm.is_standalone_mode() or lm.is_licensed():
        return False
    if lm.is_expired_trial() or lm.is_expired_paid():
        return True
    text = str(reason if reason is not None else lm.get_validity_text() or "")
    return is_renewable_block(text)


def _sellable_pack_ids() -> set[str]:
    from services.feature_packs import list_packs

    return {str(p.get("id") or "") for p in list_packs(sellable_only=True) if p.get("id")}


def infer_renew_pack_id(info: dict[str, Any] | None = None) -> str:
    """从上次授权推断续费 pack。"""
    from services.license_manager import global_license_manager

    data = info if isinstance(info, dict) else global_license_manager.get_license_info()
    sellable = _sellable_pack_ids()
    plan = str(data.get("plan_id") or "").strip()
    if plan and plan in sellable:
        return plan

    feats = data.get("features") or []
    if isinstance(feats, list):
        if "all" in feats:
            return _ALL_PACK if _ALL_PACK in sellable else _DEFAULT_PACK
        for f in feats:
            fid = str(f or "").strip()
            if fid in sellable:
                return fid

    for u in data.get("authorized_users") or []:
        if not isinstance(u, dict):
            continue
        for f in u.get("features") or u.get("menus") or []:
            fid = str(f or "").strip()
            if fid in sellable:
                return fid
    return _DEFAULT_PACK


def renew_profile(info: dict[str, Any] | None = None) -> dict[str, str]:
    from services.license_manager import global_license_manager

    data = info if isinstance(info, dict) else global_license_manager.get_license_info()
    name = str(data.get("user_name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    if not phone:
        for u in data.get("authorized_users") or []:
            if not isinstance(u, dict):
                continue
            if str(u.get("name") or "").strip() == name or not name:
                phone = str(u.get("phone") or "").strip()
                if not name:
                    name = str(u.get("name") or "").strip()
            if phone:
                break
    pack_id = infer_renew_pack_id(data)
    from services.feature_packs import list_packs

    pack_name = pack_id
    for p in list_packs(sellable_only=True):
        if p.get("id") == pack_id:
            pack_name = str(p.get("name") or pack_id)
            break
    return {
        "name": name,
        "phone": phone,
        "pack_id": pack_id,
        "pack_name": pack_name,
    }


def fetch_renew_quote(plan_id: str = "", pack_id: str = "") -> Tuple[bool, dict, str]:
    from services.commerce_client import list_sellable_plans
    from services.product_plans import resolve_plan_id

    pid = resolve_plan_id(plan_id=plan_id, pack_id=pack_id)
    ok, plans, commerce, err = list_sellable_plans()
    if not ok:
        return False, {}, err
    row = next((p for p in plans if str(p.get("plan_id") or p.get("id") or "") == pid), None)
    if not row:
        return False, {}, f"未找到产品方案 {pid}"
    days = int(row.get("validity_days") or commerce.get("default_license_days") or 365)
    name = str(row.get("plan_name") or row.get("name") or pid)
    return True, {
        "pack_id": pid,
        "plan_id": pid,
        "pack_name": name,
        "plan_name": name,
        "price_yuan": int(row.get("price_yuan") or 0),
        "license_days": days,
        "validity_days": days,
        "mock_pay": bool((commerce.get("mock_payment") or {}).get("enabled", True)),
    }, ""


def renew_one_click(
    *,
    name: str,
    phone: str,
    pack_id: str | None = None,
) -> Tuple[bool, str]:
    """创建订单 → 模拟/终端支付 → 激活。成功返回新的有效期文案。"""
    from services.upgrade_flow import purchase_one_click

    pid = str(pack_id or infer_renew_pack_id()).strip() or _DEFAULT_PACK
    return purchase_one_click(pack_id=pid, name=name, phone=phone)
