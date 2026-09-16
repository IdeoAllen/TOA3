# -*- coding: utf-8 -*-
"""运行环境：有新版本 / 升级完成待启动。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton, SemanticLabel


class UpgradeStrip(QWidget):
    """进页弱提示：更新 / 不更新 / 今日不提醒；升级完成后提示启动服务。"""

    upgrade_requested = Signal()
    dismissed = Signal()  # 不更新（本会话）
    snooze_today_requested = Signal()
    start_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._box = FormSection("运行环境更新")
        self._banner = SemanticLabel("", kind="info")
        self._banner.setWordWrap(True)
        self._box.add_widget(self._banner)

        self._detail = HintLabel("")
        self._detail.setWordWrap(True)
        self._box.add_widget(self._detail)

        ops = QHBoxLayout()
        self._btn_upgrade = PrimaryButton("更新")
        self._btn_upgrade.setToolTip("下载覆盖程序树；会话与密钥默认保留")
        self._btn_upgrade.clicked.connect(self.upgrade_requested.emit)
        ops.addWidget(self._btn_upgrade)

        self._btn_start = PrimaryButton("启动服务")
        self._btn_start.setToolTip("升级已完成，启动后即可使用")
        self._btn_start.clicked.connect(self.start_requested.emit)
        self._btn_start.hide()
        ops.addWidget(self._btn_start)

        self._btn_skip = SecondaryButton("不更新")
        self._btn_skip.setToolTip("继续用现有环境；本会话不再提醒。可随时在「更多 → 环境维护」更新")
        self._btn_skip.clicked.connect(self.dismissed.emit)
        ops.addWidget(self._btn_skip)

        self._btn_snooze = SecondaryButton("今日不提醒")
        self._btn_snooze.setToolTip("今天内不打扰；明天仍可再提示。推荐网络空闲时再更新")
        self._btn_snooze.clicked.connect(self.snooze_today_requested.emit)
        ops.addWidget(self._btn_snooze)

        ops.addStretch(1)
        self._box.add_layout(ops)

        root.addWidget(self._box)
        self.hide()
        self._mode = "idle"

    def show_update(
        self,
        *,
        label: str,
        installed: str,
        available: str,
        size_hint_mb: int = 0,
    ) -> None:
        self._mode = "prompt"
        self._box.setTitle("运行环境程序包可更新（可选）")
        size_s = f"约 {size_hint_mb} MB，" if size_hint_mb > 0 else ""
        self._banner.setText(f"{label}：本机 {installed} → 配置 {available}")
        self._detail.setText(
            f"这是程序包编号更新，不是 TOA 坏了。可先「今日不提醒」继续用现有环境；"
            f"若点「更新」则{size_s}整包下载并覆盖程序文件（会话与 API Key 默认保留）。"
            "不会自动开始下载。"
        )
        self._btn_upgrade.show()
        self._btn_start.hide()
        self._btn_skip.show()
        self._btn_snooze.show()
        self.show()

    def show_upgraded_done(self, *, version: str = "") -> None:
        """升级成功：提示用户手动启动服务。"""
        self._mode = "done"
        self._box.setTitle("运行环境已升级完成")
        ver = (version or "").strip()
        self._banner.setText(
            f"已升级到 {ver}。" if ver else "程序文件已更新完成。"
        )
        self._detail.setText("请点「启动服务」开始使用；不会自动启动。")
        self._btn_upgrade.hide()
        self._btn_skip.hide()
        self._btn_snooze.hide()
        self._btn_start.show()
        self.show()

    def clear(self) -> None:
        self._mode = "idle"
        self.hide()
        self._banner.setText("")
        self._detail.setText("")
        self._btn_upgrade.show()
        self._btn_start.hide()
        self._btn_skip.show()
        self._btn_snooze.show()
