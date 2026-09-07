# -*- coding: utf-8 -*-
"""扣分备注整理：粘贴 → 整理 → 复制 + 历史。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.error_handler import confirm
from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.deduction_note_formatter.deduction_note_service import (
    format_deduction_notes,
    score_from_item_count,
)
from modules.deduction_note_formatter.history_store import DeductionNoteHistory
from services.storage_paths import list_module_samples
from widgets import (
    DangerButton,
    FormSection,
    HintLabel,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SectionTitle,
    SemanticLabel,
)
from widgets.list_edit import ListPanel, confirm_delete

_DEFAULT_SAMPLE = (
    "没有管理层参加 扣5分\n\n"
    '"现场没有演练式检核扣5分；\n'
    '未针对AC的检核和演练有点评扣5分；"\n'
    "没有打分或成绩记录 扣5分"
)


class DeductionNotePage(BasePage):
    page_id = "deduction_note_formatter"
    page_title = "扣分备注整理"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._history = DeductionNoteHistory()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        root = scroll.content_layout

        root.addWidget(
            PageHeader(
                "扣分备注整理",
                "粘贴 Excel / 文本 → 整理为带序号列表；Ctrl+Shift+V 一键粘贴整理并复制，Ctrl+Enter 仅整理。",
            )
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(SectionTitle("原文"))
        self._input = PlainTextEdit()
        self._input.setPlaceholderText("在此粘贴扣分备注原文…")
        self._input.setMinimumHeight(160)
        left_lay.addWidget(self._input)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.addWidget(SectionTitle("整理结果"))
        self._output = ReadOnlyPlainTextEdit()
        self._output.setMinimumHeight(160)
        right_lay.addWidget(self._output)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_format = PrimaryButton("整理")
        btn_format.clicked.connect(self._on_format)
        actions.addWidget(btn_format)

        btn_paste = PrimaryButton("粘贴并整理")
        btn_paste.setToolTip("Ctrl+Shift+V：剪贴板 → 整理 → 复制")
        btn_paste.clicked.connect(self._on_paste_format)
        actions.addWidget(btn_paste)

        btn_copy = SecondaryButton("复制结果")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)

        btn_sample = SecondaryButton("加载示例")
        btn_sample.clicked.connect(self._on_load_sample)
        actions.addWidget(btn_sample)

        btn_clear = SecondaryButton("清空")
        btn_clear.clicked.connect(self._on_clear)
        actions.addWidget(btn_clear)

        actions.addStretch(1)

        score_strip = QHBoxLayout()
        score_strip.setSpacing(4)
        score_strip.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._count_label = HintLabel("共 0 条")
        self._count_label.setWordWrap(False)
        self._score_prefix = HintLabel("· 得分")
        self._score_prefix.setWordWrap(False)
        self._score_value = SemanticLabel("100", kind="success", score=True)
        self._deduct_sep = HintLabel("/ 扣")
        self._deduct_sep.setWordWrap(False)
        self._deduct_value = SemanticLabel("0", kind="danger", score=True)
        for w in (
            self._count_label,
            self._score_prefix,
            self._score_value,
            self._deduct_sep,
            self._deduct_value,
        ):
            score_strip.addWidget(w)
        actions.addLayout(score_strip)
        root.addLayout(actions)

        hist_box = FormSection("历史记录")
        self._hist_panel = ListPanel(
            add_label="",
            edit_label="使用选中",
            delete_label="删除选中",
            refresh_label="刷新",
            hint="双击条目可快速载入；整理结果自动写入历史。",
        )
        self._hist_panel._btn_add.setVisible(False)
        # 多露出几条历史（约 6～7 行），仍可滚动
        self._hist_panel.list_widget.setMinimumHeight(200)
        self._hist_panel.list_widget.setMaximumHeight(280)
        self._hist_panel.list_widget.itemDoubleClicked.connect(self._on_hist_use)
        self._hist_panel.bind_edit(self._on_hist_use)
        self._hist_panel.bind_delete(self._on_hist_delete)
        self._hist_panel.bind_refresh(self._refresh_history)
        btn_clear_hist = DangerButton("清空历史")
        btn_clear_hist.clicked.connect(self._on_hist_clear)
        self._hist_panel.append_action_button(btn_clear_hist)
        hist_box.add_widget(self._hist_panel)
        root.addWidget(hist_box)

        self._bind_shortcuts()
        self._refresh_history()
        self._refresh_score_hint(0)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._input

    def focus_tab_widgets(self) -> list:
        return [self._input, self._hist_panel.list_widget]

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Return"), self, self._on_format)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, self._on_paste_format)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self._on_copy)

    def _on_paste_format(self) -> None:
        clip = QGuiApplication.clipboard().text()
        if not (clip or "").strip():
            show_warning(self, "剪贴板没有文本。请先 Excel 复制再按 Ctrl+Shift+V。")
            return
        self._input.setPlainText(clip)
        self._on_format()
        if self._output.toPlainText().strip():
            self._on_copy()

    def _refresh_score_hint(self, count: int) -> None:
        score, deducted = score_from_item_count(count)
        self._count_label.setText(f"共 {count} 条")
        self._score_value.setText(str(score))
        self._deduct_value.setText(str(deducted))

    def _on_format(self) -> None:
        raw = self._input.toPlainText()
        if not raw.strip():
            show_warning(self, "请先粘贴原文。")
            return
        result = format_deduction_notes(raw)
        text = result.text
        self._output.setPlainText(text)
        self._history.add(raw, text, result.count)
        self._refresh_history()
        self._refresh_score_hint(result.count)
        self.report_status(f"已整理 {result.count} 条", level=StatusLevel.SUCCESS)

    def _on_copy(self) -> None:
        text = self._output.toPlainText().strip()
        if not text:
            show_warning(self, "没有可复制的结果，请先整理。")
            return
        QGuiApplication.clipboard().setText(text)
        self.report_status("结果已复制到剪贴板", level=StatusLevel.SUCCESS)

    def _on_load_sample(self) -> None:
        samples = list_module_samples(self.page_id)
        if samples:
            try:
                text = samples[0].read_text(encoding="utf-8")
            except OSError:
                text = _DEFAULT_SAMPLE
        else:
            text = _DEFAULT_SAMPLE
        self._input.setPlainText(text)
        self.report_status("已加载示例")

    def _on_clear(self) -> None:
        if not confirm(self, "确定清空当前原文与结果？"):
            return
        self._input.clear()
        self._output.clear()
        self._refresh_score_hint(0)
        self.report_status("已清空")

    def _refresh_history(self) -> None:
        lines = []
        for item in self._history.items:
            ts = item.get("ts") or ""
            count = item.get("count") or 0
            preview = str(item.get("preview") or "").replace("\n", " ")[:80]
            lines.append(f"{ts} · {count}条 · {preview}")
        self._hist_panel.set_items(lines)

    def _on_hist_use(self) -> None:
        row = self._hist_panel.current_row()
        if row < 0 or row >= len(self._history.items):
            return
        entry = self._history.items[row]
        self._input.setPlainText(str(entry.get("source") or ""))
        self._output.setPlainText(str(entry.get("text") or ""))
        self._refresh_score_hint(int(entry.get("count") or 0))
        self.report_status("已载入历史记录")

    def _on_hist_delete(self) -> None:
        row = self._hist_panel.current_row()
        if row < 0:
            return
        if not confirm_delete(self, "选中的历史记录"):
            return
        self._history.remove_at(row)
        self._refresh_history()
        self.report_status("已删除历史条目")

    def _on_hist_clear(self) -> None:
        if not confirm(self, "确定清空全部历史记录？此操作不可恢复。"):
            return
        self._history.clear()
        self._refresh_history()
        self.report_status("历史已清空")

    def on_enter(self) -> None:
        self.report_status("扣分备注整理")

    def focus_source_input(self) -> None:
        self.focus_primary()
