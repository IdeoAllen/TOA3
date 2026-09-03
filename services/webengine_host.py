# -*- coding: utf-8 -*-
"""内嵌 WebEngine 共用：文件选择、背景色、减轻闪白。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWidgets import QFileDialog, QWidget


def theme_surface_color() -> QColor:
    try:
        from app.app_state import AppState

        bg = str((AppState.get().palette or {}).get("surface") or "#FFFCF8")
        return QColor(bg)
    except Exception:
        return QColor("#FFFCF8")


def _mime_to_filter(accepted_mime_types: list[str] | None) -> str:
    mimes = [str(m or "").strip().lower() for m in (accepted_mime_types or []) if str(m or "").strip()]
    if not mimes:
        return "所有文件 (*.*)"
    parts: list[str] = []
    if any(m.startswith("image/") or m == "image/*" for m in mimes):
        parts.append("图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)")
    if any(m in ("audio/*",) or m.startswith("audio/") for m in mimes):
        parts.append("音频 (*.mp3 *.wav *.flac *.ogg *.m4a)")
    if any(m in ("video/*",) or m.startswith("video/") for m in mimes):
        parts.append("视频 (*.mp4 *.webm *.mov *.avi *.mkv)")
    if any("json" in m for m in mimes):
        parts.append("JSON (*.json)")
    parts.append("所有文件 (*.*)")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return ";;".join(out)


def choose_files_for_web(
    parent: QWidget | None,
    mode: QWebEnginePage.FileSelectionMode,
    old_files: list[str] | None,
    accepted_mime_types: list[str] | None,
) -> list[str]:
    """供 QWebEnginePage.chooseFiles 调用：把网页 <input type=file> 接到系统对话框。"""
    start = ""
    if old_files:
        start = str(old_files[0] or "")
    filt = _mime_to_filter(accepted_mime_types)
    Mode = QWebEnginePage.FileSelectionMode
    if mode == Mode.FileSelectOpenMultiple:
        paths, _ = QFileDialog.getOpenFileNames(parent, "选择文件", start, filt)
        return list(paths or [])
    if mode == Mode.FileSelectUploadFolder:
        path = QFileDialog.getExistingDirectory(parent, "选择文件夹", start or "")
        return [path] if path else []
    if mode == Mode.FileSelectSave:
        path, _ = QFileDialog.getSaveFileName(parent, "保存文件", start, filt)
        return [path] if path else []
    # FileSelectOpen
    path, _ = QFileDialog.getOpenFileName(parent, "选择文件", start, filt)
    return [path] if path else []


class ToaWebEnginePage(QWebEnginePage):
    """带本机文件对话框的页面（ComfyUI / 任意网页选文件必需）。"""

    def __init__(self, profile, parent=None, *, accept_nav: Callable | None = None) -> None:
        super().__init__(profile, parent)
        self._accept_nav = accept_nav
        try:
            self.setBackgroundColor(theme_surface_color())
        except Exception:
            pass

    def chooseFiles(self, mode, old_files, accepted_mime_types):  # noqa: N802
        parent = None
        try:
            parent = self.view()
        except Exception:
            parent = None
        try:
            return choose_files_for_web(
                parent,
                mode,
                list(old_files or []),
                list(accepted_mime_types or []),
            )
        except Exception:
            return []

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
        if self._accept_nav is not None:
            try:
                return bool(self._accept_nav(url, nav_type, is_main_frame))
            except Exception:
                return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _type):  # noqa: N802
        return self


def apply_webengine_view_defaults(view) -> None:
    """嵌入视图默认设置：背景色 + 常用能力。

    勿 WA_OpaquePaintEvent、勿在 MousePress 里 setFocus：会干扰 Comfy LiteGraph 下拉命中。
    """
    try:
        view.setAutoFillBackground(True)
        view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        pal = view.palette()
        pal.setColor(view.backgroundRole(), theme_surface_color())
        view.setPalette(pal)
    except Exception:
        pass
    try:
        settings = view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True
        )
        settings.setFontFamily(
            QWebEngineSettings.FontFamily.StandardFont, "Microsoft YaHei UI"
        )
        settings.setFontFamily(
            QWebEngineSettings.FontFamily.SansSerifFont, "Microsoft YaHei UI"
        )
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, 14)
        settings.setFontSize(QWebEngineSettings.FontSize.MinimumFontSize, 10)
    except Exception:
        pass
    # 清理旧版误装的 MousePress→setFocus 过滤器（会吞掉下拉点击）
    try:
        filt = getattr(view, "_toa_focus_filter", None)
        if filt is not None:
            view.removeEventFilter(filt)
            view._toa_focus_filter = None
    except Exception:
        pass
