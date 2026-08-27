# -*- coding: utf-8 -*-
"""在系统文件管理器中打开路径 / 选中文件。"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def open_in_file_manager(path: str | Path, *, select: bool = False) -> bool:
    """打开目录，或打开所在目录并选中文件（Windows explorer /select）。"""
    p = Path(path)
    try:
        if select and p.is_file():
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", str(p.resolve())], check=False)
                return True
            folder = p.parent
        elif p.is_dir():
            folder = p
        elif p.parent.is_dir():
            folder = p.parent
        else:
            logger.warning("路径不存在: %s", p)
            return False

        if sys.platform == "win32":
            os.startfile(str(folder))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder)], check=False)
        else:
            subprocess.run(["xdg-open", str(folder)], check=False)
        return True
    except Exception as e:
        logger.warning("打开文件管理器失败: %s", e)
        return False
