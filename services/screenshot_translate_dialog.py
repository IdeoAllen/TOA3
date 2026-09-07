# -*- coding: utf-8 -*-
"""截图翻译对照弹窗：应用时选模型 + 简单配置（大模型范式）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from core.status_service import StatusLevel, report_status
from core.user_messages import ask_confirm, show_warning
from services.compute_source import pick_effective_profile_id
from services.model_catalog import set_active_profile_id
from services.model_ready_registry import list_ready
from widgets import (
    ComboBox,
    HintLabel,
    PageTitle,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
)

_BIND = "__bind__"


class _TranslateWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, source: str, *, profile_id: str = "") -> None:
        super().__init__()
        self._source = source
        self._profile_id = profile_id

    def run(self) -> None:
        try:
            from services.integrations import get_client

            llm = get_client("llm")
            translated = llm.complete(
                self._source,
                system=(
                    "你是翻译助手。将用户给出的屏幕文字译为简体中文；"
                    "若原文已是中文则译为英文。只输出译文，不要解释。"
                ),
                temperature=0.2,
                profile_id=self._profile_id or None,
            )
            text = str(translated or "").strip()
            if not text:
                self.failed.emit("译文为空，请稍后重试。")
                return
            self.finished.emit(text)
        except Exception as exc:
            from core.exceptions import format_exception

            msg = getattr(exc, "user_message", None) or format_exception(exc)
            self.failed.emit(str(msg))


class TranslateResultDialog(BaseDialog):
    dialog_kind = "large"

    def __init__(
        self,
        parent=None,
        *,
        source: str = "",
        translated: str = "",
        offer_translate: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("截图翻译")
        self._source = source or ""
        self._translated = translated or ""
        self._offer_translate = offer_translate
        self._thread: QThread | None = None
        self._worker: _TranslateWorker | None = None
        self._profile_ids: list[str] = []

        lay = QVBoxLayout(self)
        lay.addWidget(PageTitle("原文 / 译文对照"))
        lay.addWidget(
            HintLabel("选模型即用 · 未绑定时点「简单配置」两步搞定。可分别复制。")
        )

        model_row = QHBoxLayout()
        model_row.addWidget(HintLabel("模型"))
        self._profile_combo = ComboBox()
        self._profile_combo.setMinimumWidth(240)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        model_row.addWidget(self._profile_combo, 1)
        btn_cfg = SecondaryButton("简单配置…")
        btn_cfg.setToolTip("两步：① 选来源 ② Key → 保存记住")
        btn_cfg.clicked.connect(self._open_simple_setup)
        model_row.addWidget(btn_cfg)
        lay.addLayout(model_row)

        cols = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(HintLabel("原文"))
        self._src = ReadOnlyPlainTextEdit()
        self._src.setPlainText(self._source)
        self._src.setMinimumHeight(240)
        left.addWidget(self._src)
        cols.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(HintLabel("译文"))
        self._dst = ReadOnlyPlainTextEdit()
        self._dst.setPlainText(self._translated)
        self._dst.setMinimumHeight(240)
        right.addWidget(self._dst)
        cols.addLayout(right, 1)
        lay.addLayout(cols)

        row = QHBoxLayout()
        btn_src = SecondaryButton("复制原文")
        btn_src.clicked.connect(lambda: self._copy(self._source))
        row.addWidget(btn_src)
        btn_dst = SecondaryButton("复制译文")
        btn_dst.clicked.connect(lambda: self._copy(self._dst.toPlainText()))
        row.addWidget(btn_dst)
        btn_agent = SecondaryButton("送到智能体")
        btn_agent.setToolTip("将原文与译文送入 Harness 编码智能体")
        btn_agent.clicked.connect(self._send_to_harness)
        row.addWidget(btn_agent)
        self._btn_tr = PrimaryButton("翻译原文")
        self._btn_tr.setToolTip("调用大模型把左侧原文译为译文（后台执行，勿连点）")
        self._btn_tr.clicked.connect(self._run_translate)
        row.addWidget(self._btn_tr)
        row.addStretch(1)
        btn_ok = SecondaryButton("关闭")
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_ok)
        lay.addLayout(row)

        self._reload_profiles()
        if not self._source.strip():
            self._btn_tr.setEnabled(False)

    def _reload_profiles(self) -> None:
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
        self._profile_combo.addItem("＋ 绑定新模型…", _BIND)
        if self._profile_ids:
            effective = pick_effective_profile_id("text_llm", persist=True)
            if effective in self._profile_ids:
                self._profile_combo.setCurrentIndex(self._profile_ids.index(effective))
            else:
                self._profile_combo.setCurrentIndex(0)
        self._profile_combo.blockSignals(False)

    def _current_profile_id(self) -> str:
        data = self._profile_combo.currentData()
        if data == _BIND:
            return ""
        return str(data or "")

    def _on_profile_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self._profile_combo.itemData(index)
        if data == _BIND:
            self._profile_combo.blockSignals(True)
            if self._profile_ids:
                self._profile_combo.setCurrentIndex(0)
            self._profile_combo.blockSignals(False)
            self._open_simple_setup()
            return
        pid = str(data or "")
        if pid:
            set_active_profile_id("text_llm", pid)

    def _open_simple_setup(self) -> None:
        from modules.llm_assistant.llm_simple_setup_dialog import LlmSimpleSetupDialog

        dlg = LlmSimpleSetupDialog(self)
        dlg.exec()
        self._reload_profiles()

    def _copy(self, text: str) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text or "")

    def _send_to_harness(self) -> None:
        src = self._src.toPlainText().strip()
        dst = self._dst.toPlainText().strip()
        if not src and not dst:
            show_warning(self, "没有可发送的内容。")
            return
        parts = []
        if src:
            parts.append(f"【原文】\n{src}")
        if dst:
            parts.append(f"【译文】\n{dst}")
        text = "\n\n".join(parts)
        from services.harness_feed import navigate_to_harness

        win = self.window()
        if win is not None:
            navigate_to_harness(win, text, title="来自截图翻译", source="screenshot_translate")
        self.accept()

    def _set_busy(self, busy: bool) -> None:
        self._btn_tr.setEnabled(not busy and bool(self._src.toPlainText().strip()))
        self._btn_tr.setText("翻译中…" if busy else "翻译原文")

    def _run_translate(self) -> None:
        source = (self._src.toPlainText() or "").strip()
        if not source:
            show_warning(self, "没有可翻译的原文。")
            return
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在翻译，请稍候，勿连点。")
            return

        pid = self._current_profile_id() or pick_effective_profile_id(
            "text_llm", persist=True
        )
        if not pid:
            if ask_confirm(
                self,
                "还没有可用写字模型。现在按两步配置？\n"
                "① 选来源  →  ② 粘贴 Key\n"
                "也可稍后再说，先看原文。",
                title="探索翻译模型",
            ):
                self._open_simple_setup()
            return

        self._set_busy(True)
        report_status(self, "正在翻译…", level=StatusLevel.INFO)

        self._thread = QThread(self)
        self._worker = _TranslateWorker(source, profile_id=pid)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_translate_ok)
        self._worker.failed.connect(self._on_translate_fail)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_translate_ok(self, text: str) -> None:
        self._translated = text
        self._dst.setPlainText(text)
        self._set_busy(False)
        report_status(self, "翻译完成", level=StatusLevel.SUCCESS)

    def _on_translate_fail(self, message: str) -> None:
        self._set_busy(False)
        msg = (message or "").strip()
        low = msg.lower()
        if any(k in low for k in ("key", "api", "未配置", "未启用", "未绑定", "auth")):
            if ask_confirm(
                self,
                f"{msg}\n\n是否打开「简单配置」两步绑定模型？",
                title="截图翻译",
            ):
                self._open_simple_setup()
            report_status(self, "翻译失败 · 可配置模型", level=StatusLevel.ERROR)
            return
        from core.user_messages import show_error

        show_error(self, msg, title="截图翻译失败")
        report_status(self, "翻译失败", level=StatusLevel.ERROR)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def reject(self) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在翻译，请稍候再关闭。")
            return
        super().reject()

    def accept(self) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在翻译，请稍候再关闭。")
            return
        super().accept()
