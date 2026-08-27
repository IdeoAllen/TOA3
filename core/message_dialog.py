# -*- coding: utf-8 -*-
"""统一主题化提示窗（业务唯一弹窗入口，禁止裸 QMessageBox）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from core.message_icons import message_status_icon, message_status_pixmap
from core.ui_spec import apply_dialog_spec, finalize_dialog_geometry, message_title
from services.icon_registry import device_pixel_ratio
from widgets.dialog_actions import DialogButtonRow
from widgets.themed_labels import SemanticLabel

_KIND_SEMANTIC = {
    "info": "info",
    "warning": "warning",
    "error": "danger",
    "confirm": "warning",
    "success": "success",
}


class MessageDialog(QDialog):
    """全局 QSS 主题化的信息 / 警告 / 错误 / 确认 / 成功对话框。"""

    def __init__(
        self,
        parent=None,
        *,
        kind: str = "info",
        title: str = "",
        text: str = "",
        open_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MessageDialog")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)
        apply_dialog_spec(self, "small")
        self._kind = kind if kind in _KIND_SEMANTIC else "info"
        self._open_path = open_path
        self.setWindowTitle(title)

        dpr = device_pixel_ratio(parent or self)
        # 标题栏 / 任务栏：状态图标，不用品牌 TOA logo
        self.setWindowIcon(message_status_icon(self._kind, logical=32, dpr=dpr))

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        semantic = _KIND_SEMANTIC.get(self._kind, "info")
        banner = SemanticLabel(title, kind=semantic)
        lay.addWidget(banner)

        row = QHBoxLayout()
        row.setSpacing(14)
        icon_lbl = QLabel()
        icon_lbl.setObjectName("MessageStatusIcon")
        icon_lbl.setFixedSize(44, 44)
        icon_lbl.setPixmap(message_status_pixmap(self._kind, logical=40, dpr=dpr))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        row.addWidget(icon_lbl)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        body.setMinimumWidth(260)
        row.addWidget(body, 1)
        lay.addLayout(row)

        self._buttons = DialogButtonRow()
        lay.addWidget(self._buttons)

        if self._kind == "confirm":
            self._buttons.add_secondary("取消", self.reject)
            self._buttons.add_primary("确定", self.accept)
        else:
            if open_path:
                self._buttons.add_secondary("打开所在目录", self._open_containing)
            self._buttons.add_primary("确定", self.accept)

    def _open_containing(self) -> None:
        from pathlib import Path

        from services.os_open import open_in_file_manager

        if self._open_path:
            p = Path(self._open_path)
            open_in_file_manager(self._open_path, select=p.is_file())
        self.accept()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        finalize_dialog_geometry(self, "small")

    @staticmethod
    def run(
        parent,
        kind: str,
        text: str,
        *,
        title: str | None = None,
        open_path: str | None = None,
    ) -> bool:
        if kind == "confirm":
            title_key = "confirm"
        elif kind == "warning":
            title_key = "warning"
        elif kind == "error":
            title_key = "error"
        elif kind == "success":
            title_key = "success"
        else:
            title_key = "info"
        resolved_title = title or message_title(title_key)
        dlg = MessageDialog(
            parent,
            kind=kind,
            title=resolved_title,
            text=text,
            open_path=open_path,
        )
        result = dlg.exec() == QDialog.DialogCode.Accepted
        return result if kind == "confirm" else True
