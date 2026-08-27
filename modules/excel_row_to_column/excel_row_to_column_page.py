# -*- coding: utf-8 -*-
"""行转列工具：列选择 + 经销商规则 + 整表转置。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.excel_row_to_column.excel_row_to_column_service import (
    convert_selected_columns,
    list_columns,
    preview_result,
    save_converted,
    transpose_file,
)
from services.storage_paths import module_output_dir
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    TabWidget,
)


class ExcelRowToColumnPage(BasePage):
    page_id = "excel_row_to_column"
    page_title = "行转列工具"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._columns: list[str] = []
        self._last_result = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "行转列工具",
                "选择列后按行展开为新列（含经销商简称）；也可整表转置。",
            )
        )

        box = FormSection("源文件")
        row = QHBoxLayout()
        self._src = LineEdit()
        self._src.setPlaceholderText("选择 .xlsx / .xls / .csv …")
        row.addWidget(self._src, 1)
        btn = SecondaryButton("浏览…")
        btn.clicked.connect(self._browse)
        row.addWidget(btn)
        btn_load = SecondaryButton("加载列")
        btn_load.clicked.connect(self._load_columns)
        row.addWidget(btn_load)
        box.add_layout(row)
        scroll.add_widget(box)

        self._tabs = TabWidget()
        scroll.add_widget(self._tabs)

        # 列选择
        tab_sel = QWidget()
        lay_sel = QVBoxLayout(tab_sel)
        col_box = FormSection("列选择")
        lists = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(HintLabel("可选列（多选）"))
        self._available = ListWidget()
        self._available.setSelectionMode(ListWidget.SelectionMode.ExtendedSelection)
        left.addWidget(self._available)
        lists.addLayout(left, 1)
        mid = QVBoxLayout()
        mid.addStretch(1)
        btn_add = SecondaryButton(">>")
        btn_add.clicked.connect(self._add_columns)
        mid.addWidget(btn_add)
        btn_rm = SecondaryButton("<<")
        btn_rm.clicked.connect(self._remove_columns)
        mid.addWidget(btn_rm)
        mid.addStretch(1)
        lists.addLayout(mid)
        right = QVBoxLayout()
        right.addWidget(HintLabel("已选列"))
        self._selected = ListWidget()
        self._selected.setSelectionMode(ListWidget.SelectionMode.ExtendedSelection)
        right.addWidget(self._selected)
        lists.addLayout(right, 1)
        col_box.add_layout(lists)
        col_box.add_widget(
            HintLabel("若含「经销商名称」列，将自动追加经销商简称与检查列。")
        )
        lay_sel.addWidget(col_box)
        btn_conv = PrimaryButton("按选中列行转列")
        btn_conv.clicked.connect(self._on_convert_selected)
        lay_sel.addWidget(btn_conv)
        self._tabs.addTab(tab_sel, "列选择转换")

        # 整表转置
        tab_all = QWidget()
        lay_all = QVBoxLayout(tab_all)
        lay_all.addWidget(HintLabel("将整张表行列互换（不挑列）。"))
        btn_all = PrimaryButton("整表转置并保存")
        btn_all.clicked.connect(self._on_transpose_all)
        lay_all.addWidget(btn_all)
        lay_all.addStretch(1)
        self._tabs.addTab(tab_all, "整表转置")

        out = FormSection("结果预览")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(120)
        out.add_widget(self._log)
        scroll.add_widget(out)

        save_row = QHBoxLayout()
        btn_save = SecondaryButton("保存结果")
        btn_save.clicked.connect(self._on_save)
        save_row.addWidget(btn_save)
        save_row.addStretch(1)
        scroll.add_layout(save_row)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._src

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择表格文件",
            "",
            "表格 (*.xlsx *.xls *.csv);;所有文件 (*.*)",
        )
        if path:
            self._src.setText(path)
            self._load_columns()

    def _load_columns(self) -> None:
        src = self._src.text().strip()
        if not src:
            show_warning(self, "请先选择源文件。")
            return

        def _run() -> None:
            cols = list_columns(src)
            self._columns = cols
            self._available.clear()
            self._selected.clear()
            self._available.addItems(cols)
            self._log.setPlainText(f"已加载 {len(cols)} 列。")
            self.report_status(f"已加载 {len(cols)} 列")

        self.run_safe(_run, title="加载失败")

    def _add_columns(self) -> None:
        for item in self._available.selectedItems():
            text = item.text()
            existing = [self._selected.item(i).text() for i in range(self._selected.count())]
            if text not in existing:
                self._selected.addItem(text)

    def _remove_columns(self) -> None:
        for item in self._selected.selectedItems():
            self._selected.takeItem(self._selected.row(item))

    def _selected_names(self) -> list[str]:
        return [self._selected.item(i).text() for i in range(self._selected.count())]

    def _on_convert_selected(self) -> None:
        src = self._src.text().strip()
        if not src:
            show_warning(self, "请先选择源文件。")
            return
        cols = self._selected_names()
        if not cols:
            show_warning(self, "请至少选择一列。")
            return

        def _run() -> None:
            result = convert_selected_columns(src, cols)
            self._last_result = result
            preview = preview_result(result)
            out_dir = module_output_dir(self.page_id, create=True)
            dest = out_dir / f"{Path(src).stem}_row2col.xlsx"
            saved = save_converted(result, dest)
            self._log.setPlainText(preview + f"\n\n已保存：{saved}")
            self.report_status("行转列完成", level=StatusLevel.SUCCESS)
            show_saved(self, f"已保存：\n{saved}", saved)

        self.run_safe(_run, title="转换失败")

    def _on_transpose_all(self) -> None:
        src = self._src.text().strip()
        if not src:
            show_warning(self, "请先选择源文件。")
            return

        def _run() -> None:
            src_path = Path(src)
            out_dir = module_output_dir(self.page_id, create=True)
            dest = out_dir / f"{src_path.stem}_transposed{src_path.suffix or '.csv'}"
            result = transpose_file(src_path, dest)
            self._last_result = None
            self._log.setPlainText(f"已保存：\n{result}")
            self.report_status("转置完成", level=StatusLevel.SUCCESS)
            show_saved(self, f"已保存：\n{result}", result)

        self.run_safe(_run, title="转置失败")

    def _on_save(self) -> None:
        if self._last_result is None:
            show_warning(self, "没有可保存的列选择转换结果（可先执行「按选中列行转列」）。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存结果",
            str(module_output_dir(self.page_id, create=True) / "row2col.xlsx"),
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not path:
            return

        def _run() -> None:
            saved = save_converted(self._last_result, path)
            self.report_status("已保存", level=StatusLevel.SUCCESS)
            show_saved(self, f"已保存：\n{saved}", saved)

        self.run_safe(_run, title="保存失败")

    def on_enter(self) -> None:
        self.report_status("行转列工具")
