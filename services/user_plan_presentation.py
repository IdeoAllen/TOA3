# -*- coding: utf-8 -*-
"""终端用户口径：试用版 / 授权版 / 正式版 + 套餐（与开发构建、发行 profile 分离）。

软件版本号仅在「关于」弹窗与状态栏永久区展示，其它入口不得重复。
"""
from __future__ import annotations

from typing import Tuple

TRIAL_TIER_LABEL = "试用版"
AUTH_TIER_LABEL = "授权版"
OFFICIAL_TIER_LABEL = "正式版"

# 兼容旧引用
FREE_TIER_LABEL = TRIAL_TIER_LABEL
PAID_TIER_LABEL = OFFICIAL_TIER_LABEL


def is_dev_build() -> bool:
    try:
        from services.runtime_paths import get_runtime_environment

        return get_runtime_environment() == "development"
    except Exception:
        return False


def dev_build_tag() -> str:
    """仅开发构建标识，不对用户展示为产品档位。"""
    return "开发构建" if is_dev_build() else ""


def user_software_version(*, short: bool = False) -> str:
    """用户可见版本串：仅供关于弹窗与状态栏调用。"""
    from app.version import APP_NAME, APP_VERSION

    if short:
        return f"v{APP_VERSION}"
    return f"{APP_NAME} v{APP_VERSION}"


def _license_manager():
    from services.license_manager import global_license_manager

    lm = global_license_manager
    if not lm.license_info:
        lm.load_license()
    return lm


def user_has_paid_order() -> bool:
    """正式版用户：云侧 entitlement=paid 且有关联订单号（履约签发）。"""
    lm = _license_manager()
    if lm.is_standalone_mode() or not lm.is_licensed():
        return False
    if lm.is_expired_paid():
        return False
    ent = lm.get_entitlement()
    info = lm.get_license_info()
    order_no = str(info.get("order_no") or info.get("last_order_no") or "").strip()
    return ent == "paid" and bool(order_no)


def user_has_code_activation() -> bool:
    """授权版：已通过授权码联网激活（含管理员/邀请/体验码，非套餐订单履约）。"""
    lm = _license_manager()
    if lm.is_standalone_mode():
        return False
    if not lm.is_licensed():
        return False
    if user_has_paid_order():
        return False
    return bool(
        lm.had_network_activation()
        or lm.is_admin_user()
        or lm.get_entitlement() in ("admin", "invited", "trial")
    )


def user_plan_tier() -> str:
    """用户档位：试用版 | 授权版 | 正式版。"""
    lm = _license_manager()
    if user_has_paid_order():
        ok, _ = lm._activation_still_valid()
        if ok:
            return OFFICIAL_TIER_LABEL
    if user_has_code_activation():
        return AUTH_TIER_LABEL
    return TRIAL_TIER_LABEL


def user_is_paid_active() -> bool:
    return user_plan_tier() == OFFICIAL_TIER_LABEL


def _resolve_plan_id(lm) -> str:
    info = lm.get_license_info()
    pid = str(info.get("plan_id") or "").strip()
    if pid and pid not in ("all", "local_free"):
        return pid
    feats = info.get("features") or []
    if isinstance(feats, list):
        try:
            from services.plan_tiers import _tier_map

            sellable = set(_tier_map().keys())
            for f in feats:
                fid = str(f or "").strip()
                if fid in sellable:
                    return fid
        except Exception:
            pass
    try:
        from services.plan_tiers import current_plan_id

        return str(current_plan_id() or "").strip()
    except Exception:
        return ""


def _plan_name(plan_id: str) -> str:
    pid = str(plan_id or "").strip()
    if not pid:
        return ""
    if pid == "tiyan":
        return "体验版"
    try:
        from services.plan_tiers import plan_display_name

        name = plan_display_name(pid)
        if name and name != pid:
            return name
    except Exception:
        pass
    return pid


def user_product_pack_label() -> str:
    """当前方案/身份说明（与档位分离）。"""
    lm = _license_manager()
    ent = lm.get_entitlement()

    if lm.is_admin_user() or ent == "admin":
        return "管理员授权"
    if ent == "invited":
        return "邀请授权"

    if user_has_paid_order():
        name = _plan_name(_resolve_plan_id(lm))
        return name or "付费套餐"

    if ent == "trial" and lm.is_licensed() and not lm.is_expired_trial():
        name = _plan_name(_resolve_plan_id(lm))
        return name or "体验授权"

    if lm.is_standalone_mode():
        return "基础功能"
    if lm.is_licensed() and not user_plan_expired():
        name = _plan_name(_resolve_plan_id(lm))
        if name:
            return name
    return "基础功能"


def user_plan_expired() -> bool:
    lm = _license_manager()
    return bool(
        lm.is_expired_standalone()
        or lm.is_expired_trial()
        or lm.is_expired_paid()
    )


def _expiry_date_line(lm) -> str:
    exp = str(lm.get_license_info().get("expire_date") or "").strip()[:10]
    if user_plan_expired():
        suffix = f"（{exp}）" if exp else ""
        if lm.is_expired_paid():
            return f"已到期{suffix}"
        if lm.is_expired_trial():
            return f"体验已到期{suffix}"
        return f"已到期{suffix}" if suffix else "已到期"

    if not exp:
        return "—"
    days = lm.get_remaining_days()
    if days != float("inf") and int(days) >= 0:
        return f"有效期至 {exp}（剩余 {int(days)} 天）"
    return f"有效期至 {exp}"


