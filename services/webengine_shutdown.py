# -*- coding: utf-8 -*-
"""退出前释放 Qt WebEngine，减轻 PyInstaller _MEI 临时目录删不掉。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def prepare_app_exit() -> None:
    """在 QApplication 退出前调用：卸载内嵌页、处理 pending 事件。"""
    try:
        from services.webengine_prewarm import release_prewarm_hold

        release_prewarm_hold()
    except Exception:
        pass
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        return

    blank = QUrl("about:blank")
    for view in list(app.findChildren(QWebEngineView)):
        try:
            page = view.page()
            if page is not None:
                page.setUrl(blank)
                profile = page.profile()
                if profile is not None:
                    try:
                        profile.clearHttpCache()
                    except Exception:
                        pass
            view.setUrl(blank)
            view.hide()
            view.deleteLater()
        except Exception:
            logger.debug("释放 WebEngineView 失败", exc_info=True)

    try:
        app.processEvents()
    except Exception:
        pass

    if _frozen_on_windows():
        try:
            import os
            import subprocess

            subprocess.run(
                ["taskkill", "/F", "/IM", "QtWebEngineProcess.exe", "/T"],
                capture_output=True,
                timeout=2,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            logger.debug("结束 QtWebEngineProcess 失败", exc_info=True)


def _frozen_on_windows() -> bool:
    import sys

    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))
