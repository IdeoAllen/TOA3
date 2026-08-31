# -*- coding: utf-8 -*-
"""办公链 / 扩展开发 · 待投喂条（控件库）。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton, SemanticLabel


class FeedStrip(QWidget):
    apply_requested = Signal()
    dismissed = Signal()
    open_folder_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._box = FormSection("扩展开发任务")
        self._banner = SemanticLabel("", kind="info")
        self._banner.setWordWrap(True)
        self._box.add_widget(self._banner)

        self._path_hint = HintLabel("")
        self._path_hint.setWordWrap(True)
        self._box.add_widget(self._path_hint)

        self._preview = HintLabel("")
        self._preview.setWordWrap(True)
        self._box.add_widget(self._preview)

        ops = QHBoxLayout()
        self._btn_apply = PrimaryButton("准备会话并填入")
        self._btn_apply.setToolTip("刷新页面 → 切换扩展工作区 → 新会话 → 填入开发任务")
        self._btn_apply.clicked.connect(self.apply_requested.emit)
        ops.addWidget(self._btn_apply)

        self._btn_folder = SecondaryButton("打开扩展目录")
        self._btn_folder.setToolTip("若侧栏没有本工作区：点 Harness「+」添加此目录")
        self._btn_folder.clicked.connect(self.open_folder_requested.emit)
        ops.addWidget(self._btn_folder)

        btn_skip = SecondaryButton("忽略")
        btn_skip.clicked.connect(self.dismissed.emit)
        ops.addWidget(btn_skip)
        ops.addStretch(1)
        self._box.add_layout(ops)

        root.addWidget(self._box)

    def set_preview(
        self,
        title: str,
        preview: str,
        *,
        auto_prepare: bool = False,
        workspace_path: str = "",
        workspace_title: str = "",
    ) -> None:
        title = (title or "开发引导").strip()
        text = (preview or "").strip()
        if len(text) > 160:
            text = text[:160] + "…"
        wt = (workspace_title or "").strip()
        wp = (workspace_path or "").strip()
        self._box.setTitle(f"扩展开发任务 · {title}")
        if auto_prepare:
            self._banner.setText(
                "任务已创建并开始执行。正在自动展开工作区并切入会话；"
                "若未跳转，请按下方路径在左侧点开。"
            )
            self._btn_apply.setText("再次定位到该会话")
        else:
            self._banner.setText(
                "点「准备会话并填入」将创建/打开工作区并投喂。"
                "侧栏没有时可用「打开扩展目录」核对路径。"
            )
            self._btn_apply.setText("准备会话并填入")
        if wp:
            label = f"工作区「{wt}」" if wt else "工作区"
            self._path_hint.setText(f"{label}路径：{wp}")
            self._path_hint.show()
            self._btn_folder.show()
        else:
            self._path_hint.hide()
            self._btn_folder.hide()
        if preview and "请点左侧" in preview:
            self._preview.setText(preview.strip())
        else:
            self._preview.setText(text or "（无预览）")