def user_validity_line(*, date_only: bool = False) -> str:
    """账号/状态用有效期摘要。"""
    lm = _license_manager()
    date_line = _expiry_date_line(lm)
    if date_only:
        return date_line

    tier = user_plan_tier()
    pack = user_product_pack_label()

    if user_plan_expired():
        if lm.is_expired_paid():
            return f"{OFFICIAL_TIER_LABEL}已到期 · 续费后恢复全部模块"
        if lm.is_expired_trial():
            return f"体验已到期 · 购买{OFFICIAL_TIER_LABEL}解锁付费模块"
        return f"{TRIAL_TIER_LABEL}体验已到期 · 升级{OFFICIAL_TIER_LABEL}解锁付费模块"

    if tier == OFFICIAL_TIER_LABEL:
        head = pack if pack and pack not in (OFFICIAL_TIER_LABEL, "付费套餐") else OFFICIAL_TIER_LABEL
        return _join_unique_labels(head, date_line)

    if tier == AUTH_TIER_LABEL:
        head = pack if pack and pack not in (AUTH_TIER_LABEL, "基础功能") else AUTH_TIER_LABEL
        return _join_unique_labels(head, date_line)

    return _join_unique_labels(TRIAL_TIER_LABEL, pack if pack not in (TRIAL_TIER_LABEL, "基础功能") else "", date_line)


def user_account_subtitle() -> str:
    tier = user_plan_tier()
    pack = user_product_pack_label()
    date_line = user_validity_line(date_only=True)
    if tier == AUTH_TIER_LABEL and pack not in ("基础功能", AUTH_TIER_LABEL):
        head = pack
    elif tier == OFFICIAL_TIER_LABEL and pack not in ("付费套餐", OFFICIAL_TIER_LABEL):
        head = _join_unique_labels(tier, pack)
    else:
        head = tier
    return _join_unique_labels(head, date_line)


def _join_unique_labels(*parts: str) -> str:
    """拼接展示文案，跳过空段与相邻重复段（避免「付费版 · 付费版」）。"""
    out: list[str] = []
    for raw in parts:
        text = str(raw or "").strip()
        if not text or text == "—":
            continue
        if out and out[-1] == text:
            continue
        if text in out:
            continue
        out.append(text)
    return " · ".join(out)


def user_status_bar_version_label() -> str:
    """状态栏永久区：全应用唯一的版本号展示位。"""
    base = user_software_version(short=True)
    tag = dev_build_tag()
    return f"{base} · {tag}" if tag else base


def user_status_plan_label() -> str:
    """托盘等次要入口：档位与套餐，不含版本号。"""
    tier = user_plan_tier()
    pack = user_product_pack_label()
    if tier == OFFICIAL_TIER_LABEL:
        if pack and pack not in (OFFICIAL_TIER_LABEL, "付费套餐", tier):
            return _join_unique_labels(tier, pack)
        return tier
    if tier == AUTH_TIER_LABEL:
        if pack and pack not in (AUTH_TIER_LABEL, "基础功能", tier):
            return _join_unique_labels(tier, pack)
        return tier
    if pack and pack not in (TRIAL_TIER_LABEL, "基础功能", tier):
        return _join_unique_labels(tier, pack)
    return tier


def user_status_version_label() -> str:
    """兼容旧名：等同状态栏版本标签。"""
    return user_status_bar_version_label()


def user_chip_display() -> Tuple[str, str, str]:
    """顶栏 Chip：文案、语义 kind、tooltip。"""
    tier = user_plan_tier()
    tooltip = (
        f"档位：{tier}\n"
        f"身份/套餐：{user_product_pack_label()}\n"
        f"{user_validity_line()}"
    )
    if user_plan_expired():
        return "续费", "warning", tooltip
    if tier == OFFICIAL_TIER_LABEL:
        return OFFICIAL_TIER_LABEL, "success", tooltip
    if tier == AUTH_TIER_LABEL:
        return AUTH_TIER_LABEL, "success", tooltip
    return TRIAL_TIER_LABEL, "info", tooltip


def user_upgrade_headline(*, module_name: str = "") -> str:
    if user_plan_expired():
        if module_name:
            return f"{OFFICIAL_TIER_LABEL}已到期，续费后可继续使用「{module_name}」"
        return f"{OFFICIAL_TIER_LABEL}已到期，续费后恢复全部付费模块"
    if module_name:
        return f"开通{OFFICIAL_TIER_LABEL}即可使用「{module_name}」"
    return f"开通{OFFICIAL_TIER_LABEL}，解锁全部办公工具"


def user_access_block_message() -> str:
    lm = _license_manager()
    if user_plan_expired():
        if lm.is_expired_paid():
            return f"{OFFICIAL_TIER_LABEL}已到期，请续费"
        try:
            from services.license_manager import upgrade_target_label

            target = upgrade_target_label()
        except Exception:
            target = OFFICIAL_TIER_LABEL
        return f"体验已到期，请升级{target}"
    if lm.is_standalone_mode() and not user_plan_expired():
        try:
            from services.license_manager import upgrade_target_label

            target = upgrade_target_label()
        except Exception:
            target = OFFICIAL_TIER_LABEL
        return f"该功能需{OFFICIAL_TIER_LABEL}，请升级{target}"
    return f"该功能需{OFFICIAL_TIER_LABEL}，请先开通"


def user_login_subtitle() -> str:
    tag = dev_build_tag()
    if tag:
        return tag
    try:
        from services.product_vision import tagline

        return tagline() or ""
    except Exception:
        return ""


def user_login_hint() -> str:
    return f"粘贴授权码登录，或直接进入{TRIAL_TIER_LABEL}。购买与续费在软件内完成。"


def user_version_caption(*, for_about: bool = False) -> str:
    """关于弹窗专用版本行；开发构建仅在 about 时附带。"""
    base = user_software_version()
    if for_about and dev_build_tag():
        return f"{base} · {dev_build_tag()}"
    return base
