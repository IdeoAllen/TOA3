# -*- coding: utf-8 -*-
"""终端管理员：将本机菜单目录同步至 TOA 云服务（供运营台组包）。"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.version import APP_VERSION
from services.config_service import get_all_menu_items, load_config
from services.license_manager import global_license_manager, is_full_license_code
from services.migration_manifest import get_module_meta

logger = logging.getLogger("TOA3.catalog")


def _catalog_base_url() -> str:
    cfg = load_config()
    lic = cfg.get("license") or {}
    service = str(lic.get("service_url") or "").strip().rstrip("/")
    if service.endswith("/api/toa-license"):
        return service[: -len("/api/toa-license")] + "/api/toa/menu-catalog"
    if service:
        return service.rsplit("/api/", 1)[0] + "/api/toa/menu-catalog"
    return "https://toa-service.yczh.tech/api/toa/menu-catalog"


def build_menu_catalog_payload() -> list[dict[str, Any]]:
    from services.config_service import get_group_labels
    from services.menu_registry import get_group_order

    labels = get_group_labels()
    group_rank = {gid: idx for idx, gid in enumerate(get_group_order())}
    modules: list[dict[str, Any]] = []
    for item in get_all_menu_items():
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        if not mid:
            continue
        meta = get_module_meta(mid) or {}
        gid = str(item.get("group") or "other").strip().lower()
        modules.append(
            {
                "id": mid,
                "name": str(item.get("name") or mid),
                "group": gid,
                "group_label": str(labels.get(gid) or item.get("group_label") or ""),
                "order": int(item.get("order") or 0),
                "group_order": int(group_rank.get(gid, 99)),
                "show": bool(item.get("show", True)),
                "requires_license": bool(item.get("requires_license", False)),
                "feature_id": str(item.get("feature_id") or mid),
                "migration_status": str(meta.get("status") or ""),
            }
        )
    modules.sort(
        key=lambda m: (int(m.get("group_order") or 99), int(m.get("order") or 0), str(m.get("id") or ""))
    )
    return modules


def publish_menu_catalog_to_cloud(*, license_key: str = "") -> tuple[bool, str]:
    lm = global_license_manager
    if not lm.is_admin_user():
        return False, "仅终端管理员可同步菜单目录到云服务"

    key = (license_key or "").strip()
    if not key:
        key, hint = lm.resolve_cloud_license_key()
        if not key:
            return False, hint or "请先使用管理员授权码联网激活"

    if not is_full_license_code(key):
        return False, "授权码格式无效，请粘贴运营台签发的完整 TOA2 授权码"

    ok, msg, payload = lm.verify_license_code(key)
    if not ok:
        return False, msg or "授权码无效"
    role = str((payload or {}).get("role") or "").strip().lower()
    if role != "admin":
        return False, "同步目录需要管理员授权码"

    info = lm.get_license_info() or lm.license_info or {}
    machine_id = str(info.get("machine_id") or lm.get_machine_id() or "").strip()
    if not machine_id:
        return False, "无法读取本机 machine_id"

    url = _catalog_base_url().rstrip("/") + "/publish"
    body = {
        "license_key": key,
        "machine_id": machine_id,
        "app_version": APP_VERSION,
        "modules": build_menu_catalog_payload(),
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = exc.reason
        return False, str(detail or f"HTTP {exc.code}")
    except Exception as exc:
        logger.warning("publish menu catalog failed: %s", exc)
        return False, str(exc)

    published = payload.get("published")
    return True, f"已同步 {published} 个 module 至运营台（TOA3 v{APP_VERSION}）"
