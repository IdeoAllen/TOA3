# -*- coding: utf-8 -*-
"""用户侧开通/升级：推断功能包、一键下单支付激活。"""
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
)


class UpgradeIntent(str, Enum):
    ACTIVATE = "activate"
    UPGRADE = "upgrade"
    RENEW = "renew"


def is_feature_block(reason: str) -> bool:
    text = str(reason or "")
    return any(k in text for k in ("未包含功能", "未包含", "请联系管理员开通"))


def should_offer_purchase(*, reason: str = "") -> bool:
    text = str(reason or "")
    return is_renewable_block(text) or is_activation_block(text) or is_feature_block(text)


def classify_intent(*, reason: str = "", module_id: str = "") -> UpgradeIntent:
    text = str(reason or "")
    if is_renewable_block(text):
        return UpgradeIntent.RENEW
    if is_feature_block(text) and module_id:
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
    """选覆盖该模块的最低价可售包；无模块上下文时返回入门版。"""
    mid = str(module_id or "").strip()
    from services.feature_packs import expand_features, list_packs

    ok, cloud_packs, _, _ = _list_cloud_packs()
    price_map: dict[str, int] = {}
    if ok:
        for row in cloud_packs:
            pid = str(row.get("id") or "")
            if pid:
                try:
                    price_map[pid] = int(row.get("price_yuan") or 0)
                except Exception:
                    price_map[pid] = 0

    candidates: list[tuple[int, str]] = []
    for pack in list_packs(sellable_only=True):
        pid = str(pack.get("id") or "")
        if not pid:
            continue
        feats = expand_features([pid])
        if feats == ["all"] or (mid and mid in feats) or (not mid and pid == _DEFAULT_PACK):
            price = price_map.get(pid, 10**9 if mid else 0)
            candidates.append((price, pid))

    if not candidates:
        return _DEFAULT_PACK
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][1]


def resolve_pack_id(*, intent: UpgradeIntent, module_id: str = "", reason: str = "") -> str:
    if intent is UpgradeIntent.RENEW:
        return infer_renew_pack_id()
    if intent in (UpgradeIntent.ACTIVATE, UpgradeIntent.UPGRADE):
        return suggest_pack_for_module(module_id)
    return _DEFAULT_PACK


def intent_headline(*, intent: UpgradeIntent, module_id: str = "") -> str:
    name = module_display_name(module_id)
    if intent is UpgradeIntent.RENEW:
        return "续费后即可继续使用"
    if intent is UpgradeIntent.UPGRADE and name:
        return f"升级后即可使用「{name}」"
    if name:
        return f"开通后即可使用「{name}」"
    return "开通完整版，解锁全部办公工具"


def intent_window_title(*, intent: UpgradeIntent) -> str:
    if intent is UpgradeIntent.RENEW:
        return "续费"
    if intent is UpgradeIntent.UPGRADE:
        return "升级"
    return "开通"


def primary_action_label(*, intent: UpgradeIntent | None = None, price_yuan: int) -> str:
    if intent is UpgradeIntent.RENEW:
        return f"一键续费 ¥{price_yuan}"
    return f"一键开通 ¥{price_yuan}"


def _list_cloud_packs() -> Tuple[bool, list[dict[str, Any]], dict, str]:
    from services.commerce_client import list_sellable_packs

    return list_sellable_packs()


def purchase_pack(
    *,
    pack_id: str,
    name: str,
    phone: str,
) -> Tuple[bool, str, dict[str, Any]]:
    """创建订单 → 模拟/真实支付 → 激活。meta 含 order_no、pending_payment。"""
    from services.commerce_client import create_order, pay_order
    from services.license_manager import global_license_manager
    from services.notify_bus import emit_license_changed

    meta: dict[str, Any] = {
        "order_no": "",
        "pending_payment": False,
        "renewed": False,
        "pack_id": str(pack_id or "").strip() or _DEFAULT_PACK,
    }

    phone = str(phone or "").strip()
    name = str(name or "").strip()
    if len(phone) != 11 or not phone.isdigit():
        return False, "请填写 11 位手机号", meta
    if not name:
        name = "用户"

    pid = meta["pack_id"]
    mid = global_license_manager.get_machine_id()

    ok, order, err = create_order(
        pack_id=pid,
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

    ok, quote, _ = fetch_renew_quote(pid)
    mock_pay = quote.get("mock_pay", True) if ok else True
    if not mock_pay:
        meta["pending_payment"] = True
        return False, f"订单 {order_no} 已创建，请完成支付后点「同步已付订单」", meta

    ok, paid, err = pay_order(order_no=order_no, phone=phone, machine_id=mid)
    if not ok:
        return False, err or "支付失败", meta

    key = str((paid or {}).get("license_key") or "").strip()
    if not key:
        return False, "支付成功但未返回授权码", meta

    act_ok, act_msg, _ = global_license_manager.activate_with_code(key)
    if not act_ok:
        return False, act_msg or "激活失败", meta

    meta["renewed"] = "续费" in str((paid or {}).get("remark") or "")
    emit_license_changed()
    return True, global_license_manager.get_validity_text(), meta


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

    act_ok, act_msg, _ = global_license_manager.activate_with_code(key)
    if not act_ok:
        return False, act_msg or "激活失败", meta

    meta["renewed"] = "续费" in str((data or {}).get("remark") or "")
    emit_license_changed()
    save_profile(phone=phone)
    return True, global_license_manager.get_validity_text(), meta


def build_offer(*, module_id: str = "", reason: str = "") -> dict[str, Any]:
    intent = classify_intent(reason=reason, module_id=module_id)
    pack_id = resolve_pack_id(intent=intent, module_id=module_id, reason=reason)
    profile = merge_buyer_profile()
    return {
        "intent": intent,
        "pack_id": pack_id,
        "module_id": module_id,
        "module_name": module_display_name(module_id),
        "headline": intent_headline(intent=intent, module_id=module_id),
        "window_title": intent_window_title(intent=intent),
        "name": profile.get("name") or "用户",
        "phone": profile.get("phone") or "",
        "reason": reason,
    }
