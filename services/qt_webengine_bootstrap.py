# -*- coding: utf-8 -*-
"""Qt WebEngine 冻结包路径与可用性检测。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_DSH_RESOURCE_SCHEME = b"dsh-resource"
_dsh_resource_scheme_registered = False


def register_dsh_resource_url_scheme() -> bool:
    """注册 Harness `dsh-resource://` 自定义协议（须在 QApplication / 首个 WebEngine 之前）。

    未注册时，Qt WebEngine 的 JS `new URL('dsh-resource://file/...')` 会把 hostname
    解析成空串；`dsh-client-resources` 因而判定「无 file 提供方」，侧栏预览显示
    「文件资源服务不可用」。系统 Chrome 解析正常，故浏览器里能预览、套件内嵌不行。
    """
    global _dsh_resource_scheme_registered
    if _dsh_resource_scheme_registered:
        return True
    try:
        from PySide6.QtWebEngineCore import QWebEngineUrlScheme
    except ImportError:
        logger.debug("QWebEngineUrlScheme 不可用，跳过 dsh-resource 注册")
        return False
    try:
        existing = QWebEngineUrlScheme.schemeByName(_DSH_RESOURCE_SCHEME)
        name = bytes(existing.name() or b"")
        if name == _DSH_RESOURCE_SCHEME:
            _dsh_resource_scheme_registered = True
            return True
    except Exception:
        pass
    try:
        scheme = QWebEngineUrlScheme(_DSH_RESOURCE_SCHEME)
        scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
        # 仅校正 URL 解析；页面并不真导航到该协议
        scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
        QWebEngineUrlScheme.registerScheme(scheme)
        _dsh_resource_scheme_registered = True
        logger.info("已注册 WebEngine URL scheme: dsh-resource（Harness 侧栏文件预览）")
        return True
    except Exception:
        logger.warning("注册 dsh-resource URL scheme 失败", exc_info=True)
        return False


def configure_qt_webengine() -> None:
    """QApplication 之前：自定义协议 + 冻结包路径。"""
    register_dsh_resource_url_scheme()
    configure_frozen_qt_webengine()


def _frozen_base() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    p = Path(str(base))
    return p if p.is_dir() else None


def configure_frozen_qt_webengine() -> None:
    """在 QApplication 之前设置 WebEngine 子进程、资源路径，以及 Qt 插件目录。"""
    base = _frozen_base()
    if base is None:
        return

    # 图片/平台等插件：冻结包内常在 PySide6/plugins；未设路径时 QImageReader 解不出 jpg/png
    plugin_roots = (
        base / "PySide6" / "plugins",
        base / "plugins",
        base,
    )
    for plugins in plugin_roots:
        img = plugins / "imageformats"
        if img.is_dir() and (
            any(img.glob("q*.dll")) or any(img.glob("q*.so")) or any(img.glob("libq*.so*"))
        ):
            os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))
            # 供后续 QCoreApplication.addLibraryPath 使用
            os.environ.setdefault("TOA_QT_PLUGIN_PATH", str(plugins))
            break

    # 让插件能找到同目录的 Qt6*.dll
    pyside = base / "PySide6"
    if pyside.is_dir():
        path_now = os.environ.get("PATH", "")
        prefix = str(pyside)
        if prefix.lower() not in path_now.lower():
            os.environ["PATH"] = prefix + os.pathsep + path_now

    for proc in (
        base / "PySide6" / "QtWebEngineProcess.exe",
        base / "QtWebEngineProcess.exe",
    ):
        if proc.is_file():
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", str(proc))
            break

    for res in (base / "PySide6" / "resources", base / "resources"):
        if res.is_dir() and any(res.glob("qtwebengine_resources*.pak")):
            os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", str(res))
            break

    for loc in (
        base / "PySide6" / "translations" / "qtwebengine_locales",
        base / "translations" / "qtwebengine_locales",
    ):
        if loc.is_dir():
            os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", str(loc))
            break

    icu_candidates = (
        base / "PySide6" / "resources" / "icudtl.dat",
        base / "resources" / "icudtl.dat",
    )
    for icu in icu_candidates:
        if icu.is_file():
            os.environ.setdefault("QTWEBENGINE_ICU_DATA_PATH", str(icu.parent))
            break


def apply_frozen_qt_library_paths(app=None) -> None:
    """QApplication 创建后补登记插件库路径（双保险）。"""
    from PySide6.QtCore import QCoreApplication

    paths: list[str] = []
    env = (os.environ.get("TOA_QT_PLUGIN_PATH") or os.environ.get("QT_PLUGIN_PATH") or "").strip()
    if env:
        paths.append(env)
    base = _frozen_base()
    if base is not None:
        for p in (base / "PySide6" / "plugins", base / "plugins", base / "PySide6", base):
            if p.is_dir():
                paths.append(str(p))
    for p in paths:
        try:
            QCoreApplication.addLibraryPath(p)
            if app is not None and hasattr(app, "addLibraryPath"):
                app.addLibraryPath(p)
        except Exception:
            logger.debug("addLibraryPath failed: %s", p, exc_info=True)


def webengine_import_ok() -> bool:
    configure_qt_webengine()
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except ImportError as exc:
        logger.debug("Qt WebEngine 不可用: %s", exc)
        return False
