# -*- coding: utf-8 -*-
"""大模型助手：提示词生成 / 剪贴板润色。"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from widgets import (
    FormSection,
    HintLabel,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)

_POLISH_SYSTEM = (
    "你是中文办公文案助手。请润色用户给出的文本，保持原意，"
    "使表达更清晰、简洁、专业。只输出润色后的正文，不要解释。"
)


class LlmAssistantPage(BasePage):
    page_id = "llm_assistant"
    page_title = "大模型助手"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "大模型助手",
                "提示词生成 / 剪贴板润色。先在「系统设置 → 能力接入 → 大模型」配置。",
            )
        )

        prompt_box = FormSection("提示词")
        self._prompt = PlainTextEdit()
        self._prompt.setMinimumHeight(140)
        self._prompt.setPlaceholderText("输入问题或指令…")
        prompt_box.add_widget(self._prompt)
        prompt_box.add_widget(
            HintLabel("未配置时可点下方「打开能力接入」填写 API 地址、模型与 Key。")
        )
        scroll.add_widget(prompt_box)

        actions = QHBoxLayout()
        btn_gen = PrimaryButton("生成")
        btn_gen.clicked.connect(self._on_generate)
        actions.addWidget(btn_gen)
        btn_polish = SecondaryButton("润色剪贴板")
        btn_polish.clicked.connect(self._on_polish_clipboard)
        actions.addWidget(btn_polish)
        btn_copy = SecondaryButton("复制结果")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)
        btn_cfg = SecondaryButton("打开能力接入")
        btn_cfg.clicked.connect(self._open_settings)
        actions.addWidget(btn_cfg)
        actions.addStretch(1)
        scroll.add_layout(actions)

        out = FormSection("结果")
        self._result = ReadOnlyPlainTextEdit()
        self._result.setMinimumHeight(220)
        self._result.setPlaceholderText("生成结果…")
        out.add_widget(self._result)
        scroll.add_widget(out)
        scroll.add_stretch(1)

    def _client_complete(self, prompt: str, *, system: str = "") -> str:
        from services.integrations import get_client

        client = get_client("llm")
        return client.complete(prompt, system=system)

    def _on_generate(self) -> None:
        prompt = self._prompt.toPlainText().strip()
        if not prompt:
            show_warning(self, "请先输入提示词。")
            return

        def _run() -> None:
            text = self._client_complete(prompt)
            self._result.setPlainText(text)
            self.report_status("生成完成", level=StatusLevel.SUCCESS)

        self.run_safe(_run, title="大模型调用失败")

    def _on_polish_clipboard(self) -> None:
        clip = QGuiApplication.clipboard()
        raw = (clip.text() if clip is not None else "") or ""
        if not raw.strip():
            show_warning(self, "剪贴板没有文本。")
            return
        self._prompt.setPlainText(raw)

        def _run() -> None:
            text = self._client_complete(raw, system=_POLISH_SYSTEM)
            self._result.setPlainText(text)
            self.report_status("润色完成", level=StatusLevel.SUCCESS)
            show_info(self, "剪贴板文本已润色。")

        self.run_safe(_run, title="润色失败")

    def _on_copy(self) -> None:
        text = self._result.toPlainText()
        if not text.strip():
            show_warning(self, "没有可复制的内容。")
            return
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(text)
            self.report_status("已复制到剪贴板", level=StatusLevel.SUCCESS)

    def _open_settings(self) -> None:
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            shell.navigate("system_settings")
            page = getattr(shell, "_pages", {}).get("system_settings")
            if page is not None and hasattr(page, "open_capability_tab"):
                page.open_capability_tab()

    def on_enter(self) -> None:
        self.report_status("大模型助手")
