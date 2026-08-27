# -*- coding: utf-8 -*-
"""对话框基类：统一窗口规格与异常边界。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog

from core.error_handler import run_safe
from core.ui_spec import apply_dialog_spec, finalize_dialog_geometry


class BaseDialog(QDialog):
    """所有业务弹窗基类（跟当前主题走，禁止自写样式表）。"""

    dialog_kind: str = "medium"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setObjectName("ThemedDialog")
        # 禁止用户拖边改大小（配合 finalize 的 setFixedSize）
        self.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)
        apply_dialog_spec(self, self.dialog_kind)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        finalize_dialog_geometry(self, self.dialog_kind)

    def run_safe(self, fn, *, title: str | None = None, success_status: str | None = None) -> bool:
        ctx = self.__class__.__name__
        result = run_safe(fn, self, title=title, context=ctx, success_status=success_status)
        return result is not None
