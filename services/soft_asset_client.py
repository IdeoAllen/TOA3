# -*- coding: utf-8 -*-
"""终端 ↔ TOA 云：办公插件投稿 / 公示检索 / 下载（无偿流通）。"""
from __future__ import annotations

import base64
import json
import logging
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services.commerce_urls import admin_console_url
from services.dms_license_client import cloud_origin
from services.extension_pack_io import export_extension_zip, import_extension_zip
from services.license_manager import global_license_manager, is_full_license_code

logger = logging.getLogger("TOA3.soft_assets")


def soft_assets_base_url() -> str:
    origin = (cloud_origin() or "https://toa-service.yczh.tech").rstrip("/")
    return f"{origin}/api/toa-soft-assets"


def _optional_machine_id() -> str:
    try:
        lm = global_license_manager
        info = lm.get_license_info() or lm.license_info or {}
        return str(info.get("machine_id") or lm.get_machine_id() or "").strip()
    except Exception:
        return ""


def _post_json(url: str, body: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
            msg = str(payload.get("detail") or payload.get("message") or detail)
        except Exception:
            msg = detail or str(e)
        raise ValueError(msg) from e
    except urllib.error.URLError as e:
        raise ValueError(f"无法连接运营台：{e.reason}") from e


def _get_json(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
            msg = str(payload.get("detail") or detail)
        except Exception:
            msg = detail or str(e)
        raise ValueError(msg) from e
    except urllib.error.URLError as e:
        raise ValueError(f"无法连接运营台：{e.reason}") from e


def list_public_plugins(*, q: str = "", limit: int = 100) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({"q": q or "", "kind": "extension.pack", "status": "approved"})
    url = f"{soft_assets_base_url()}?{qs}"
    data = _get_json(url)
    items = data.get("items") or []
    return list(items)[: max(1, min(int(limit), 200))]


def submit_extension_to_cloud(root: Path | str) -> dict[str, Any]:
    """导出并投稿到运营台（待审）。无偿开放，无需授权码。"""
    mid = _optional_machine_id()
    # 有完整授权码则顺带关联账号；没有也不拦
    key = ""
    try:
        k, _hint = global_license_manager.resolve_cloud_license_key()
        if k and is_full_license_code(k):
            key = k
    except Exception:
        key = ""
    with tempfile.TemporaryDirectory(prefix="toa_submit_") as tmp:
        zip_path = Path(tmp) / "pack.toa-ext.zip"
        result = export_extension_zip(root, zip_path)
        raw = zip_path.read_bytes()
        body = {
            "license_key": key,
            "machine_id": mid,
            "meta": result.meta,
            "zip_base64": base64.b64encode(raw).decode("ascii"),
        }
        data = _post_json(f"{soft_assets_base_url()}/submit-json", body, timeout=120.0)
    if not data.get("ok"):
        raise ValueError(str(data.get("detail") or "投稿失败"))
    return data.get("asset") or {}


def download_and_install_plugin(asset_id: int, *, show: bool = False) -> tuple[str, str]:
    """公开下载公示插件并导入本机（无授权门槛）；返回 (plugin_id, name)。"""
    mid = _optional_machine_id()
    qs = urllib.parse.urlencode({"machine_id": mid}) if mid else ""
    url = f"{soft_assets_base_url()}/{int(asset_id)}/download"
    if qs:
        url = f"{url}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/zip"},
        method="GET",
    )
    with tempfile.TemporaryDirectory(prefix="toa_dl_") as tmp:
        dest = Path(tmp) / f"asset_{asset_id}.toa-ext.zip"
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                dest.write_bytes(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(detail)
                msg = str(payload.get("detail") or detail)
            except Exception:
                msg = detail or str(e)
            raise ValueError(msg) from e
        except urllib.error.URLError as e:
            raise ValueError(f"无法连接运营台：{e.reason}") from e
        imported = import_extension_zip(dest, show=show)
    return imported.plugin_id, imported.name


def ops_console_hint() -> str:
    return admin_console_url()
