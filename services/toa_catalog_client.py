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
from services.license_manager import global_license_manager
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
    modules: list[dict[str, Any]] = []
    for item in get_all_menu_items():
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        if not mid:
            continue
        meta = get_module_meta(mid) or {}
        modules.append(
            {
                "id": mid,
                "name": str(item.get("name") or mid),
                "group": str(item.get("group") or "other"),
                "group_label": str(item.get("group_label") or ""),
                "show": bool(item.get("show", True)),
                "requires_license": bool(item.get("requires_license", False)),
                "feature_id": str(item.get("feature_id") or mid),
                "migration_status": str(meta.get("status") or ""),
            }
        )
    return modules


def publish_menu_catalog_to_cloud() -> tuple[bool, str]:
    lm = global_license_manager
    if not lm.is_admin_user():
        return False, "仅终端管理员可同步菜单目录到云服务"
    info = lm.get_license_info() or lm.license_info or {}
    license_key = str(info.get("license_key") or "").strip()
    if not license_key:
        return False, "请先使用管理员授权码联网激活"
    machine_id = str(info.get("machine_id") or lm.get_machine_id() or "").strip()
    if not machine_id:
        return False, "无法读取本机 machine_id"

    url = _catalog_base_url().rstrip("/") + "/publish"
    body = {
        "license_key": license_key,
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
