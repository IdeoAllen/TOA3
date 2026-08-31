# -*- coding: utf-8 -*-
"""用户扩展 WebView 表面：宿主薄壳 + 本地 file:// HTML + QWebChannel。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from services.extension_web_bridge import ExtensionWebBridge
from services.harness_web_bridge import apply_theme_harmonize

if TYPE_CHECKING:
    from services.plugin_pack import PluginManifest

logger = logging.getLogger(__name__)


def _webengine_available() -> bool:
    from services.qt_webengine_bootstrap import webengine_import_ok

    return webengine_import_ok()


def _file_url(path: Path) -> QUrl:
    return QUrl.fromLocalFile(str(path.resolve()))


class ExtensionWebPage(BasePage):
    """加载扩展目录内 ui/*.html；导航限制在扩展根 + 可选联网。"""

    def __init__(self, manifest: PluginManifest, parent=None) -> None:
        super().__init__(parent)
        self.page_id = manifest.plugin_id
        self.page_title = manifest.name
        self._manifest = manifest
        self._root = manifest.root.resolve()
        self._entry = manifest.web_entry_file.resolve()
        self._view = None
        self._profile = None
        self._bridge: ExtensionWebBridge | None = None
        self._channel = None
        self._ready = _webengine_available()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._host = QWidget()
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._host, 1)

        if not self._ready:
            from widgets import HintLabel

            hint = HintLabel("本机未安装 Qt WebEngine，无法打开网页型扩展。\n请使用完整安装包或联系管理员。")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._host_lay.addWidget(hint, 1)
            return

        if not self._entry.is_file():
            from widgets import HintLabel

            hint = HintLabel(
                f"缺少网页入口：{manifest.web_root}\n请在扩展目录创建该文件后点「开发完成」。"
            )
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._host_lay.addWidget(hint, 1)

    def on_enter(self) -> None:
        if not self._ready or not self._entry.is_file():
            return
        self._ensure_view()
        if self._view is not None:
            self._view.load(_file_url(self._entry))

    def on_theme_changed(self, theme_id: str, palette: dict) -> None:
        if self._view is not None and palette:
            apply_theme_harmonize(self._view, palette)

    def _ensure_view(self) -> None:
        if self._view is not None:
            return
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from services.storage_paths import module_data_dir

        profile_dir = module_data_dir(self._manifest.plugin_id, create=True) / "webview_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile(f"toa3_ext_{self._manifest.plugin_id}", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(profile_dir / "cache"))

        manifest = self._manifest
        root = self._root

        class _GuardPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
                if not is_main_frame:
                    return True
                scheme = (url.scheme() or "").lower()
                if scheme == "qrc":
                    return True
                if scheme == "file":
                    try:
                        local = Path(url.toLocalFile()).resolve()
                        if str(local).startswith(str(root)):
                            return True
                    except OSError:
                        return False
                    return False
                if manifest.allow_network and scheme in ("http", "https"):
                    return True
                return False

        self._view = QWebEngineView(self._host)
        page = _GuardPage(self._profile, self._view)
        self._view.setPage(page)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            bool(manifest.allow_network),
        )
        settings.setFontFamily(QWebEngineSettings.FontFamily.StandardFont, "Microsoft YaHei UI")
        settings.setFontFamily(QWebEngineSettings.FontFamily.SansSerifFont, "Microsoft YaHei UI")
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, 14)

        self._bridge = ExtensionWebBridge(self, manifest)
        self._channel = QWebChannel(page)
        self._channel.registerObject("toa", self._bridge)
        page.setWebChannel(self._channel)

        self._view.loadFinished.connect(self._on_load_finished)
        self._host_lay.addWidget(self._view, 1)

        from app.app_state import AppState

        pal = dict(AppState.get().palette or {})
        if pal:
            apply_theme_harmonize(self._view, pal)

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            self.report_status("网页扩展就绪", level=StatusLevel.SUCCESS)
        else:
            self.report_status("网页加载失败，请检查 ui 入口文件", level=StatusLevel.WARNING)


def create_extension_web_page(manifest: PluginManifest) -> ExtensionWebPage:
    return ExtensionWebPage(manifest)
