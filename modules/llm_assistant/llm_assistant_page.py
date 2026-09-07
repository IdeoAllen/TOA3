# -*- coding: utf-8 -*-
"""大模型助手：应用时选模型 + 简单配置持久化（极简范式）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.llm_assistant.llm_simple_setup_dialog import LlmSimpleSetupDialog
from services.compute_source import pick_effective_profile_id
from services.model_catalog import set_active_profile_id
from services.model_ready_registry import list_ready
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

_BIND_SENTINEL = "__bind__"


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
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

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
                cancel_check=lambda: self._cancelled,
            ):
                if self._cancelled:
                    self.failed.emit("已取消生成。")
                    return
                if delta:
                    parts.append(delta)
                    self.chunk.emit(delta)
            if self._cancelled:
                self.failed.emit("已取消生成。")
                return
            self.finished.emit("".join(parts))
        except Exception as exc:
            from core.exceptions import format_exception

            msg = getattr(exc, "user_message", None) or format_exception(exc)
            if self._cancelled or "已取消" in str(msg):
                self.failed.emit("已取消生成。")
            else:
                self.failed.emit(str(msg))


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
                "问一句、得一段 · 选模型即用 · 配置只做一次（两步）。"
                "写代码 / 多轮 Agent → 顶栏「引擎」→ 编码智能体。",
            )
        )

        # —— 应用时选模型 ——
        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self._profile_combo = ComboBox()
        self._profile_combo.setMinimumWidth(280)
        self._profile_combo.setToolTip("本次生成用此模型；切换后设为默认（持久）")
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        model_row.addWidget(self._profile_combo)
        self._model_hint = HintLabel("本次生成用此模型 · 切换即记为默认")
        model_row.addWidget(self._model_hint, 1)
        self._btn_simple_cfg = SecondaryButton("简单配置…")
        self._btn_simple_cfg.setToolTip("两步：① 选来源 ② Key/本机模型 → 保存记住")
        self._btn_simple_cfg.clicked.connect(self._open_simple_setup)
        model_row.addWidget(self._btn_simple_cfg)
        scroll.add_layout(model_row)
        self._profile_ids: list[str] = []

        # —— 首次空态（可跳过）——
        self._empty_panel = QWidget()
        empty_lay = QVBoxLayout(self._empty_panel)
        empty_lay.setContentsMargins(0, 4, 0, 8)
        empty_lay.setSpacing(8)
        empty_lay.addWidget(HintLabel("还没有可用模型。有条件时两步绑好；也可稍后再说，先浏览页面。"))
        empty_actions = QHBoxLayout()
        btn_start = PrimaryButton("开始两步配置")
        btn_start.clicked.connect(self._open_simple_setup)
        empty_actions.addWidget(btn_start)
        btn_later = SecondaryButton("稍后再说")
        btn_later.clicked.connect(lambda: self.report_status("可随时点「简单配置…」", StatusLevel.INFO))
        empty_actions.addWidget(btn_later)
        empty_actions.addStretch(1)
        empty_lay.addLayout(empty_actions)
        scroll.add_widget(self._empty_panel)

        prompt_box = FormSection("提示词")
        self._prompt = PlainTextEdit()
        self._prompt.setMinimumHeight(140)
        self._prompt.setPlaceholderText("输入问题或指令…")
        prompt_box.add_widget(self._prompt)
        scroll.add_widget(prompt_box)

        actions = QHBoxLayout()
        self._btn_gen = PrimaryButton("生成")
        self._btn_gen.clicked.connect(self._on_generate)
        actions.addWidget(self._btn_gen)
        self._btn_cancel = SecondaryButton("取消")
        self._btn_cancel.setVisible(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        actions.addWidget(self._btn_cancel)
        self._btn_polish = SecondaryButton("润色剪贴板")
        self._btn_polish.clicked.connect(self._on_polish_clipboard)
        actions.addWidget(self._btn_polish)
        btn_copy = SecondaryButton("复制结果")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)
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
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._prompt

    def _current_profile_id(self) -> str:
        idx = self._profile_combo.currentIndex()
        data = self._profile_combo.itemData(idx)
        if data == _BIND_SENTINEL:
            return ""
        if 0 <= idx < len(self._profile_ids):
            return self._profile_ids[idx]
        return str(data or "")

    def _reload_profiles(self, *, select_active: bool = False) -> None:
        profiles = list_ready("text_llm", ready_only=True)
        self._profile_ids = [
            str(p.get("id") or "") for p in profiles if p.get("source") == "catalog"
        ]
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
        self._profile_combo.addItem("＋ 绑定新模型…", _BIND_SENTINEL)
        self._profile_combo.blockSignals(False)

        has = bool(self._profile_ids)
        self._empty_panel.setVisible(not has)
        self._model_hint.setText(
            "本次生成用此模型 · 切换即记为默认"
            if has
            else "无可用模型时请两步配置，或稍后再说"
        )

        if select_active and self._profile_ids:
            effective = pick_effective_profile_id("text_llm", persist=True)
            if effective in self._profile_ids:
                self._profile_combo.setCurrentIndex(self._profile_ids.index(effective))
            else:
                self._profile_combo.setCurrentIndex(0)
        elif not self._profile_ids:
            self._profile_combo.setCurrentIndex(0)

    def _on_profile_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self._profile_combo.itemData(index)
        if data == _BIND_SENTINEL:
            self._profile_combo.blockSignals(True)
            if self._profile_ids:
                effective = pick_effective_profile_id("text_llm", persist=False)
                if effective in self._profile_ids:
                    self._profile_combo.setCurrentIndex(self._profile_ids.index(effective))
                else:
                    self._profile_combo.setCurrentIndex(0)
            self._profile_combo.blockSignals(False)
            self._open_simple_setup()
            return
        pid = str(data or "")
        if pid:
            set_active_profile_id("text_llm", pid)
            self.report_status("已设默认模型", StatusLevel.INFO)

    def _open_simple_setup(self) -> None:
        dlg = LlmSimpleSetupDialog(self)
        dlg.exec()
        self._reload_profiles(select_active=True)
        if dlg.saved and dlg.profile_id:
            self.report_status("简单配置已保存", StatusLevel.SUCCESS)

    def _generation_running(self) -> bool:
        return self._gen_thread is not None and self._gen_thread.isRunning()

    def _set_generating(self, busy: bool) -> None:
        self._btn_gen.setEnabled(not busy)
        self._btn_polish.setEnabled(not busy)
        self._btn_gen.setText("生成中…" if busy else "生成")
        self._btn_cancel.setVisible(busy)
        self._btn_cancel.setEnabled(busy)
        self._gen_progress.setVisible(busy)
        if busy:
            self._gen_progress.setRange(0, 0)
        else:
            self._gen_progress.setRange(0, 100)
            self._gen_progress.setValue(0)

    def _on_cancel(self) -> None:
        if self._gen_worker is not None:
            self._gen_worker.cancel()
        self.report_status("正在取消…", level=StatusLevel.INFO)
        self._btn_cancel.setEnabled(False)

    def _start_stream(
        self, prompt: str, *, system: str = "", status_connect: str = "正在连接模型…"
    ) -> None:
        if self._generation_running():
            show_warning(self, "正在生成，请稍候，勿连点。可点「取消」中止。")
            return
        pid = self._current_profile_id() or pick_effective_profile_id(
            "text_llm", persist=True
        )
        if not pid:
            show_warning(
                self,
                "暂无可用模型。点「开始两步配置」或「简单配置…」：① 选来源 ② 填 Key。",
            )
            self._open_simple_setup()
            return
        if pid in self._profile_ids:
            self._profile_combo.blockSignals(True)
            self._profile_combo.setCurrentIndex(self._profile_ids.index(pid))
            self._profile_combo.blockSignals(False)

        self._stream_acc = ""
        self._result.setPlainText("")
        self._set_generating(True)
        self.report_status(status_connect, level=StatusLevel.INFO)

        self._gen_thread = QThread(self)
        self._gen_worker = _LlmStreamWorker(prompt, system=system, profile_id=pid)
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
        n = len(self._stream_acc)
        if n < 8 or n % 80 < len(delta):
            self.report_status(f"正在生成…已输出 {n} 字", level=StatusLevel.INFO)

    def _on_stream_finished(self, full: str) -> None:
        if full and not self._stream_acc:
            self._result.setPlainText(full)
        self._set_generating(False)
        self.report_status("生成完成", level=StatusLevel.SUCCESS)

    def _on_stream_failed(self, message: str) -> None:
        self._set_generating(False)
        msg = (message or "").strip()
        if "已取消" in msg:
            self.report_status("已取消生成", level=StatusLevel.INFO)
            return
        from core.error_handler import report_error

        report_error(
            self, Exception(msg or "大模型调用失败"), title="大模型调用失败", context=self.page_id
        )

    def _cleanup_stream_worker(self) -> None:
        self._set_generating(False)
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

    def on_enter(self) -> None:
        self._reload_profiles(select_active=True)
        if not self._generation_running():
            self._set_generating(False)
            self.report_status("大模型助手")

    def on_leave(self) -> None:
        if self._generation_running() and self._gen_worker is not None:
            self._gen_worker.cancel()
            self.report_status("离开页面，已取消生成", level=StatusLevel.INFO)
