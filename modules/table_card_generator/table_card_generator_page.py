# -*- coding: utf-8 -*-
"""桌卡生成工具（单张 / 列表 / Excel）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QButtonGroup, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.table_card_generator.table_card_generator_service import (
    generate_cards,
    generate_cards_merged,
    generate_cards_separate,
    generate_single_pptx,
    list_excel_columns,
    parse_names,
    read_names_from_excel,
    resolve_template,
)
from services.storage_paths import list_module_templates, module_output_dir
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    RadioButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    TabWidget,
)


class TableCardGeneratorPage(BasePage):
    page_id = "table_card_generator"
    page_title = "桌卡生成工具"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "桌卡生成工具",
                "支持单个、文本列表、Excel 导入；可选合并单文件或每人一文件。",
            )
        )

        tpl_box = FormSection("模板")
        tpls = list_module_templates("table_card_generator")
        self._tpl_hint = HintLabel("")
        if resolve_template() and tpls:
            self._tpl_hint.setText(f"当前模板：{tpls[0]}")
        else:
            self._tpl_hint.setText(
                "警告：未找到桌卡 PPTX 模板（assets/templates/business/table_card.pptx）。"
                "当前将退回文本卡输出。"
            )
        tpl_box.add_widget(self._tpl_hint)
        scroll.add_widget(tpl_box)

        self._tabs = TabWidget()
        scroll.add_widget(self._tabs)

        # Tab 1: 单个
        tab_single = QWidget()
        lay_single = QVBoxLayout(tab_single)
        self._single_name = LineEdit()
        self._single_name.setPlaceholderText("请输入姓名")
        lay_single.addWidget(HintLabel("姓名"))
        lay_single.addWidget(self._single_name)
        btn_single = PrimaryButton("生成桌卡")
        btn_single.clicked.connect(self._on_single)
        lay_single.addWidget(btn_single)
        lay_single.addStretch(1)
        self._tabs.addTab(tab_single, "单个生成")

        # Tab 2: 文本列表
        tab_list = QWidget()
        lay_list = QVBoxLayout(tab_list)
        self._names = PlainTextEdit()
        self._names.setPlaceholderText("张三\n李四\n王五")
        self._names.setMinimumHeight(160)
        lay_list.addWidget(self._names)
        self._list_mode = self._make_output_mode(lay_list)
        btn_list = PrimaryButton("批量生成")
        btn_list.clicked.connect(self._on_text_list)
        lay_list.addWidget(btn_list)
        self._tabs.addTab(tab_list, "文本列表")

        # Tab 3: Excel
        tab_excel = QWidget()
        lay_excel = QVBoxLayout(tab_excel)
        row = QHBoxLayout()
        self._excel_path = LineEdit()
        self._excel_path.setReadOnly(True)
        row.addWidget(self._excel_path, 1)
        browse = SecondaryButton("浏览…")
        browse.clicked.connect(self._pick_excel)
        row.addWidget(browse)
        lay_excel.addLayout(row)
        lay_excel.addWidget(
            HintLabel(
                "姓名列优先匹配：姓名 / 名字 / name / 学员姓名 等；"
                "也可在下方手动选择。加载后自动探测。"
            )
        )
        col_row = QHBoxLayout()
        col_row.addWidget(HintLabel("姓名列"))
        self._name_col = ComboBox()
        self._name_col.setMinimumWidth(160)
        self._name_col.addItem("（自动探测）", "")
        col_row.addWidget(self._name_col)
        col_row.addStretch(1)
        lay_excel.addLayout(col_row)
        self._excel_mode = self._make_output_mode(lay_excel)
        btn_excel = PrimaryButton("从 Excel 生成")
        btn_excel.clicked.connect(self._on_excel)
        lay_excel.addWidget(btn_excel)
        self._tabs.addTab(tab_excel, "Excel 导入")

        out = FormSection("结果")
        self._log = ReadOnlyPlainTextEdit()
        out.add_widget(self._log)
        scroll.add_widget(out)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._single_name

    def _make_output_mode(self, parent_layout: QVBoxLayout) -> QButtonGroup:
        box = FormSection("生成选项")
        group = QButtonGroup(self)
        rb_merged = RadioButton("所有桌卡合并到单个文件")
        rb_merged.setChecked(True)
        rb_sep = RadioButton("每个名字一个文件")
        group.addButton(rb_merged, 0)
        group.addButton(rb_sep, 1)
        box.add_widget(rb_merged)
        box.add_widget(rb_sep)
        parent_layout.addWidget(box)
        return group

    def _merged(self, group: QButtonGroup) -> bool:
        return group.checkedId() == 0

    def _out_dir(self) -> Path:
        return module_output_dir(self.page_id, create=True)

    def _pick_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Excel 文件",
            "",
            "Excel (*.xlsx *.xls)",
        )
        if not path:
            return
        self._excel_path.setText(path)
        self._name_col.clear()
        self._name_col.addItem("（自动探测）", "")
        try:
            cols = list_excel_columns(path)
            for c in cols:
                self._name_col.addItem(c, c)
        except Exception as e:
            self._log.setPlainText(f"读取列名失败：{e}")

    def _on_single(self) -> None:
        name = self._single_name.text().strip()
        if not name:
            show_warning(self, "请输入姓名。")
            return

        def _run() -> None:
            out_dir = self._out_dir()
            if resolve_template():
                path = generate_single_pptx(name, out_dir)
                self._log.setPlainText(f"已生成：{path}")
                show_saved(self, f"桌卡已生成：\n{path}", path)
            else:
                result = generate_cards([name], out_dir, prefer_pptx=False)
                self._log.setPlainText(result.summary)
                show_saved(self, f"桌卡已生成\n{result.summary}", result.out_dir)
            self.report_status("桌卡已生成", level=StatusLevel.SUCCESS)

        self.run_safe(_run, title="生成失败")

    def _on_text_list(self) -> None:
        names = parse_names(self._names.toPlainText())
        if not names:
            show_warning(self, "请至少输入一个姓名。")
            return
        merged = self._merged(self._list_mode)

        def _run() -> None:
            out_dir = self._out_dir()
            if merged:
                result = generate_cards_merged(names, out_dir)
            else:
                result = generate_cards_separate(names, out_dir)
            self._log.setPlainText(result.summary)
            self.report_status(f"已生成 {len(names)} 张桌卡", level=StatusLevel.SUCCESS)
            show_saved(self, f"输出目录：\n{result.out_dir}", result.out_dir)

        self.run_safe(_run, title="生成失败")

    def _on_excel(self) -> None:
        excel = self._excel_path.text().strip()
        if not excel:
            show_warning(self, "请选择 Excel 文件。")
            return
        merged = self._merged(self._excel_mode)
        col = self._name_col.currentData()
        name_column = str(col) if col else None

        def _run() -> None:
            names = read_names_from_excel(excel, name_column=name_column)
            if not names:
                raise ValueError("Excel 中未找到有效姓名")
            out_dir = self._out_dir()
            if merged:
                result = generate_cards_merged(names, out_dir)
            else:
                batch = out_dir / f"batch_{Path(excel).stem}"
                result = generate_cards_separate(names, batch)
            self._log.setPlainText(result.summary)
            self.report_status(f"Excel 批量完成：{len(names)} 人", level=StatusLevel.SUCCESS)
            show_saved(self, f"输出目录：\n{result.out_dir}", result.out_dir)

        self.run_safe(_run, title="Excel 生成失败")

    def on_enter(self) -> None:
        tpls = list_module_templates("table_card_generator")
        if resolve_template() and tpls:
            self._tpl_hint.setText(f"当前模板：{tpls[0]}")
        else:
            self._tpl_hint.setText(
                "警告：未找到桌卡 PPTX 模板。请将 table_card.pptx 放到 "
                "assets/templates/business/ 或用户模板目录。"
            )
        self.report_status("桌卡生成工具")
