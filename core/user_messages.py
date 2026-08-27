# -*- coding: utf-8 -*-
"""统一用户提示窗（全应用唯一弹窗入口）。"""
from __future__ import annotations

import logging
import os
from typing import Union

from PySide6.QtWidgets import QWidget

from core.message_dialog import MessageDialog
from core.ui_spec import message_title

logger = logging.getLogger("TOA3.ui")


def show_info(parent: QWidget | None, text: str, *, title: str | None = None) -> None:
    title = title or message_title("info")
    logger.info("提示窗 [%s]: %s", title, text.replace("\n", " "))
    MessageDialog.run(parent, "info", text, title=title)


def show_saved(
    parent: QWidget | None,
    text: str,
    path: Union[str, os.PathLike[str], None] = None,
    *,
    title: str | None = None,
) -> None:
    """生成/导出/保存成功：绿色「完成」对话框，并提供「打开所在目录」。

    凡产出文件或目录的功能必须走本入口（禁止用 show_info 冒充完成）。
    ``path`` 为刚生成的文件或输出目录，供「打开所在目录」定位。
    """
    title = title or message_title("success")
    open_path = str(path) if path else None
    if not open_path:
        logger.warning("show_saved 未传 path，将无「打开所在目录」按钮")
    logger.info("完成提示 [%s]: %s", title, text.replace("\n", " "))
    MessageDialog.run(parent, "success", text, title=title, open_path=open_path)


def show_warning(parent: QWidget | None, text: str, *, title: str | None = None) -> None:
    title = title or message_title("warning")
    logger.warning("警告窗 [%s]: %s", title, text.replace("\n", " "))
    MessageDialog.run(parent, "warning", text, title=title)


def show_error(parent: QWidget | None, text: str, *, title: str | None = None) -> None:
    title = title or message_title("error")
    logger.error("错误窗 [%s]: %s", title, text.replace("\n", " "))
    MessageDialog.run(parent, "error", text, title=title)


def show_success(
    parent: QWidget | None,
    text: str,
    *,
    title: str | None = None,
    path: Union[str, os.PathLike[str], None] = None,
) -> None:
    """绿色成功提示。若有产出路径，请改用或传入 path（等同 show_saved）。"""
    if path is not None:
        show_saved(parent, text, path, title=title)
        return
    title = title or message_title("success")
    logger.info("成功窗 [%s]: %s", title, text.replace("\n", " "))
    MessageDialog.run(parent, "success", text, title=title)


def ask_confirm(parent: QWidget | None, text: str, *, title: str | None = None) -> bool:
    title = title or message_title("confirm")
    logger.info("确认窗 [%s]: %s", title, text.replace("\n", " "))
    return MessageDialog.run(parent, "confirm", text, title=title)
