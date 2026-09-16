# -*- coding: utf-8 -*-
"""助教招聘稿：班级命名即表单 · 话术骨架锁定 · 复制即发。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QSplitter, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.assistant_recruit_post.assistant_recruit_post_service import (
    DEFAULT_DAILY_RATE,
    SAMPLE_ADDRESS,
    SAMPLE_CLASS_NAME,
    RecruitFields,
    compute_fee,
    format_cn_date,
    parse_class_name,
    render_recruit_post,
    save_recruit_txt,
)
from services.storage_paths import module_output_dir
from widgets import (
    FormRow,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SpinBox,
)

_LABEL_W = 64


class AssistantRecruitPostPage(BasePage):
    page_id = "assistant_recruit_post"
    page_title = "助教招聘稿"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        root = scroll.content_layout

        root.addWidget(
            PageHeader(
                "助教招聘稿",
                "粘贴班级名与地址 → 校对字段 → 生成并复制发群。职责/着装为公司固定话术，仅出现在成稿中。",
            )
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # —— 左：输入 + 校对 ——
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(10)

        input_box = FormSection("班级与地址")
        self._class_name = LineEdit()
        self._class_name.setPlaceholderText("课程-城市-开始YYYYMMDD-结束YYYYMMDD")
        self._class_name.editingFinished.connect(self._on_class_name_finished)
        input_box.add_widget(FormRow("班级名称", self._class_name, label_width=_LABEL_W))

        self._address = LineEdit()
        self._address.setPlaceholderText("完整工作地址")
        input_box.add_widget(FormRow("工作地址", self._address, label_width=_LABEL_W))
        input_box.add_widget(
            HintLabel("解析失败时可手工改右侧校对字段，不堵死出稿。")
        )

        prefill_row = QHBoxLayout()
        prefill_row.setSpacing(8)
        btn_sample = SecondaryButton("加载示例")
        btn_sample.clicked.connect(self._on_load_sample)
        prefill_row.addWidget(btn_sample)
        btn_board = SecondaryButton("从看板预填")
        btn_board.setToolTip("读取培训交付看板当前班级名")
        btn_board.clicked.connect(self._on_prefills_from_board)
        prefill_row.addWidget(btn_board)
        prefill_row.addStretch(1)
        input_box.add_layout(prefill_row)
        left_lay.addWidget(input_box)

        fields_box = FormSection("校对字段")
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._city = LineEdit()
        self._start = LineEdit()
        self._end = LineEdit()
        self._days = SpinBox()
        self._days.setRange(1, 366)
        self._days.setValue(1)
        self._rate = SpinBox()
        self._rate.setRange(0, 9999)
        self._rate.setValue(DEFAULT_DAILY_RATE)
        self._fee = SpinBox()
        self._fee.setRange(0, 999999)
        self._fee.setValue(DEFAULT_DAILY_RATE)

        def _cell(label: str, field: QWidget) -> QWidget:
            return FormRow(label, field, label_width=_LABEL_W)

        grid.addWidget(_cell("城市", self._city), 0, 0)
        grid.addWidget(_cell("天数", self._days), 0, 1)
        grid.addWidget(_cell("开始", self._start), 1, 0)
        grid.addWidget(_cell("结束", self._end), 1, 1)
        grid.addWidget(_cell("日薪", self._rate), 2, 0)
        grid.addWidget(_cell("费用", self._fee), 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        fields_box.add_widget(grid_host)
        fields_box.add_widget(
            HintLabel("改天数/日薪自动重算费用；也可直接改费用。")
        )
        left_lay.addWidget(fields_box)
        left_lay.addStretch(1)

        # —— 右：成稿预览（主区） ——
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(10)

        out_box = FormSection("招聘稿成稿")
        self._output = ReadOnlyPlainTextEdit()
        self._output.setPlaceholderText("生成后显示完整招聘稿，可直接复制发群…")
        self._output.setMinimumHeight(280)
        self._output.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        out_box.add_widget(self._output)
        right_lay.addWidget(out_box, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 580])
        root.addWidget(splitter, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_gen_copy = PrimaryButton("生成并复制")
        btn_gen_copy.setToolTip("Ctrl+Return：生成并复制到剪贴板")
        btn_gen_copy.clicked.connect(self._on_generate_and_copy)
        actions.addWidget(btn_gen_copy)

        btn_gen = SecondaryButton("仅生成")
        btn_gen.clicked.connect(self._on_generate)
        actions.addWidget(btn_gen)

        btn_copy = SecondaryButton("复制结果")
        btn_copy.setToolTip("Ctrl+Shift+C")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)

        btn_save = SecondaryButton("保存 txt")
        btn_save.clicked.connect(self._on_save)
        actions.addWidget(btn_save)
        actions.addStretch(1)
        root.addLayout(actions)

        self._days.valueChanged.connect(self._on_days_or_rate_changed)
        self._rate.valueChanged.connect(self._on_days_or_rate_changed)

        QShortcut(QKeySequence("Ctrl+Return"), self, self._on_generate_and_copy)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self._on_copy)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._class_name

    def focus_tab_widgets(self) -> list:
        return [self._class_name, self._address, self._output]

    def on_enter(self) -> None:
        self._try_prefill_board(silent=True)
        self.report_status("助教招聘稿")

    def _on_class_name_finished(self) -> None:
        self._apply_parse(show_error=True)

    def _apply_parse(self, *, show_error: bool) -> bool:
        result = parse_class_name(self._class_name.text())
        if not result.ok:
            if show_error and result.message:
                self.report_status(result.message, level=StatusLevel.WARNING)
            if result.city:
                self._city.setText(result.city)
            if result.start is not None:
                self._start.setText(format_cn_date(result.start))
            if result.end is not None:
                self._end.setText(format_cn_date(result.end))
            if result.days > 0:
                self._set_days_and_fee(result.days)
            return False
        self._updating = True
        try:
            self._city.setText(result.city)
            assert result.start is not None and result.end is not None
            self._start.setText(format_cn_date(result.start))
            self._end.setText(format_cn_date(result.end))
            self._set_days_and_fee(result.days)
        finally:
            self._updating = False
        self.report_status(
            f"已解析：{result.city} · {result.days} 天 · 费用 {compute_fee(result.days, self._rate.value())}",
            level=StatusLevel.SUCCESS,
        )
        return True

    def _set_days_and_fee(self, days: int) -> None:
        self._updating = True
        try:
            self._days.setValue(max(1, int(days)))
            self._fee.setValue(compute_fee(self._days.value(), self._rate.value()))
        finally:
            self._updating = False

    def _on_days_or_rate_changed(self, *_args) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self._fee.setValue(compute_fee(self._days.value(), self._rate.value()))
        finally:
            self._updating = False

    def _collect_fields(self) -> RecruitFields:
        return RecruitFields(
            city=self._city.text().strip(),
            start_text=self._start.text().strip(),
            end_text=self._end.text().strip(),
            address=self._address.text().strip(),
            days=int(self._days.value()),
            daily_rate=int(self._rate.value()),
            fee=int(self._fee.value()),
        )

    def _render_to_output(self) -> str | None:
        if not self._city.text().strip() or not self._start.text().strip():
            self._apply_parse(show_error=False)
        try:
            text = render_recruit_post(self._collect_fields())
        except ValueError as exc:
            show_warning(self, str(exc))
            return None
        self._output.setPlainText(text)
        return text

    def _on_generate(self) -> None:
        text = self._render_to_output()
        if text:
            self.report_status("招聘稿已生成", level=StatusLevel.SUCCESS)

    def _on_generate_and_copy(self) -> None:
        text = self._render_to_output()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.report_status("已生成并复制到剪贴板，可直接粘贴发群", level=StatusLevel.SUCCESS)

    def _on_copy(self) -> None:
        text = self._output.toPlainText().strip()
        if not text:
            show_warning(self, "没有可复制的结果，请先生成。")
            return
        QGuiApplication.clipboard().setText(text)
        self.report_status("结果已复制到剪贴板", level=StatusLevel.SUCCESS)

    def _on_save(self) -> None:
        text = self._output.toPlainText().strip()
        if not text:
            text = self._render_to_output() or ""
        if not text:
            return
        out_dir = module_output_dir(self.page_id, create=True)
        path = save_recruit_txt(
            text,
            out_dir=out_dir,
            city=self._city.text().strip(),
            start_text=self._start.text().strip(),
        )
        show_saved(self, f"招聘稿已保存：{path.name}", path)

    def _on_load_sample(self) -> None:
        self._class_name.setText(SAMPLE_CLASS_NAME)
        self._address.setText(SAMPLE_ADDRESS)
        self._rate.setValue(DEFAULT_DAILY_RATE)
        self._apply_parse(show_error=True)
        self._render_to_output()
        self.report_status("已加载示例并生成预览")

    def _on_prefills_from_board(self) -> None:
        if not self._try_prefill_board(silent=False):
            show_warning(self, "培训交付看板暂无班级名，请先在看板绑定班级，或手工粘贴。")

    def _try_prefill_board(self, *, silent: bool) -> bool:
        try:
            from services.class_session_handoff import load_session
        except Exception:
            return False
        session = load_session()
        name = str(getattr(session, "class_name", "") or "").strip()
        if not name:
            return False
        if self._class_name.text().strip() and silent:
            return True
        self._class_name.setText(name)
        self._apply_parse(show_error=not silent)
        if not silent:
            self.report_status(f"已预填看板班级：{name}")
        return True
