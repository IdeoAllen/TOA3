# -*- coding: utf-8 -*-
"""PyInstaller runtime hook：冻结包内 Qt WebEngine 路径。"""
from __future__ import annotations

try:
    from services.qt_webengine_bootstrap import configure_frozen_qt_webengine

    configure_frozen_qt_webengine()
except Exception:
    pass
