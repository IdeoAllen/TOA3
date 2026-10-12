# -*- coding: utf-8 -*-
"""截图翻译对照弹窗：原文/译文并列 + 一键拷贝；OCR/翻译均走后台线程。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_dialog import BaseDialog
from core.status_service import StatusLevel, report_status
from core.user_messages import ask_confirm, show_warning
from services.compute_source import pick_effective_profile_id
from services.model_catalog import set_active_profile_id
from services.model_ready_registry import list_ready
from services.screenshot_translate import PLACEHOLDER_TRANSLATED, OcrWorker
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
            from services.screenshot_translate import translate_text

            text = translate_text(self._source, profile_id=self._profile_id or None)
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
        ocr_pending: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("截图翻译")
        self._source = source or ""
        self._translated = translated or ""
        self._offer_translate = offer_translate
        self._ocr_pending = ocr_pending
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
        if self._ocr_pending and not self._source.strip():
            self._src.setPlainText("正在识别文字…")
        else:
            self._src.setPlainText(self._source)
        self._src.setMinimumHeight(240)
        left.addWidget(self._src)
        cols.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(HintLabel("译文"))
        self._dst = ReadOnlyPlainTextEdit()
        if self._ocr_pending and not self._translated.strip():
            self._dst.setPlainText("识别完成后可点「翻译原文」。")
        else:
            self._dst.setPlainText(self._translated)
        self._dst.setMinimumHeight(240)
        right.addWidget(self._dst)
        cols.addLayout(right, 1)
        lay.addLayout(cols)

        row = QHBoxLayout()
        btn_src = SecondaryButton("复制原文")
        btn_src.clicked.connect(self._copy_source)
        row.addWidget(btn_src)
        self._btn_copy_dst = SecondaryButton("复制译文")
        self._btn_copy_dst.clicked.connect(self._copy_translated)
        row.addWidget(self._btn_copy_dst)
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
        self._refresh_actions()
        if self._offer_translate and self._source.strip() and not self._has_real_translation():
            self._btn_tr.setDefault(True)

    def _has_real_translation(self) -> bool:
        t = (self._dst.toPlainText() or "").strip()
        if not t:
            return False
        if t == PLACEHOLDER_TRANSLATED:
            return False
        if t.startswith("识别完成后") or t.startswith("（原文已复制"):
            return False
        return True

    def _refresh_actions(self) -> None:
        busy = self._thread is not None and self._thread.isRunning()
        has_src = (
            not self._ocr_pending
            and bool((self._src.toPlainText() or "").strip())
            and not (self._src.toPlainText() or "").startswith("正在识别")
        )
        self._btn_tr.setEnabled(has_src and not busy)
        self._btn_copy_dst.setEnabled(self._has_real_translation())

    def apply_ocr_result(self, source: str) -> None:
        """OCR 线程完成后灌入原文（供 launch_translate_from_pixmap）。"""
        self._ocr_pending = False
        self._source = (source or "").strip()
        self._src.setPlainText(self._source)
        if self._source:
            self._dst.setPlainText(PLACEHOLDER_TRANSLATED)
            self._push_clipboard(self._source)
            report_status(self, "识别完成 · 可翻译", level=StatusLevel.SUCCESS)
        else:
            self._dst.setPlainText("")
            show_warning(self, "未识别到文字。请确认 OCR 已在系统设置中配置。")
            report_status(self, "未识别到文字", level=StatusLevel.WARNING)
        self._refresh_actions()
        if self._offer_translate and self._source:
            self._btn_tr.setDefault(True)

    def apply_ocr_failure(self, message: str) -> None:
        self._ocr_pending = False
        self._src.setPlainText("")
        self._dst.setPlainText("")
        self._refresh_actions()
        msg = (message or "").strip() or "OCR 失败"
        low = msg.lower()
        if any(k in low for k in ("ocr", "tesseract", "未配置", "未启用", "未就绪")):
            show_warning(self, f"{msg}\n\n请在系统设置 → 集成中配置 OCR。")
        else:
            from core.user_messages import show_error

            show_error(self, msg, title="截图翻译 · 识字失败")
        report_status(self, "识字失败", level=StatusLevel.ERROR)

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

    def _push_clipboard(self, text: str) -> None:
        try:
            from services.clipboard_history_store import push_text
            from services.clipboard_watcher import get_clipboard_watcher

            get_clipboard_watcher().suppress_once()
            push_text(text, source="ocr")
        except Exception:
            pass
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text or "")

    def _copy(self, text: str, *, label: str) -> None:
        body = text or ""
        if not body.strip() or body.strip() == PLACEHOLDER_TRANSLATED:
            show_warning(self, f"没有可复制的{label}。")
            return
        if body.startswith("正在识别") or body.startswith("识别完成后"):
            show_warning(self, f"没有可复制的{label}。")
            return
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(body)
        report_status(self, f"已复制{label}", level=StatusLevel.SUCCESS)

    def _copy_source(self) -> None:
        self._copy(self._src.toPlainText(), label="原文")

    def _copy_translated(self) -> None:
        self._copy(self._dst.toPlainText(), label="译文")

    def _send_to_harness(self) -> None:
        src = self._src.toPlainText().strip()
        dst = self._dst.toPlainText().strip()
        if dst == PLACEHOLDER_TRANSLATED or dst.startswith("识别完成后"):
            dst = ""
        if not src and not dst:
            show_warning(self, "没有可发送的内容。")
            return
        if src.startswith("正在识别"):
            show_warning(self, "正在识别，请稍候。")
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
        self._btn_tr.setText("翻译中…" if busy else "翻译原文")
        self._refresh_actions()
        if busy:
            self._btn_tr.setEnabled(False)

    def _run_translate(self) -> None:
        source = (self._src.toPlainText() or "").strip()
        if not source or source.startswith("正在识别"):
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
        self._refresh_actions()
        report_status(self, "翻译完成 · 可复制译文", level=StatusLevel.SUCCESS)

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
        self._refresh_actions()

    def reject(self) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在翻译，请稍候再关闭。")
            return
        if self._ocr_pending:
            show_warning(self, "正在识别，请稍候再关闭。")
            return
        super().reject()

    def accept(self) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在翻译，请稍候再关闭。")
            return
        if self._ocr_pending:
            show_warning(self, "正在识别，请稍候再关闭。")
            return
        super().accept()


class _LaunchHost(QObject):
    """持有 OCR 线程生命周期，直至对照窗关闭。"""

    def __init__(self, parent: QWidget | None, pixmap: QPixmap) -> None:
        super().__init__(parent)
        self._dlg = TranslateResultDialog(
            parent,
            source="",
            translated="",
            offer_translate=True,
            ocr_pending=True,
        )
        self._thread = QThread(self)
        self._worker = OcrWorker(pixmap)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_ocr_ok)
        self._worker.failed.connect(self._on_ocr_fail)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

    def start(self) -> None:
        self._thread.start()
        self._dlg.exec()

    def _on_ocr_ok(self, text: str) -> None:
        self._dlg.apply_ocr_result(text)

    def _on_ocr_fail(self, message: str) -> None:
        self._dlg.apply_ocr_failure(message)

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None


def launch_translate_from_pixmap(parent: QWidget | None, pixmap: QPixmap) -> None:
    """推荐入口：后台 OCR → 对照窗 → 用户点「翻译原文」→ 复制。

    满足 STD：不在 UI 线程同步长联网。截图工具栏应调用本函数替代同步 ocr_only。
    """
    if pixmap is None or pixmap.isNull():
        show_warning(parent, "无有效截图，无法翻译。")
        return
    pix = QPixmap(pixmap)
    host = _LaunchHost(parent, pix)
    host.start()


__all__ = [
    "TranslateResultDialog",
    "launch_translate_from_pixmap",
]
