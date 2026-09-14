# -*- coding: utf-8 -*-
"""本机已有 Harness 实例：直接加载 / 刷新加载 / 更新环境。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton, SemanticLabel


class InstanceStrip(QWidget):
    """识别到本机实例时的引导条（不一定由运营宝启动）。"""

    refresh_requested = Signal()
    update_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._box = FormSection("本机已有 Harness")
        self._banner = SemanticLabel("", kind="info")
        self._banner.setWordWrap(True)
        self._box.add_widget(self._banner)

        self._detail = HintLabel("")
        self._detail.setWordWrap(True)
        self._box.add_widget(self._detail)

        ops = QHBoxLayout()
        self._btn_refresh = PrimaryButton("刷新加载")
        self._btn_refresh.setToolTip("接上本机正在运行的服务并装入界面")
        self._btn_refresh.clicked.connect(self.refresh_requested.emit)
        ops.addWidget(self._btn_refresh)

        self._btn_update = SecondaryButton("更新环境")
        self._btn_update.setToolTip("下载新版运行环境（覆盖程序树，会话与密钥默认保留）")
        self._btn_update.clicked.connect(self.update_requested.emit)
        ops.addWidget(self._btn_update)

        btn_hide = SecondaryButton("知道了")
        btn_hide.clicked.connect(self.dismissed.emit)
        ops.addWidget(btn_hide)
        ops.addStretch(1)
        self._box.add_layout(ops)

        root.addWidget(self._box)
        self.hide()
        self._mode = "idle"

    def show_detected(
        self,
        *,
        port: int = 3082,
        owned: bool = False,
        http_ok: bool = True,
        offer_update: bool = False,
    ) -> None:
        self._mode = "detected"
        self._box.setTitle("识别到本机有 Harness 在运行")
        who = "由运营宝托管" if owned else "不一定由运营宝启动"
        if http_ok:
            self._banner.setText(f"端口 {port} 上的服务可用（{who}）。")
            self._detail.setText(
                "可点「刷新加载」直接装入界面。"
                + (" 若要换成新版程序包，再点「更新环境」。" if offer_update else "")
            )
        else:
            self._banner.setText(f"端口 {port} 已被占用，但暂未确认服务响应（{who}）。")
            self._detail.setText(
                "请点「刷新加载」再试一次。"
                + (" 也可「更新环境」安装新版。" if offer_update else "")
            )
        self._btn_update.setVisible(bool(offer_update))
        self.show()

    def clear(self) -> None:
        self._mode = "idle"
        self.hide()
        self._banner.setText("")
        self._detail.setText("")
