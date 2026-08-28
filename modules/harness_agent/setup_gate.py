# -*- coding: utf-8 -*-
"""未安装 / 待配置时的主区引导（小白一键路径）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.user_messages import show_info, show_warning
from services.harness_credentials import save_api_key
from services.harness_probe import HarnessPageState
from widgets import FormSection, HintLabel, PasswordLineEdit, PrimaryButton, SecondaryButton


class SetupGate(QWidget):
    """覆盖主内容区：未就绪时显示，就绪后隐藏。"""

    install_requested = Signal()
    key_saved = Signal()
    open_settings_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        card = FormSection("DeepSeek Harness")
        card_inner = QVBoxLayout()
        card_inner.setSpacing(10)

        self._title = HintLabel("AI 编码助手")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_inner.addWidget(self._title)

        self._body = HintLabel("")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_inner.addWidget(self._body)

        self._key_row = QWidget()
        key_lay = QHBoxLayout(self._key_row)
        key_lay.setContentsMargins(0, 0, 0, 0)
        self._key_edit = PasswordLineEdit()
        self._key_edit.setPlaceholderText("粘贴 DeepSeek API Key")
        key_lay.addWidget(self._key_edit, 1)
        btn_key = PrimaryButton("保存并继续")
        btn_key.clicked.connect(self._save_key)
        key_lay.addWidget(btn_key)
        self._key_row.hide()
        card_inner.addWidget(self._key_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_primary = PrimaryButton("一键安装 DeepSeek Harness")
        self._btn_primary.clicked.connect(self.install_requested.emit)
        btn_row.addWidget(self._btn_primary)
        self._btn_secondary = SecondaryButton("高级设置")
        self._btn_secondary.clicked.connect(self.open_settings_requested.emit)
        btn_row.addWidget(self._btn_secondary)
        btn_row.addStretch(1)
        card_inner.addLayout(btn_row)

        card.add_layout(card_inner)
        outer.addWidget(card)
        outer.addStretch(2)

        self._state = HarnessPageState.CHECKING

    def show_state(self, state: HarnessPageState, message: str = "") -> None:
        self._state = state
        if state == HarnessPageState.CHECKING:
            self.show()
            self._body.setText(message or "正在确认服务状态…")
            self._btn_primary.hide()
            self._btn_secondary.hide()
            self._key_row.hide()
            return

        if state == HarnessPageState.NOT_INSTALLED:
            self.show()
            self._body.setText(
                message or "安装后即可在下方使用 Harness 原版界面，无需单独打开浏览器。"
            )
            self._btn_primary.setText("一键安装 DeepSeek Harness")
            self._btn_primary.show()
            self._btn_primary.setEnabled(True)
            self._btn_secondary.show()
            self._key_row.hide()
            return

        if state == HarnessPageState.NEEDS_KEY:
            self.show()
            self._body.setText("Harness 已安装。填写 API Key 后即可启动服务。")
            self._btn_primary.hide()
            self._btn_secondary.show()
            self._key_row.show()
            return

        self.hide()

    def set_installing(self, active: bool) -> None:
        if active:
            self._body.setText("正在安装，首次可能需要几分钟，请稍候…")
            self._btn_primary.setEnabled(False)
        else:
            self._btn_primary.setEnabled(True)

    def _save_key(self) -> None:
        ok, msg = save_api_key(self._key_edit.text())
        if ok:
            self._key_edit.clear()
            show_info(self, msg)
            self.key_saved.emit()
        else:
            show_warning(self, msg)
