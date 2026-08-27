# -*- coding: utf-8 -*-
"""截图翻译对照弹窗（挂截图工具栏，非独立空菜单）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from core.status_service import StatusLevel, report_status
from core.user_messages import show_warning
from widgets import HintLabel, PageTitle, PrimaryButton, ReadOnlyPlainTextEdit, SecondaryButton


class _TranslateWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, source: str) -> None:
        super().__init__()
        self._source = source

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
            )
            text = str(translated or "").strip()
            if not text:
                self.failed.emit("译文为空，请稍后重试。")
                return
            self.finished.emit(text)
        except Exception as exc:
            from core.exceptions import format_exception

            self.failed.emit(format_exception(exc))


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

        lay = QVBoxLayout(self)
        lay.addWidget(PageTitle("原文 / 译文对照"))
        lay.addWidget(HintLabel("引擎经 integrations（OCR + LLM）。可在本窗直接翻译并分别复制。"))

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

        if not self._source.strip():
            self._btn_tr.setEnabled(False)

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

        self._set_busy(True)
        report_status(self, "正在翻译…", level=StatusLevel.INFO)

        self._thread = QThread(self)
        self._worker = _TranslateWorker(source)
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
        from core.user_messages import show_error

        show_error(self, message, title="截图翻译失败")
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
