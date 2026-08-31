# -*- coding: utf-8 -*-
"""用户扩展 WebView 表面：QWebChannel 白名单桥（本地 HTML ↔ TOA 能力）。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot

from core.status_service import StatusLevel
from core.user_messages import show_saved
from services.storage_paths import module_data_dir, module_output_dir

if TYPE_CHECKING:
    from core.extension_web_page import ExtensionWebPage
    from services.plugin_pack import PluginManifest

logger = logging.getLogger(__name__)

_LEVELS = {
    "info": StatusLevel.INFO,
    "success": StatusLevel.SUCCESS,
    "warning": StatusLevel.WARNING,
    "error": StatusLevel.ERROR,
}


def _safe_child(base: Path, relative: str) -> Path | None:
    rel = str(relative or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    try:
        target = (base / rel).resolve()
        base_r = base.resolve()
        if not str(target).startswith(str(base_r)):
            return None
        return target
    except OSError:
        return None


class ExtensionWebBridge(QObject):
    """暴露给扩展 ui/*.html 的宿主 API（经 QWebChannel 对象名 toa）。"""

    def __init__(self, page: ExtensionWebPage, manifest: PluginManifest) -> None:
        super().__init__(page)
        self._page = page
        self._manifest = manifest
        self._data_root = module_data_dir(manifest.plugin_id, create=True)
        self._output_root = module_output_dir(manifest.plugin_id, create=True)

    @Slot(result=str)
    def pluginId(self) -> str:
        return self._manifest.plugin_id

    @Slot(result=str)
    def pluginName(self) -> str:
        return self._manifest.name

    @Slot(result=str)
    def dataDir(self) -> str:
        return str(self._data_root)

    @Slot(result=str)
    def outputDir(self) -> str:
        return str(self._output_root)

    @Slot(result=str)
    def themePalette(self) -> str:
        from app.app_state import AppState

        pal = dict(AppState.get().palette or {})
        return json.dumps(pal, ensure_ascii=False)

    @Slot(result=str)
    def themeId(self) -> str:
        from app.app_state import AppState

        return str(AppState.get().theme_id or "")

    @Slot(str, str)
    def reportStatus(self, text: str, level: str = "info") -> None:
        lv = _LEVELS.get(str(level or "info").strip().lower(), StatusLevel.INFO)
        self._page.report_status(str(text or ""), level=lv)

    @Slot(str, str)
    def showSaved(self, text: str, path: str) -> None:
        p = str(path or "").strip()
        if not p:
            self.reportStatus("缺少保存路径", level="warning")
            return
        show_saved(self._page, str(text or "已完成"), p)

    @Slot(str, result=str)
    def readTextFile(self, relative_path: str) -> str:
        target = _safe_child(self._data_root, relative_path)
        if target is None or not target.is_file():
            return ""
        try:
            return target.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug("readTextFile failed: %s", exc)
            return ""

    @Slot(str, str, result=bool)
    def writeTextFile(self, relative_path: str, content: str) -> bool:
        target = _safe_child(self._data_root, relative_path)
        if target is None:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content or ""), encoding="utf-8")
            return True
        except OSError as exc:
            logger.debug("writeTextFile failed: %s", exc)
            return False
