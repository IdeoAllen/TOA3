# -*- coding: utf-8 -*-
"""未安装 / 待配置时的主区引导（小白 ≤3 步）。

① 一键安装运行环境（独立目录，不绑其它软件）
② 粘贴 DeepSeek API Key
③ 自动启动并进入内嵌界面
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.user_messages import show_info, show_warning
from services.harness_credentials import save_api_key
from services.harness_guide import GUIDE_INTRO, NODE_DOWNLOAD_URL, STEP_HINTS
from services.harness_probe import HarnessPageState
from services.harness_setup import NEED_NODE_PREFIX
from widgets import FormSection, HintLabel, PasswordLineEdit, PrimaryButton, SecondaryButton, SemanticLabel


class SetupGate(QWidget):
    """覆盖主内容区：未就绪时显示三步进度，就绪后隐藏。"""

    install_requested = Signal()
    key_saved = Signal()
    open_settings_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        card = FormSection("编码智能体 · 三步开用")
        card_inner = QVBoxLayout()
        card_inner.setSpacing(10)

        self._intro = HintLabel(GUIDE_INTRO)
        self._intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._intro.setWordWrap(True)
        card_inner.addWidget(self._intro)

        steps = QHBoxLayout()
        steps.setSpacing(8)
        self._step_labels: list[SemanticLabel] = []
        for text in ("① 安装环境", "② 填写密钥", "③ 启动使用"):
            lab = SemanticLabel(text, "info")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lab)
            steps.addWidget(lab, 1)
        card_inner.addLayout(steps)

        self._body = HintLabel("")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        card_inner.addWidget(self._body)

        self._key_row = QWidget()
        key_lay = QHBoxLayout(self._key_row)
        key_lay.setContentsMargins(0, 0, 0, 0)
        self._key_edit = PasswordLineEdit()
        self._key_edit.setPlaceholderText("粘贴 DeepSeek API Key（仅存本机）")
        key_lay.addWidget(self._key_edit, 1)
        self._btn_key = PrimaryButton("保存并启动")
        self._btn_key.clicked.connect(self._save_key)
        key_lay.addWidget(self._btn_key)
        self._key_row.hide()
        card_inner.addWidget(self._key_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_primary = PrimaryButton("① 一键安装")
        self._btn_primary.clicked.connect(self.install_requested.emit)
        btn_row.addWidget(self._btn_primary)
        self._btn_node = SecondaryButton("去安装 Node.js")
        self._btn_node.clicked.connect(self._open_node_download)
        self._btn_node.hide()
        btn_row.addWidget(self._btn_node)
        self._btn_secondary = SecondaryButton("高级路径…")
        self._btn_secondary.clicked.connect(self.open_settings_requested.emit)
        btn_row.addWidget(self._btn_secondary)
        btn_row.addStretch(1)
        card_inner.addLayout(btn_row)

        self._footer = HintLabel("高级路径仅供改 Node/端口；日常请走上面三步。")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer.setWordWrap(True)
        card_inner.addWidget(self._footer)

        card.add_layout(card_inner)
        outer.addWidget(card)
        outer.addStretch(2)

        self._state = HarnessPageState.CHECKING
        self._need_node = False

    def show_state(self, state: HarnessPageState, message: str = "") -> None:
        self._state = state
        self._need_node = False
        if state == HarnessPageState.CHECKING:
            self.show()
            self._set_active_step(0)
            self._body.setText(message or "正在确认本机环境…")
            self._btn_primary.hide()
            self._btn_node.hide()
            self._btn_secondary.hide()
            self._key_row.hide()
            return

        if state == HarnessPageState.NOT_INSTALLED:
            self.show()
            self._set_active_step(1)
            msg = (message or "").strip()
            if msg.startswith(NEED_NODE_PREFIX):
                self._need_node = True
                self._body.setText(
                    msg[len(NEED_NODE_PREFIX) :].strip()
                    or STEP_HINTS["runtime_need_node"]
                )
                self._btn_primary.setText("装好后点这里重试")
                self._btn_node.show()
            else:
                self._body.setText(msg or STEP_HINTS["runtime"])
                self._btn_primary.setText("① 一键安装")
                self._btn_node.hide()
            self._btn_primary.show()
            self._btn_primary.setEnabled(True)
            self._btn_secondary.show()
            self._key_row.hide()
            return

        if state == HarnessPageState.NEEDS_KEY:
            self.show()
            self._set_active_step(2)
            self._body.setText(message or STEP_HINTS["credentials"])
            self._btn_primary.hide()
            self._btn_node.hide()
            self._btn_secondary.show()
            self._key_row.show()
            self._key_edit.setFocus()
            return

        self.hide()

    def set_installing(self, active: bool) -> None:
        if active:
            self._set_active_step(1)
            self._body.setText("正在安装运行环境（首次可能需要几分钟，请保持网络畅通）…")
            self._btn_primary.setEnabled(False)
            self._btn_node.hide()
        else:
            self._btn_primary.setEnabled(True)

    def mark_need_node(self, detail: str = "") -> None:
        """安装失败且缺 Node 时，切到可点「去安装 Node.js」的状态。"""
        self._need_node = True
        self._set_active_step(1)
        self._body.setText(detail or STEP_HINTS["runtime_need_node"])
        self._btn_primary.setText("装好后点这里重试")
        self._btn_primary.show()
        self._btn_primary.setEnabled(True)
        self._btn_node.show()
        self._btn_secondary.show()
        self._key_row.hide()

    def _set_active_step(self, step: int) -> None:
        """step: 0=检测, 1/2/3=三步高亮。"""
        for i, lab in enumerate(self._step_labels, start=1):
            if step <= 0:
                kind = "info"
            elif i < step:
                kind = "success"
            elif i == step:
                kind = "info"
            else:
                kind = "info"
            lab.setProperty("class", f"semantic-{kind}")
            st = lab.style()
            if st is not None:
                st.unpolish(lab)
                st.polish(lab)
            lab.update()

    def _open_node_download(self) -> None:
        QDesktopServices.openUrl(QUrl(NODE_DOWNLOAD_URL))
        self._body.setText(
            "已打开 Node.js 下载页。请安装 LTS（18+），装完后回到本页点「装好后点这里重试」。"
        )

    def _save_key(self) -> None:
        ok, msg = save_api_key(self._key_edit.text())
        if ok:
            self._key_edit.clear()
            self._set_active_step(3)
            self._body.setText(STEP_HINTS["start"])
            show_info(self, "密钥已保存，正在启动…")
            self.key_saved.emit()
        else:
            show_warning(self, msg)
