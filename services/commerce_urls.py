# -*- coding: utf-8 -*-
"""TOA 云服务 · 运营台链接。"""
from __future__ import annotations

import urllib.parse

from services.dms_license_client import cloud_origin

_DEFAULT_ORIGIN = "https://toa-service.yczh.tech"


def _origin() -> str:
    return (cloud_origin() or _DEFAULT_ORIGIN).rstrip("/")


def admin_console_url() -> str:
    """运营台主入口（应用壳）。"""
    return f"{_origin()}/admin/app.html"


def admin_purchase_url(*, plan_id: str = "") -> str:
    """运营台产品方案 / 购买相关锚点。"""
    base = admin_console_url()
    if plan_id:
        qs = urllib.parse.urlencode({"plan": plan_id.strip()})
        return f"{base}#packs?{qs}"
    return f"{base}#packs"


def open_admin_console() -> bool:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    return bool(QDesktopServices.openUrl(QUrl(admin_console_url())))


def open_admin_purchase_page(*, plan_id: str = "") -> bool:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    return bool(QDesktopServices.openUrl(QUrl(admin_purchase_url(plan_id=plan_id))))
