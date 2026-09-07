# -*- coding: utf-8 -*-
"""终端用户口径：基础版 / 体验版 / 授权版 / 正式版 + 套餐（与开发构建、发行 profile 分离）。

分层（勿混称）：
- 构建：开发构建 vs 安装包（不要对用户说「正式版安装」当档位）
- 档位：基础版（离线） / 体验版（trial） / 授权版（邀请/管理员） / 正式版（付费订单）
- 方案：feature_packs（如全功能方案）；唯一方案时不与档位叠成「正式版·体验版」

软件版本号仅在「关于」弹窗与状态栏永久区展示，其它入口不得重复。
"""
from __future__ import annotations

from typing import Tuple

TRIAL_TIER_LABEL = "基础版"
EXPERIENCE_TIER_LABEL = "体验版"
AUTH_TIER_LABEL = "授权版"
OFFICIAL_TIER_LABEL = "正式版"

# 兼容旧引用
FREE_TIER_LABEL = TRIAL_TIER_LABEL
PAID_TIER_LABEL = OFFICIAL_TIER_LABEL

# 与档位语义冲突、不得并排展示的方案名（含历史「体验版」SKU）
_PACK_OMIT_WITH_TIER: dict[str, frozenset[str]] = {
    OFFICIAL_TIER_LABEL: frozenset(
        {
            OFFICIAL_TIER_LABEL,
            "付费套餐",
            "全功能",
            "全功能方案",
            "体验版",
            "体验授权",
            "体验中",
            "基础功能",
        }
    ),
    EXPERIENCE_TIER_LABEL: frozenset(
        {
            EXPERIENCE_TIER_LABEL,
            "体验授权",
            "体验中",
            "全功能",
            "全功能方案",
            "基础功能",
            "基础版",
        }
    ),
    AUTH_TIER_LABEL: frozenset({AUTH_TIER_LABEL, "基础功能"}),
    TRIAL_TIER_LABEL: frozenset({TRIAL_TIER_LABEL, "基础功能"}),
}


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
    """用户档位：基础版 | 体验版 | 授权版 | 正式版。"""
    lm = _license_manager()
    if user_has_paid_order():
        ok, _ = lm._activation_still_valid()
        if ok:
            return OFFICIAL_TIER_LABEL

    ent = str(lm.get_entitlement() or "").strip().lower()
    if lm.is_admin_user() or ent == "admin":
        return AUTH_TIER_LABEL
    if ent == "invited" and (lm.is_licensed() or lm.had_network_activation()):
        return AUTH_TIER_LABEL
    if ent == "trial" and (lm.is_licensed() or lm.had_network_activation()):
        return EXPERIENCE_TIER_LABEL
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


def _plan_name(plan_id: str, *, entitlement: str = "") -> str:
    """方案展示名。唯一 SKU tiyan 不对外叫「体验版」（体验版=试用档位）。"""
    pid = str(plan_id or "").strip()
    if not pid:
        return ""
    ent = str(entitlement or "").strip().lower()
    if pid == "tiyan":
        # 默认不单独展示方案名，避免与档位叠成「正式版·体验版」
        return ""
    try:
        from services.plan_tiers import plan_display_name

        name = plan_display_name(pid)
        if name and name != pid:
            # 历史包名纠偏
            if name.strip() == "体验版":
                return ""
            return name
    except Exception:
        pass
    return pid


def user_product_pack_label() -> str:
    """当前方案/身份说明（与档位分离；能省略则省略）。"""
    lm = _license_manager()
    ent = str(lm.get_entitlement() or "").strip().lower()

    if lm.is_admin_user() or ent == "admin":
        return "管理员授权"
    if ent == "invited":
        return "邀请授权"

    if user_has_paid_order():
        name = _plan_name(_resolve_plan_id(lm), entitlement="paid")
        return name  # 唯一方案时常为空，由档位「正式版」表达

    if ent == "trial" and lm.is_licensed() and not lm.is_expired_trial():
        return ""  # 档位已是「体验版」

    if lm.is_standalone_mode():
        return "基础功能"
    if lm.is_licensed() and not user_plan_expired():
        name = _plan_name(_resolve_plan_id(lm), entitlement=ent)
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


def _pack_for_join(tier: str, pack: str) -> str:
    text = str(pack or "").strip()
    if not text or text == tier:
        return ""
    omit = _PACK_OMIT_WITH_TIER.get(tier, frozenset())
    if text in omit:
        return ""
    return text


def user_validity_line(*, date_only: bool = False) -> str:
    """账号/状态用有效期摘要。"""
    lm = _license_manager()
    date_line = _expiry_date_line(lm)
    if date_only:
        return date_line

    tier = user_plan_tier()
    pack = _pack_for_join(tier, user_product_pack_label())

    if user_plan_expired():
        if lm.is_expired_paid():
            return f"{OFFICIAL_TIER_LABEL}已到期 · 续费后恢复全部模块"
        if lm.is_expired_trial():
            return f"体验已到期 · 购买{OFFICIAL_TIER_LABEL}解锁付费模块"
        return f"{TRIAL_TIER_LABEL}已到期 · 升级{OFFICIAL_TIER_LABEL}解锁付费模块"

    if tier == OFFICIAL_TIER_LABEL:
        return _join_unique_labels(tier, pack, date_line)

    if tier == EXPERIENCE_TIER_LABEL:
        return _join_unique_labels(tier, pack, date_line)

    if tier == AUTH_TIER_LABEL:
        return _join_unique_labels(tier, pack, date_line)

    return _join_unique_labels(TRIAL_TIER_LABEL, pack, date_line)


