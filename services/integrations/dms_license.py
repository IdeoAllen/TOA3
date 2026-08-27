# -*- coding: utf-8 -*-
"""DMS TOA License API 客户端 — 委托 license_client / TOA 云服务。"""
from __future__ import annotations

import logging
from typing import Any

from core.exceptions import IntegrationError
from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config
from services.license_client import cloud_health_check

logger = logging.getLogger(__name__)


class DmsLicenseClient(IntegrationClient):
    name = "dms"

    def __init__(self) -> None:
        super().__init__(integration_config("dms"))

    def health_check(self) -> bool:
        if cloud_health_check(timeout=min(float(self.timeout), 3.0)):
            return True
        if not self.enabled:
            return False
        base = str(self._config.get("base_url") or "").strip().rstrip("/")
        if not base:
            return False
        probe_timeout = min(float(self.timeout), 3.0)
        try:
            import urllib.request

            req = urllib.request.Request(base + "/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=probe_timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning("云服务/DMS health_check 失败: %s", e)
            return False

    def activate(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_enabled()
        from services.license_client import activate_on_cloud

        ok, msg, data = activate_on_cloud(
            str((payload or {}).get("license_key") or ""),
            str((payload or {}).get("machine_id") or ""),
            str((payload or {}).get("app_version") or ""),
        )
        if not ok:
            raise IntegrationError("dms", msg or "activate failed", user_message=msg)
        return data or {}

    def check(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_enabled()
        from services.license_client import check_on_cloud

        ok, msg, data = check_on_cloud(
            str((payload or {}).get("code_id") or ""),
            str((payload or {}).get("machine_id") or ""),
            str((payload or {}).get("license_key") or ""),
            force=True,
            blocking=True,
        )
        if not ok:
            raise IntegrationError("dms", msg or "check failed", user_message=msg)
        return data or {}


def get_dms_client() -> DmsLicenseClient:
    return DmsLicenseClient()
