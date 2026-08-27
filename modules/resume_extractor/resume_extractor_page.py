# -*- coding: utf-8 -*-
"""简历信息提取：单文件 / 目录批量 → 预览 → 导出 CSV/XLSX。"""
from __future__ import annotations

import json

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QSizePolicy, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_info, show_saved, show_warning
from modules.resume_extractor.resume_extractor_service import (
    extract_directory,
    extract_resume,
    export_results,
    ocr_status_summary,
    rows_from_results,
    save_extract_json,
)
from services.storage_paths import module_output_dir
from widgets import (
    ComboBox,
    DataTable,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
)


class ResumeExtractorPage(BasePage):
    page_id = "resume_extractor"
    page_title = "简历信息提取"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._results: list = []

        # 不用整页 ScrollPage：表格区纵向撑满，避免「表小、底下大片空白」
        root = QVBoxLayout(self)
        m = page_content_margins()
        root.setContentsMargins(m[0], m[1], m[2], m[3])
        root.setSpacing(10)

        root.addWidget(
            PageHeader(
                "简历信息提取",
                "选择简历文件或目录，递归提取姓名/手机/微信/城市；图片与扫描件 PDF 走 OCR。",
            ),
            0,
        )

        src_box = FormSection("源")
        row = QHBoxLayout()
        self._src = LineEdit()
        row.addWidget(self._src, 1)
        btn_file = SecondaryButton("选文件…")
        btn_file.clicked.connect(self._browse_file)
        row.addWidget(btn_file)
        btn_dir = SecondaryButton("选目录…")
        btn_dir.clicked.connect(self._browse_dir)
        row.addWidget(btn_dir)
        src_box.add_layout(row)
        src_box.add_widget(
            HintLabel(
                "支持 PDF / 图片 / txt / md / docx / pptx（旧版 .ppt 请另存为 pptx）。"
                "目录模式递归扫描多级子文件夹。"
            )
        )
        self._ocr_hint = HintLabel(ocr_status_summary())
        src_box.add_widget(self._ocr_hint)
        root.addWidget(src_box, 0)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("提取")
        btn_go.clicked.connect(self._on_extract)
        actions.addWidget(btn_go)
        actions.addWidget(HintLabel("导出格式"))
        self._fmt = ComboBox()
        self._fmt.addItems(["xlsx", "csv"])
        actions.addWidget(self._fmt)
        btn_export = SecondaryButton("导出表格")
        btn_export.clicked.connect(self._on_export)
        actions.addWidget(btn_export)
        actions.addStretch(1)
        root.addLayout(actions)

        table_box = FormSection("字段结果")
        table_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._table = DataTable()
        self._table.setMinimumHeight(320)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._table.set_headers(["文件名", "城市", "姓名", "手机号", "微信号", "备注", "引擎"])
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        table_box.add_widget(self._table, stretch=1)
        root.addWidget(table_box, 1)

        detail = FormSection("详情 JSON")
        detail.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._preview = ReadOnlyPlainTextEdit()
        self._preview.setMinimumHeight(72)
        self._preview.setMaximumHeight(140)
        self._preview.setPlaceholderText("选中表格一行查看该条 JSON；批量提取后默认显示摘要。")
        detail.add_widget(self._preview)
        root.addWidget(detail, 0)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._src

    def focus_tab_widgets(self):
        return [self._src]

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择简历文件",
            "",
            "简历 (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp "
            "*.txt *.md *.docx *.pptx);;所有文件 (*.*)",
        )
        if path:
            self._src.setText(path)

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择简历目录")
        if path:
            self._src.setText(path)

    def _fill_table(self) -> None:
        rows = rows_from_results(self._results)
        self._table.set_headers(["文件名", "城市", "姓名", "手机号", "微信号", "备注", "引擎"])
        self._table.set_rows(
            [
                (
                    str(r.get("文件名") or ""),
                    str(r.get("城市") or ""),
                    str(r.get("姓名") or ""),
                    str(r.get("手机号") or ""),
                    str(r.get("微信号") or ""),
                    str(r.get("备注") or ""),
                    str(r.get("引擎") or ""),
                )
                for r in rows
            ]
        )

    def _on_row_selected(self) -> None:
        items = self._table.selectedItems()
        if not items or not self._results:
            return
        row = items[0].row()
        if row < 0 or row >= len(self._results):
            return
        self._preview.setPlainText(
            json.dumps(self._results[row], ensure_ascii=False, indent=2)
        )

    def _on_extract(self) -> None:
        src = self._src.text().strip()
        if not src:
            show_warning(self, "请先选择文件或目录。")
            return

        def _run() -> None:
            from pathlib import Path

            p = Path(src)
            if p.is_dir():
                self._results = extract_directory(p)
            elif p.is_file():
                self._results = [extract_resume(p)]
            else:
                raise FileNotFoundError(f"路径不存在: {src}")

            self._fill_table()
            if len(self._results) == 1:
                text = json.dumps(self._results[0], ensure_ascii=False, indent=2)
                self._preview.setPlainText(text)
                out = save_extract_json(
                    self._results[0], module_output_dir(self.page_id, create=True)
                )
                self.report_status(f"已提取并保存 {out.name}", level=StatusLevel.SUCCESS)
            else:
                self._preview.setPlainText(
                    f"批量完成：{len(self._results)} 个文件\n"
                    "（点击表格某一行查看该条详情 JSON）"
                )
                self.report_status(
                    f"批量提取 {len(self._results)} 个", level=StatusLevel.SUCCESS
                )
            show_info(self, f"提取完成：{len(self._results)} 条")

        self.run_safe(_run, title="提取失败")

    def _on_export(self) -> None:
        if not self._results:
            show_warning(self, "请先提取简历。")
            return

        def _run() -> None:
            path = export_results(
                self._results,
                module_output_dir(self.page_id, create=True),
                fmt=self._fmt.currentText(),
            )
            self.report_status(f"已导出 {path.name}", level=StatusLevel.SUCCESS)
            show_saved(self, f"已导出：\n{path}", path)

        self.run_safe(_run, title="导出失败")

    def on_enter(self) -> None:
        if hasattr(self, "_ocr_hint"):
            self._ocr_hint.setText(ocr_status_summary())
        self.report_status("简历信息提取")
