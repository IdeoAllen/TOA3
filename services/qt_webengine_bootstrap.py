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
    """在 QApplication 之前设置 WebEngine 子进程与资源路径。"""
    base = _frozen_base()
    if base is None:
        return

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


def webengine_import_ok() -> bool:
    configure_frozen_qt_webengine()
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except ImportError as exc:
        logger.debug("Qt WebEngine 不可用: %s", exc)
        return False
