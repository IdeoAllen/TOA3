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

from PySide6.QtCore import QObject, QTimer, Qt, Signal

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
    download_page: str | None = None
    min_version: str | None = None
    below_min_version: bool = False


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


def _resolve_urls(manifest: dict[str, Any], cfg: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (installer_url, landing_page_url). Prefer page for browser open."""
    installer = str(manifest.get("download_url") or "").strip() or None
    page = str(
        manifest.get("download_page") or cfg.get("download_page") or ""
    ).strip() or None
    if not page:
        local = _bundled_manifest()
        page = str(local.get("download_page") or "").strip() or None
    if not installer and not page:
        installer = str(cfg.get("download_page") or "").strip() or None
    return installer, page


def check_for_update(*, timeout_seconds: float | None = None) -> UpdateCheckResult:
    """同步检查（应在工作线程调用，勿阻塞 UI 主线程）。"""
    cfg = _update_config()
    current = APP_VERSION
    if cfg.get("enabled") is False:
        local = _bundled_manifest()
        latest = str(local.get("version") or current)
        installer, page = _resolve_urls(local, cfg)
        min_ver = str(local.get("min_version") or "").strip() or None
        below = bool(min_ver and compare_versions(current, min_ver) < 0)
        return UpdateCheckResult(
            current_version=current,
            latest_version=latest,
            has_update=compare_versions(current, latest) < 0 or below,
            download_url=installer,
            download_page=page,
            release_notes=str(local.get("release_notes") or "").strip() or None,
            source="local",
            error="更新检查已关闭",
            min_version=min_ver,
            below_min_version=below,
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
    installer, page = _resolve_urls(manifest, cfg)
    notes = str(manifest.get("release_notes") or manifest.get("notes") or "").strip() or None
    min_ver = str(manifest.get("min_version") or "").strip() or None
    below = bool(min_ver and compare_versions(current, min_ver) < 0)
    has_update = compare_versions(current, latest) < 0 or below

    return UpdateCheckResult(
        current_version=current,
        latest_version=latest,
        has_update=has_update,
        download_url=installer,
        download_page=page,
        release_notes=notes,
        source=source,
        error=error,
        min_version=min_ver,
        below_min_version=below,
    )


def open_download_page(result: UpdateCheckResult | None = None) -> None:
    """在系统浏览器打开下载落地页（优先），无页时再回退安装包直链。"""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    cfg = _update_config()
    url = ""
    if result and result.download_page:
        url = result.download_page
    if not url:
        local = _bundled_manifest()
        url = str(local.get("download_page") or "").strip()
    if not url:
        url = str(cfg.get("download_page") or "").strip()
    if not url and result and result.download_url:
        url = result.download_url
    if not url:
        local = _bundled_manifest()
        url = str(local.get("download_url") or "").strip()
    if url:
        QDesktopServices.openUrl(QUrl(url))


def format_update_message(result: UpdateCheckResult) -> str:
    """手动检查有更新时的提示文案。"""
    parts: list[str] = []
    if result.below_min_version and result.min_version:
        parts.append(
            f"当前版本 {result.current_version} 低于最低可升级要求 "
            f"v{result.min_version}，请尽快升级。"
        )
    if result.latest_version and compare_versions(result.current_version, result.latest_version) < 0:
        parts.append(
            f"发现新版本 {result.latest_version}（当前 {result.current_version}）。"
        )
    elif not parts and result.latest_version:
        parts.append(f"请升级到 v{result.latest_version}（当前 {result.current_version}）。")
    if result.release_notes:
        parts.append(result.release_notes.strip())
    parts.append("将打开下载页。")
    return "\n\n".join(parts)


def is_offline_update_source(result: UpdateCheckResult) -> bool:
    src = (result.source or "").strip()
    return src in ("local-fallback", "timeout", "error", "local") or (
        bool(result.error) and src.startswith("local")
    )


def format_up_to_date_message(result: UpdateCheckResult, *, for_tray: bool = False) -> str:
    """无可用更新（或检查失败）时的提示；离线回退不伪装「云端已确认最新」。"""
    src = (result.source or "").strip()
    if src in ("timeout", "error"):
        msg = (result.error or "检查更新失败，请稍后重试。").strip()
        return msg if for_tray else msg

    offline = src == "local-fallback" or (
        bool(result.error) and src.startswith("local")
    )
    if offline:
        if for_tray:
            return "无法连接更新服务，请联网后再检查"
        lines = [
            "无法连接 TOA 云服务更新清单，以下为离线对照（可能不是最新）。",
            f"当前版本 {result.current_version}"
            + (f" · 离线清单 {result.latest_version}" if result.latest_version else ""),
        ]
        if result.error:
            lines.append(f"原因：{result.error}")
        lines.append("恢复网络后请再检查一次。")
        return "\n\n".join(lines)

    if for_tray:
        return f"当前版本 {result.current_version} 已是最新"

    msg = f"当前版本 {result.current_version} 已是最新。"
    if src.startswith("toa"):
        msg += "\n（来源：TOA 云服务）"
    elif src:
        msg += f"\n（来源：{src}）"
    if result.error and src == "local":
        # 更新检查已关闭等
        msg += f"\n\n提示：{result.error}"
    return msg


def start_update_check_thread(*, on_finished, reason: str = "manual"):
    """在后台线程检查更新；on_finished(UpdateCheckResult) 在主线程回调。"""
    return get_update_hub().check_async(on_finished=on_finished, reason=reason)


class _UpdateWorker(QObject):
    finished = Signal(object)

    def run(self) -> None:
        try:
            self.finished.emit(check_for_update())
        except Exception as exc:
            self.finished.emit(
                UpdateCheckResult(
                    current_version=APP_VERSION,
                    latest_version=None,
                    has_update=False,
                    download_url=None,
                    download_page=None,
                    release_notes=None,
                    source="error",
                    error=str(exc),
                )
            )


class UpdateCheckHub(QObject):
    """进程内单例：避免线程被 GC、统一 busy 状态与 12s 看门狗。"""

    result_ready = Signal(object)
    checking_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checking = False
        self._last: UpdateCheckResult | None = None
        self._reason = "manual"
        self._thread = None
        self._worker = None
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)

    def is_checking(self) -> bool:
        return self._checking

    def last_result(self) -> UpdateCheckResult | None:
        return self._last

    def last_reason(self) -> str:
        return self._reason

    def check_async(self, *, on_finished=None, reason: str = "manual") -> None:
        from PySide6.QtCore import QThread

        if self._checking:
            return
        self._reason = str(reason or "manual")
        self._checking = True
        self.checking_changed.emit(True)
        self._watchdog.start(12000)

        self._thread = QThread(self)
        self._worker = _UpdateWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        def _done(result: object) -> None:
            self._watchdog.stop()
            if not self._checking:
                return
            self._checking = False
            if isinstance(result, UpdateCheckResult):
                self._last = result
            self.checking_changed.emit(False)
            self.result_ready.emit(result)
            if on_finished:
                on_finished(result)
            if self._thread is not None:
                self._thread.quit()

        self._worker.finished.connect(_done, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _on_watchdog(self) -> None:
        if not self._checking:
            return
        logger.warning("检查更新超时，强制结束")
        self._checking = False
        self.checking_changed.emit(False)
        result = UpdateCheckResult(
            current_version=APP_VERSION,
            latest_version=None,
            has_update=False,
            download_url=None,
            download_page=None,
            release_notes=None,
            source="timeout",
            error="检查更新超时，请稍后重试",
        )
        self._last = result
        self.result_ready.emit(result)
        thread = self._thread
        worker = self._worker
        self._thread = None
        self._worker = None
        if thread is not None:
            try:
                thread.quit()
                if not thread.wait(800):
                    thread.terminate()
                    thread.wait(500)
            except Exception:
                logger.debug("update check thread cleanup failed", exc_info=True)
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass


_HUB: UpdateCheckHub | None = None


def get_update_hub() -> UpdateCheckHub:
    global _HUB
    if _HUB is None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        _HUB = UpdateCheckHub(app)
    return _HUB
