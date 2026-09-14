# -*- coding: utf-8 -*-
"""Qt WebEngine 冻结包路径与可用性检测。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


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
    configure_frozen_qt_webengine()
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except ImportError as exc:
        logger.debug("Qt WebEngine 不可用: %s", exc)
        return False
