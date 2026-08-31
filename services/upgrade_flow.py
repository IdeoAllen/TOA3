# -*- coding: utf-8 -*-
"""用户侧开通/升级：推断产品方案、一键下单支付激活（一订单一授权码）。"""
from __future__ import annotations

from enum import Enum
from typing import Any, Tuple

from services.commerce_profile import merge_buyer_profile, save_profile
from services.subscription_renew import (
    _DEFAULT_PACK,
    fetch_renew_quote,
    infer_renew_pack_id,
    is_activation_block,
    is_renewable_block,
    is_trial_expired_block,
)


class UpgradeIntent(str, Enum):
    ACTIVATE = "activate"
    UPGRADE = "upgrade"
    RENEW = "renew"


def is_feature_block(reason: str) -> bool:
    text = str(reason or "")
    return any(k in text for k in ("未包含功能", "未包含", "请联系管理员开通", "请升级", "升级至"))


def should_offer_purchase(*, reason: str = "") -> bool:
    text = str(reason or "")
    try:
        from services.license_manager import global_license_manager as lm

        if lm.is_expired_trial() or lm.is_expired_paid():
            return True
    except Exception:
        pass
    return is_renewable_block(text) or is_activation_block(text) or is_feature_block(text) or is_trial_expired_block(text)


def classify_intent(*, reason: str = "", module_id: str = "") -> UpgradeIntent:
    text = str(reason or "")
    try:
        from services.license_manager import global_license_manager as lm

        if lm.is_expired_trial() or is_trial_expired_block(text):
            return UpgradeIntent.ACTIVATE
        if lm.is_expired_paid() or is_renewable_block(text):
            return UpgradeIntent.RENEW
    except Exception:
        if is_trial_expired_block(text):
            return UpgradeIntent.ACTIVATE
        if is_renewable_block(text):
            return UpgradeIntent.RENEW
    if is_feature_block(text) and module_id:
        from services.plan_tiers import current_plan_id, is_upgrade_needed, suggest_upgrade_plan

        cur = current_plan_id()
        tgt = suggest_upgrade_plan(module_id=module_id, current_plan_id=cur)
        if cur and is_upgrade_needed(target_plan_id=tgt, current_plan_id=cur):
            return UpgradeIntent.UPGRADE
        return UpgradeIntent.UPGRADE
    return UpgradeIntent.ACTIVATE


def module_display_name(module_id: str) -> str:
    mid = str(module_id or "").strip()
    if not mid:
        return ""
    try:
        from services.config_service import get_menu_item_by_id

        item = get_menu_item_by_id(mid)
        if item:
            return str(item.get("name") or mid)
    except Exception:
        pass
    try:
        from services.menu_registry import all_menu_items

        for item in all_menu_items():
            if str(item.get("id") or "") == mid:
                return str(item.get("name") or mid)
    except Exception:
        pass
    return mid


def suggest_pack_for_module(module_id: str) -> str:
    """唯一可售方案：体验版 tiyan。"""
    return _DEFAULT_PACK


def resolve_pack_id(*, intent: UpgradeIntent, module_id: str = "", reason: str = "") -> str:
    from services.plan_tiers import current_plan_id, suggest_upgrade_plan

    cur = current_plan_id()
    if intent is UpgradeIntent.RENEW:
        return infer_renew_pack_id()
    if intent in (UpgradeIntent.ACTIVATE, UpgradeIntent.UPGRADE):
        if module_id:
            return suggest_upgrade_plan(module_id=module_id, current_plan_id=cur)
        if cur:
            return cur
        return suggest_pack_for_module(module_id)
    return _DEFAULT_PACK


def intent_headline(*, intent: UpgradeIntent, module_id: str = "", reason: str = "") -> str:
    from services.user_plan_presentation import user_upgrade_headline

    name = module_display_name(module_id)
    try:
        from services.license_manager import global_license_manager as lm

        if lm.is_expired_trial() or is_trial_expired_block(reason):
            return user_upgrade_headline(module_name=name)
    except Exception:
        if is_trial_expired_block(reason):
            return user_upgrade_headline(module_name=name)
    if intent is UpgradeIntent.RENEW:
        if name:
            return user_upgrade_headline(module_name=name)
        return "续费后即可继续使用"
    if intent is UpgradeIntent.UPGRADE:
        from services.plan_tiers import current_plan_id, plan_display_name, suggest_upgrade_plan, upgrade_hint

        hint = upgrade_hint(module_id=module_id, current_plan_id=current_plan_id())
        if hint:
            return hint
        tgt = suggest_upgrade_plan(module_id=module_id, current_plan_id=current_plan_id())
        if name:
            return f"升级至「{plan_display_name(tgt)}」即可使用「{name}」"
        return "升级产品方案以解锁更多功能"
    return user_upgrade_headline(module_name=name)


def intent_window_title(*, intent: UpgradeIntent) -> str:
    if intent is UpgradeIntent.RENEW:
        return "续费"
    if intent is UpgradeIntent.UPGRADE:
        return "升级"
    return "开通"


def primary_action_label(*, intent: UpgradeIntent | None = None, price_yuan: int = 0) -> str:
    if intent is UpgradeIntent.RENEW:
        return "提交续费申请"
    return "提交开通申请"