def user_account_subtitle() -> str:
    tier = user_plan_tier()
    pack = _pack_for_join(tier, user_product_pack_label())
    date_line = user_validity_line(date_only=True)
    head = _join_unique_labels(tier, pack) if pack else tier
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
    """托盘/状态栏档位：与顶栏 Chip 同口径，不含版本号。"""
    tier = user_plan_tier()
    pack = _pack_for_join(tier, user_product_pack_label())
    if pack:
        return _join_unique_labels(tier, pack)
    return tier


def user_status_version_label() -> str:
    """兼容旧名：等同状态栏版本标签。"""
    return user_status_bar_version_label()

def user_offline_grace_hint() -> str:
    """L12：断网宽限期说明（配置 offline_grace_days）。"""
    try:
        from services.license_client import offline_grace_days

        days = int(offline_grace_days() or 0)
        if days <= 0:
            return ""
        return (
            f"已联网激活后，断网仍可使用约 {days} 天（离线宽限期）；"
            "超期或吊销后需恢复网络并再次联网校验。"
        )
    except Exception:
        return "已联网激活后，断网短期内仍可使用；恢复网络后请再联网校验一次。"


def user_auth_failure_hint(err: str) -> str:
    """L3：登录/激活失败时的下一步引导（单行，接在主错误后）。"""
    text = str(err or "").strip()
    low = text.lower()
    if not text:
        return "请检查网络后重试，或在设置页查看云服务连接。"

    if "绑定" in text or "bound" in low or "其它电脑" in text or "其它设备" in text:
        try:
            mid = _license_manager().get_machine_id()
            return (
                f"本机机器 ID：{mid}。"
                "请复制后发给管理员换机解绑，或打开运营台处理。"
            )
        except Exception:
            return "请在「系统设置 → 授权 → 云服务连接」复制机器 ID，联系管理员换机解绑。"

    if any(k in text for k in ("停用", "吊销", "revoked")):
        return "请联系管理员恢复授权，或在运营台查看该账号状态。"

    if "到期" in text or "expired" in low:
        return "登录成功后，可在顶栏 Chip 或「设置 → 开通与续费」续费。"

    if any(k in text for k in ("登记", "新码", "更换", "无效", "missing", "unknown")):
        return "请从运营台重新获取完整授权码后再试。"

    if "手机" in text or "11 位" in text:
        return "请确认手机号无误；若已在他处试用，请联系运营台。"

    if any(k in text for k in ("超时", "网络", "连接", "timeout")):
        return "请检查网络或防火墙，稍后重试。"

    return "仍无法登录时，请打开「系统设置 → 云服务连接」核对 API 与机器 ID。"


def user_entitlement_status_line() -> str:
    """L2 云授权状态：用户可读一行摘要（Chip tooltip / 我的账号）。"""
    lm = _license_manager()
    if is_dev_build():
        return "开发构建 · 全部功能已开放"

    info = lm.get_license_info()
    online = str(info.get("online_status") or "").strip().lower()

    def _days_suffix() -> str:
        days = lm.get_remaining_days()
        if days != float("inf") and int(days) >= 0:
            return f" · 剩余 {int(days)} 天"
        return ""

    if lm.is_standalone_mode():
        if lm.is_expired_standalone():
            return "离线体验已到期"
        suffix = _days_suffix()
        return f"离线体验（未联网授权）{suffix}" if suffix else "离线体验（未联网授权）"

    if online == "revoked":
        return "已吊销"
    if online == "bound_elsewhere":
        return "已绑定其它设备"

    if not lm.is_licensed():
        offline_map = {
            "expired": "已过期",
            "missing": "授权无效",
            "unknown": "授权无效",
        }
        return offline_map.get(online, "未激活")

    ent = lm.get_entitlement()

    if user_plan_expired() or online == "expired":
        if ent == "paid":
            return "正式授权已过期"
        if ent == "trial":
            return "试用已过期"
        if ent == "invited":
            return "邀请授权已过期"
        return "授权已过期"

    suffix = _days_suffix()
    if ent == "admin":
        return f"管理员授权 · 有效{suffix}"
    if ent == "invited":
        return f"邀请授权 · 有效{suffix}"
    if ent == "paid":
        return f"正式授权 · 有效{suffix}"
    if ent == "trial":
        return f"试用中{suffix}"
    if online == "active" or lm.had_network_activation():
        return f"授权有效{suffix}"
    return f"授权有效{suffix}"


def user_chip_display() -> Tuple[str, str, str]:
    """顶栏 Chip：文案、语义 kind、tooltip。"""
    tier = user_plan_tier()
    pack = user_product_pack_label()
    pack_line = pack if pack else "—"
    l2 = user_entitlement_status_line()
    tooltip = (
        f"档位：{tier}\n"
        f"云状态：{l2}\n"
        f"身份/套餐：{pack_line}\n"
        f"{user_validity_line()}"
    )
    if user_plan_expired():
        return "续费", "warning", tooltip
    if tier == OFFICIAL_TIER_LABEL:
        return OFFICIAL_TIER_LABEL, "success", tooltip
    if tier == EXPERIENCE_TIER_LABEL:
        return EXPERIENCE_TIER_LABEL, "info", tooltip
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
    return "有授权码就登录；没有就点「进入软件」，联网后再升级。"


def user_version_caption(*, for_about: bool = False) -> str:
    """关于弹窗专用版本行；开发构建仅在 about 时附带。"""
    base = user_software_version()
    if for_about and dev_build_tag():
        return f"{base} · {dev_build_tag()}"
    return base
