# -*- coding: utf-8 -*-
"""版本更新检查：异步、短超时、离线可回退本地 manifest。"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.version import APP_VERSION
from services.config_service import get_update_config, project_root
from services.license_client import default_manifest_url

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str | None
    has_update: bool
    download_url: str | None
    release_notes: str | None
    source: str
    error: str | None = None


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    if not text:
        return None
    m = _VERSION_RE.search(str(text).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def compare_versions(current: str, latest: str) -> int:
    """Return -1 if current < latest, 0 if equal, 1 if current > latest."""
    a, b = parse_version(current), parse_version(latest)
    if a is None or b is None:
        return 0 if str(current).strip() == str(latest).strip() else -1
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


@lru_cache(maxsize=1)
def _update_config() -> dict[str, Any]:
    return get_update_config()


def _bundled_manifest() -> dict[str, Any]:
    path = project_root() / "config" / "update_manifest.yml"
    if not path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("读取本地 update_manifest 失败: %s", e)
        return {}


def _fetch_remote_manifest(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def check_for_update(*, timeout_seconds: float | None = None) -> UpdateCheckResult:
    """同步检查（应在工作线程调用，勿阻塞 UI 主线程）。"""
    cfg = _update_config()
    current = APP_VERSION
    if cfg.get("enabled") is False:
        local = _bundled_manifest()
        latest = str(local.get("version") or current)
        return UpdateCheckResult(
            current_version=current,
            latest_version=latest,
            has_update=compare_versions(current, latest) < 0,
            download_url=str(local.get("download_url") or local.get("download_page") or "").strip() or None,
            release_notes=str(local.get("release_notes") or "").strip() or None,
            source="local",
            error="更新检查已关闭",
        )

    timeout = float(timeout_seconds if timeout_seconds is not None else cfg.get("timeout_seconds") or 3.0)
    remote_url = str(cfg.get("manifest_url") or "").strip() or default_manifest_url()
    manifest: dict[str, Any] = {}
    source = "local"
    error: str | None = None

    if remote_url:
        try:
            manifest = _fetch_remote_manifest(remote_url, timeout)
            source = "toa-cloud" if "toa/releases" in remote_url else "remote"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            error = f"TOA 云服务更新清单不可用：{e}"
            logger.info("远程更新 manifest 不可用，回退本地: %s", e)

    if not manifest:
        manifest = _bundled_manifest()
        if error:
            source = "local-fallback"

    latest = str(manifest.get("version") or manifest.get("latest_version") or current).strip()
    download = str(
        manifest.get("download_url") or manifest.get("download_page") or cfg.get("download_page") or ""
    ).strip()
    notes = str(manifest.get("release_notes") or manifest.get("notes") or "").strip() or None
    has_update = compare_versions(current, latest) < 0

    return UpdateCheckResult(
        current_version=current,
        latest_version=latest,
        has_update=has_update,
        download_url=download or None,
        release_notes=notes,
        source=source,
        error=error,
    )


def open_download_page(result: UpdateCheckResult | None = None) -> None:
    """在系统浏览器打开下载页。"""
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtCore import QUrl

    cfg = _update_config()
    url = ""
    if result and result.download_url:
        url = result.download_url
    if not url:
        local = _bundled_manifest()
        url = str(local.get("download_page") or local.get("download_url") or "").strip()
    if not url:
        url = str(cfg.get("download_page") or "").strip()
    if url:
        QDesktopServices.openUrl(QUrl(url))
