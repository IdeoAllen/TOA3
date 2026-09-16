# -*- coding: utf-8 -*-
"""对话框基类：统一窗口规格与异常边界。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog

from core.error_handler import run_safe
from core.ui_spec import apply_dialog_spec, finalize_dialog_geometry


class BaseDialog(QDialog):
    """所有业务弹窗基类（跟当前主题走，禁止自写样式表）。

    标题栏图标统一用「笔书写」矢量，不用应用品牌 logo / 系统 Python 图标。
    """

    dialog_kind: str = "medium"
    # 子类可覆盖为其它 icon_registry 名；空字符串表示不设图标
    dialog_icon_name: str = "dialog_edit"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setObjectName("ThemedDialog")
        # 禁止用户拖边改大小（配合 finalize 的 setFixedSize）
        self.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)
        apply_dialog_spec(self, self.dialog_kind)
        self._apply_dialog_window_icon()

    def _apply_dialog_window_icon(self) -> None:
        name = str(getattr(self, "dialog_icon_name", "") or "").strip()
        if not name:
            return
        try:
            from services.icon_registry import get_icon

            icon = get_icon(name, size=32, parent=self)
            if not icon.isNull():
                self.setWindowIcon(icon)
        except Exception:
            pass

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        try:
            from services.screenshot_overlay import cancel_active_screenshot

            cancel_active_screenshot(reason="modal_dialog")
        except Exception:
            pass
        super().showEvent(event)
        finalize_dialog_geometry(self, self.dialog_kind)
        # 业务弹窗不要套主窗任务栏身份（会把标题栏刷成品牌 logo）
        self._apply_dialog_window_icon()

    def run_safe(self, fn, *, title: str | None = None, success_status: str | None = None) -> bool:
        ctx = self.__class__.__name__
        result = run_safe(fn, self, title=title, context=ctx, success_status=success_status)
        return result is not None
