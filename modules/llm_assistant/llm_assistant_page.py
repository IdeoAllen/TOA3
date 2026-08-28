# -*- coding: utf-8 -*-
"""大模型助手：提示词生成 / 剪贴板润色。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_warning
from services.model_ready_registry import list_ready
from services.model_catalog import (
    get_active_profile_id,
    set_active_profile_id,
)
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ProgressBar,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)

_POLISH_SYSTEM = (
    "你是中文办公文案助手。请润色用户给出的文本，保持原意，"
    "使表达更清晰、简洁、专业。只输出润色后的正文，不要解释。"
)


class _LlmStreamWorker(QObject):
    connecting = Signal()
    chunk = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        prompt: str,
        *,
        system: str = "",
        profile_id: str = "",
    ) -> None:
        super().__init__()
        self._prompt = prompt
        self._system = system
        self._profile_id = profile_id

    def run(self) -> None:
        self.connecting.emit()
        try:
            from services.integrations import get_client

            client = get_client("llm")
            parts: list[str] = []
            for delta in client.complete_stream(
                self._prompt,
                system=self._system,
                profile_id=self._profile_id or None,
            ):
                if delta:
                    parts.append(delta)
                    self.chunk.emit(delta)
            self.finished.emit("".join(parts))
        except Exception as exc:
            from core.exceptions import format_exception

            self.failed.emit(format_exception(exc))


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
                "轻量「问一句、得一段文字」：润色邮件/通知、写提纲、试提示词。"
                "写代码、改项目、多轮 Agent → 请用「编码智能体」。",
            )
        )

        model_box = FormSection("模型配置")
        self._profile_combo = ComboBox()
        self._profile_combo.setMinimumWidth(280)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        model_box.add_widget(HintLabel("仅显示「可用」模型；其余在 系统设置 → 能力接入 → 模型管理"))
        self._empty_hint = HintLabel("")
        model_box.add_widget(self._empty_hint)
        model_box.add_widget(self._profile_combo)
        scroll.add_widget(model_box)
        self._profile_ids: list[str] = []

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
        self._btn_gen = PrimaryButton("生成")
        self._btn_gen.clicked.connect(self._on_generate)
        actions.addWidget(self._btn_gen)
        self._btn_polish = SecondaryButton("润色剪贴板")
        self._btn_polish.clicked.connect(self._on_polish_clipboard)
        actions.addWidget(self._btn_polish)
        btn_copy = SecondaryButton("复制结果")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)
        btn_cfg = SecondaryButton("打开能力接入")
        btn_cfg.clicked.connect(self._open_settings)
        actions.addWidget(btn_cfg)
        actions.addStretch(1)
        scroll.add_layout(actions)

        self._gen_progress = ProgressBar()
        self._gen_progress.setVisible(False)
        self._gen_progress.setTextVisible(False)
        self._gen_progress.setMaximumHeight(10)
        scroll.add_widget(self._gen_progress)

        out = FormSection("结果")
        self._result = ReadOnlyPlainTextEdit()
        self._result.setMinimumHeight(220)
        self._result.setPlaceholderText("生成结果…")
        out.add_widget(self._result)
        scroll.add_widget(out)
        scroll.add_stretch(1)

        self._gen_thread: QThread | None = None
        self._gen_worker: _LlmStreamWorker | None = None
        self._stream_acc = ""

    def _current_profile_id(self) -> str:
        idx = self._profile_combo.currentIndex()
        if 0 <= idx < len(self._profile_ids):
            return self._profile_ids[idx]
        return ""

    def _reload_profiles(self, *, select_active: bool = False) -> None:
        profiles = list_ready("text_llm", ready_only=True)
        self._profile_ids = [str(p.get("id") or "") for p in profiles if p.get("source") == "catalog"]
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for p in profiles:
            if p.get("source") != "catalog":
                continue
            label = str(p.get("label") or p.get("id") or "未命名")
            model = str(p.get("model") or "")
            if model:
                label = f"{label}（{model}）"
            self._profile_combo.addItem(label, str(p.get("id") or ""))
        self._profile_combo.blockSignals(False)
        if not self._profile_ids:
            self._empty_hint.setText(
                "暂无可用模型 → 系统设置 → 能力接入 → 模型管理，配置网络 Key 或本地 Ollama 端点。"
            )
            self._profile_combo.addItem("（无可用模型）", "")
        else:
            self._empty_hint.setText("")
        if select_active and self._profile_ids:
            active = get_active_profile_id("text_llm")
            idx = self._profile_ids.index(active) if active in self._profile_ids else 0
            self._profile_combo.setCurrentIndex(idx)

    def _on_profile_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._profile_ids):
            return
        pid = self._profile_ids[index]
        if pid:
            set_active_profile_id("text_llm", pid)

    def _generation_running(self) -> bool:
        return self._gen_thread is not None and self._gen_thread.isRunning()

    def _set_generating(self, busy: bool) -> None:
        self._btn_gen.setEnabled(not busy)
        self._btn_polish.setEnabled(not busy)
        self._btn_gen.setText("生成中…" if busy else "生成")
        self._gen_progress.setVisible(busy)
        if busy:
            self._gen_progress.setRange(0, 0)
        else:
            self._gen_progress.setRange(0, 100)
            self._gen_progress.setValue(0)

    def _start_stream(self, prompt: str, *, system: str = "", status_connect: str = "正在连接模型…") -> None:
        if self._generation_running():
            show_warning(self, "正在生成，请稍候，勿连点。")
            return
        if not self._current_profile_id():
            show_warning(self, "暂无可用模型，请先到「系统设置 → 能力接入 → 模型管理」配置。")
            return

        self._stream_acc = ""
        self._result.setPlainText("")
        self._set_generating(True)
        self.report_status(status_connect, level=StatusLevel.INFO)

        self._gen_thread = QThread(self)
        self._gen_worker = _LlmStreamWorker(
            prompt,
            system=system,
            profile_id=self._current_profile_id(),
        )
        self._gen_worker.moveToThread(self._gen_thread)
        self._gen_thread.started.connect(self._gen_worker.run)
        self._gen_worker.connecting.connect(self._on_stream_connecting)
        self._gen_worker.chunk.connect(self._on_stream_chunk)
        self._gen_worker.finished.connect(self._on_stream_finished)
        self._gen_worker.failed.connect(self._on_stream_failed)
        self._gen_worker.finished.connect(self._gen_thread.quit)
        self._gen_worker.failed.connect(self._gen_thread.quit)
        self._gen_thread.finished.connect(self._cleanup_stream_worker)
        self._gen_thread.start()

    def _on_stream_connecting(self) -> None:
        self.report_status("正在连接模型…", level=StatusLevel.INFO)

    def _on_stream_chunk(self, delta: str) -> None:
        if not delta:
            return
        self._stream_acc += delta
        cursor = self._result.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(delta)
        self._result.setTextCursor(cursor)
        self._result.ensureCursorVisible()
        if len(self._stream_acc) < 8:
            self.report_status("正在生成…", level=StatusLevel.INFO)

    def _on_stream_finished(self, full: str) -> None:
        if full and not self._stream_acc:
            self._result.setPlainText(full)
        self._set_generating(False)
        self.report_status("生成完成", level=StatusLevel.SUCCESS)

    def _on_stream_failed(self, message: str) -> None:
        self._set_generating(False)
        from core.error_handler import report_error

        report_error(self, Exception(message), title="大模型调用失败", context=self.page_id)

    def _cleanup_stream_worker(self) -> None:
        if self._gen_worker is not None:
            self._gen_worker.deleteLater()
            self._gen_worker = None
        if self._gen_thread is not None:
            self._gen_thread.deleteLater()
            self._gen_thread = None

    def _on_generate(self) -> None:
        prompt = self._prompt.toPlainText().strip()
        if not prompt:
            show_warning(self, "请先输入提示词。")
            return
        self._start_stream(prompt)

    def _on_polish_clipboard(self) -> None:
        clip = QGuiApplication.clipboard()
        raw = (clip.text() if clip is not None else "") or ""
        if not raw.strip():
            show_warning(self, "剪贴板没有文本。")
            return
        self._prompt.setPlainText(raw)
        self._start_stream(raw, system=_POLISH_SYSTEM, status_connect="正在润色…")

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
            if page is not None and hasattr(page, "open_model_hub_tab"):
                page.open_model_hub_tab()
            elif page is not None and hasattr(page, "open_capability_tab"):
                page.open_capability_tab()

    def on_enter(self) -> None:
        self._reload_profiles(select_active=True)
        self.report_status("大模型助手")

    def on_leave(self) -> None:
        if self._generation_running():
            self._gen_thread.requestInterruption()
            self._gen_thread.quit()