def submit_purchase_request(
    *,
    pack_id: str = "",
    plan_id: str = "",
    name: str,
    phone: str,
) -> Tuple[bool, str, dict[str, Any]]:
    """终端购买：仅创建订单并同步到运营台，不在客户端走支付/自动激活。"""
    from services.commerce_client import create_order
    from services.license_manager import global_license_manager
    from services.product_plans import resolve_plan_id

    meta: dict[str, Any] = {
        "order_no": "",
        "pending_payment": True,
        "pending_admin": True,
        "pack_id": "",
        "plan_id": "",
    }

    phone = str(phone or "").strip()
    name = str(name or "").strip()
    if len(phone) != 11 or not phone.isdigit():
        return False, "请填写 11 位手机号", meta
    if not name:
        name = "用户"

    pid = resolve_plan_id(plan_id=plan_id, pack_id=pack_id) or _DEFAULT_PACK
    meta["plan_id"] = pid
    meta["pack_id"] = pid
    mid = global_license_manager.get_machine_id()

    ok, order, err = create_order(
        plan_id=pid,
        customer_name=name,
        phone=phone,
        machine_id=mid,
    )
    if not ok:
        return False, err or "创建订单失败", meta
    order_no = str((order or {}).get("order_no") or "")
    if not order_no:
        return False, "订单号为空", meta
    meta["order_no"] = order_no
    save_profile(name=name, phone=phone)
    _save_commerce_meta(plan_id=pid, order_no=order_no)
    return (
        True,
        f"开通申请已提交（订单 {order_no}）。请等待运营台确认后，点「同步授权」刷新本机授权。",
        meta,
    )


def purchase_pack(
    *,
    pack_id: str = "",
    plan_id: str = "",
    name: str,
    phone: str,
) -> Tuple[bool, str, dict[str, Any]]:
    """终端统一走运营台订单，不在客户端支付。"""
    return submit_purchase_request(pack_id=pack_id, plan_id=plan_id, name=name, phone=phone)


def purchase_plan(
    *,
    plan_id: str,
    name: str,
    phone: str,
) -> Tuple[bool, str, dict[str, Any]]:
    return purchase_pack(plan_id=plan_id, name=name, phone=phone)


def _list_cloud_packs() -> Tuple[bool, list[dict[str, Any]], dict, str]:
    from services.commerce_client import list_sellable_packs

    return list_sellable_packs()


def _activate_purchased_key(key: str, *, name: str, phone: str) -> Tuple[bool, str]:
    """支付/同步订单后激活：先解除本机旧码绑定，再联网激活。"""
    from services.license_manager import global_license_manager

    lm = global_license_manager
    lm.prepare_commerce_activation(name=name, phone=phone)
    act_ok, act_msg, _ = lm.activate_with_code(key)
    if act_ok:
        return True, act_msg or ""
    ok, _, payload = lm.verify_license_code(key)
    if ok and payload:
        lm.prepare_commerce_activation(
            name=str(payload.get("name") or name),
            phone=str(payload.get("phone") or phone),
        )
        act_ok, act_msg, _ = lm.activate_with_code(key)
    return bool(act_ok), str(act_msg or "激活失败")


def _save_commerce_meta(*, plan_id: str, order_no: str) -> None:
    from services.license_manager import global_license_manager

    info = dict(global_license_manager.get_license_info() or {})
    if plan_id:
        info["plan_id"] = plan_id
    if order_no:
        info["last_order_no"] = order_no
        info["order_no"] = order_no
    global_license_manager.license_info.update(info)
    global_license_manager.save_license()


def purchase_one_click(
    *,
    pack_id: str,
    name: str,
    phone: str,
) -> Tuple[bool, str]:
    ok, msg, meta = purchase_pack(pack_id=pack_id, name=name, phone=phone)
    if ok and not meta.get("pending_payment"):
        save_profile(name=name, phone=phone)
    return ok, msg


def sync_paid_order(*, order_no: str, phone: str) -> Tuple[bool, str, dict[str, Any]]:
    """Portal 真实支付后同步订单并激活。"""
    from services.commerce_client import pay_order, upgrade_from_order
    from services.license_manager import global_license_manager
    from services.notify_bus import emit_license_changed

    meta: dict[str, Any] = {"order_no": str(order_no or "").strip(), "pending_payment": False}
    phone = str(phone or "").strip()
    mid = global_license_manager.get_machine_id()
    if not meta["order_no"]:
        return False, "订单号为空", meta

    ok, data, err = upgrade_from_order(order_no=meta["order_no"], phone=phone, machine_id=mid)
    if not ok:
        ok2, st, err2 = pay_order(order_no=meta["order_no"], phone=phone, machine_id=mid)
        if not ok2:
            return False, err or err2 or "订单尚未支付或同步失败", meta
        data = st

    key = str((data or {}).get("license_key") or "").strip()
    if not key:
        return False, "同步成功但未返回授权码", meta

    profile = merge_buyer_profile()
    buyer_name = str(profile.get("name") or "用户").strip() or "用户"
    act_ok, act_msg = _activate_purchased_key(key, name=buyer_name, phone=phone)
    if not act_ok:
        return False, act_msg or "激活失败", meta

    plan_id = str((data or {}).get("plan_id") or (data or {}).get("pack_id") or "").strip()
    _save_commerce_meta(plan_id=plan_id, order_no=meta["order_no"])
    meta["renewed"] = False
    meta["plan_id"] = plan_id
    emit_license_changed()
    save_profile(phone=phone)
    return True, global_license_manager.get_validity_text(), meta


def build_offer(*, module_id: str = "", reason: str = "") -> dict[str, Any]:
    intent = classify_intent(reason=reason, module_id=module_id)
    plan_id = resolve_pack_id(intent=intent, module_id=module_id, reason=reason)
    profile = merge_buyer_profile()
    return {
        "intent": intent,
        "pack_id": plan_id,
        "plan_id": plan_id,
        "module_id": module_id,
        "module_name": module_display_name(module_id),
        "headline": intent_headline(intent=intent, module_id=module_id, reason=reason),
        "window_title": intent_window_title(intent=intent),
        "name": profile.get("name") or "用户",
        "phone": profile.get("phone") or "",
        "reason": reason,
    }
