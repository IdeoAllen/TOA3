# -*- coding: utf-8 -*-
"""TOA 云服务授权客户端（推荐入口）。

实现位于 dms_license_client（历史文件名）；新代码请从此模块导入。
"""
from __future__ import annotations

from services.config_service import get_license_config, get_update_config
from services.dms_license_client import (  # noqa: F401
    FAIL_STATUSES,
    activate_on_cloud,
    activate_on_dms,
    apply_cloud_identity,
    apply_dms_identity,
    check_on_cloud,
    check_on_dms,
    cloud_health_check,
    cloud_origin,
    dms_base_url,
    invalidate_check_cache,
    is_local_dms,
    is_local_license_service,
    license_api_base,
    license_service_url,
    offline_grace_days,
    peek_check_cache,
    reconcile_roster_on_cloud,
    reconcile_roster_on_dms,
    register_on_cloud,
    register_on_dms,
    sync_roster_on_cloud,
    sync_roster_on_dms,
    within_grace,
)


def default_manifest_url(*, product: str = "TOA3", channel: str = "stable") -> str:
    """从 update.manifest_url 或 license.service_url 推导远程 manifest 地址。"""
    upd = get_update_config()
    explicit = str(upd.get("manifest_url") or "").strip()
    if explicit:
        return explicit
    origin = cloud_origin()
    if origin:
        return f"{origin}/api/toa/releases/manifest?product={product}&channel={channel}"
    return ""


def license_service_summary() -> str:
    """设置页/关于页展示用一行摘要。"""
    lic = get_license_config()
    if str(lic.get("service_url") or "").strip():
        return license_service_url()
    fb = dms_base_url()
    return f"{fb}（DMS 过渡 fallback）"
