# -*- coding: utf-8 -*-
"""网页工作台：可配置站点列表与上次选中。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from services.config_service import project_root
from services.storage_paths import module_data_dir

_CACHE: dict[str, Any] | None = None
_SCHEMA_VERSION = 2
_PRIMARY_ID = "avatr_sheet_2026"


def _user_path() -> Path:
    return module_data_dir("web_workspace", create=True) / "sites.json"


def _load_default_sites() -> list[dict[str, Any]]:
    path = project_root() / "config" / "web_workspace.yml"
    if not path.is_file():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = raw.get("default_sites") or []
        return [x for x in items if isinstance(x, dict) and x.get("url")]
    except Exception:
        return []


def _normalize_site(item: dict[str, Any]) -> dict[str, Any] | None:
    url = str(item.get("url") or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    name = str(item.get("name") or url).strip() or url
    sid = str(item.get("id") or uuid.uuid4().hex[:10])
    return {"id": sid, "name": name, "url": url}


def normalize_url(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    parsed = urlparse(u)
    if not parsed.netloc:
        raise ValueError("请输入有效的 http(s) 地址")
    return u


def _primary_site() -> dict[str, Any]:
    item = _normalize_site(
        {
            "id": _PRIMARY_ID,
            "name": "2026年阿维塔销交项目-大表",
            "url": "https://docs.qq.com/sheet/DZkNPUG9mbWRsRmVm?tab=pfklbk",
        }
    )
    if item is None:
        raise RuntimeError("primary web workspace site invalid")
    return item


def _upgrade_workspace(data: dict[str, Any]) -> dict[str, Any]:
    """合并出厂默认大表站点，并设为默认打开项。"""
    ver = int(data.get("schema_version") or 0)
    sites = [_normalize_site(x) for x in data.get("sites") or [] if isinstance(x, dict)]
    sites = [s for s in sites if s]
    has_primary = any(str(s.get("id")) == _PRIMARY_ID for s in sites)
    if ver >= _SCHEMA_VERSION and has_primary:
        data["sites"] = sites
        return data
    primary = _primary_site()
    rest = [s for s in sites if str(s.get("id")) not in (_PRIMARY_ID, "tencent_docs")]
    data["sites"] = [primary, *rest]
    data["last_id"] = _PRIMARY_ID
    data["schema_version"] = _SCHEMA_VERSION
    save_workspace(data)
    return data


def load_workspace() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = _user_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                sites = [_normalize_site(x) for x in raw.get("sites") or [] if isinstance(x, dict)]
                sites = [s for s in sites if s]
                last = str(raw.get("last_id") or "")
                payload: dict[str, Any] = {
                    "sites": sites,
                    "last_id": last,
                    "schema_version": int(raw.get("schema_version") or 0),
                    "zoom_factor": float(raw.get("zoom_factor") or 1.0),
                }
                _CACHE = _upgrade_workspace(payload)
                return _CACHE
        except Exception:
            pass
    sites = [_normalize_site(x) for x in _load_default_sites()]
    sites = [s for s in sites if s]
    _CACHE = {
        "sites": sites,
        "last_id": sites[0]["id"] if sites else "",
        "schema_version": _SCHEMA_VERSION,
        "zoom_factor": 1.0,
    }
    save_workspace(_CACHE)
    return _CACHE


def save_workspace(data: dict[str, Any]) -> None:
    global _CACHE
    sites = [_normalize_site(x) for x in data.get("sites") or [] if isinstance(x, dict)]
    sites = [s for s in sites if s]
    last = str(data.get("last_id") or "")
    if last and not any(s["id"] == last for s in sites):
        last = sites[0]["id"] if sites else ""
    try:
        zoom = float(data.get("zoom_factor") or 1.0)
    except (TypeError, ValueError):
        zoom = 1.0
    zoom = max(0.75, min(1.75, zoom))
    payload = {
        "sites": sites,
        "last_id": last,
        "schema_version": int(data.get("schema_version") or _SCHEMA_VERSION),
        "zoom_factor": zoom,
    }
    _CACHE = payload
    path = _user_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_zoom_factor() -> float:
    try:
        return float(load_workspace().get("zoom_factor") or 1.0)
    except (TypeError, ValueError):
        return 1.0


def set_zoom_factor(zoom: float) -> float:
    data = load_workspace()
    z = max(0.75, min(1.75, float(zoom)))
    data["zoom_factor"] = round(z, 2)
    save_workspace(data)
    return z


def list_sites() -> list[dict[str, Any]]:
    return list(load_workspace().get("sites") or [])


def get_site(site_id: str) -> dict[str, Any] | None:
    sid = str(site_id or "").strip()
    for item in list_sites():
        if str(item.get("id")) == sid:
            return item
    return None


def set_last_site(site_id: str) -> None:
    data = load_workspace()
    sid = str(site_id or "").strip()
    if not any(str(s.get("id")) == sid for s in data.get("sites") or []):
        return
    data["last_id"] = sid
    save_workspace(data)


def add_site(name: str, url: str) -> dict[str, Any]:
    data = load_workspace()
    entry = _normalize_site(
        {"id": uuid.uuid4().hex[:10], "name": name, "url": normalize_url(url)}
    )
    if entry is None:
        raise ValueError("站点无效")
    sites = list(data.get("sites") or [])
    sites.append(entry)
    data["sites"] = sites
    data["last_id"] = entry["id"]
    save_workspace(data)
    return entry


def update_site(site_id: str, *, name: str, url: str) -> None:
    data = load_workspace()
    sid = str(site_id or "").strip()
    found = False
    sites: list[dict[str, Any]] = []
    for item in data.get("sites") or []:
        if str(item.get("id")) != sid:
            sites.append(item)
            continue
        found = True
        sites.append(
            _normalize_site({"id": sid, "name": name, "url": normalize_url(url)}) or item
        )
    if not found:
        raise ValueError("站点不存在")
    data["sites"] = sites
    save_workspace(data)


def delete_site(site_id: str) -> None:
    data = load_workspace()
    sid = str(site_id or "").strip()
    sites = [s for s in data.get("sites") or [] if str(s.get("id")) != sid]
    data["sites"] = sites
    if str(data.get("last_id") or "") == sid:
        data["last_id"] = sites[0]["id"] if sites else ""
    save_workspace(data)


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None
