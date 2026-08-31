# -*- coding: utf-8 -*-
"""生成交付报告：班级交付目录 → Word 封面贴图 + Excel 层级图片统计。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_saved, show_warning
from modules.deliverable_directory_check.deliverable_directory_check_service import (
    DeliveryReportContext,
    export_all_reports,
    export_excel_report,
    export_word_report,
)
from services.storage_paths import module_output_dir
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
)


class DeliverableDirectoryCheckPage(BasePage):
    page_id = "deliverable_directory_check"
    page_title = "生成交付报告"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._log_lines: list[str] = []

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(12)

        outer.addWidget(
            PageHeader(
                "生成交付报告",
                "选择班级交付目录，扫描结构与图片，导出 Word 交付报告与 Excel 层级统计。",
            )
        )

        path_box = FormSection("班级交付目录")
        row = QHBoxLayout()
        self._root = LineEdit()
        self._root.setPlaceholderText("选择班级交付材料根目录…")
        row.addWidget(self._root, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        path_box.add_layout(row)
        path_box.add_widget(
            HintLabel("与「交付材料生成」不同：本页只做检查报告，不生成 PPT 模板目录。")
        )
        outer.addWidget(path_box)

        actions = QHBoxLayout()
        btn_word = PrimaryButton("导出 Word 报告")
        btn_word.clicked.connect(self._on_export_word)
        actions.addWidget(btn_word)
        btn_xlsx = SecondaryButton("导出 Excel 统计")
        btn_xlsx.clicked.connect(self._on_export_excel)
        actions.addWidget(btn_xlsx)
        btn_all = SecondaryButton("全部导出")
        btn_all.clicked.connect(self._on_export_all)
        actions.addWidget(btn_all)
        actions.addStretch(1)
        outer.addLayout(actions)

        log_box = FormSection("操作日志")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(220)
        log_box.add_widget(self._log, stretch=1)
        outer.addWidget(log_box, 1)

        self.apply_page_focus_policy()
        self._append_log("欢迎使用生成交付报告")
        self._append_log("请先选择班级交付目录")

    def primary_focus_widget(self):
        return self._root

    def _append_log(self, message: str, *, error: bool = False) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {message}"
        self._log_lines.append(line)
        self._log.setPlainText("\n".join(self._log_lines))
        if error:
            self.report_status(message, level=StatusLevel.ERROR)
        scrollbar = self._log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _service_log(self, message: str, error: bool = False) -> None:
        self._append_log(message, error=error)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择班级交付目录")
        if path:
            self._root.setText(path)
            self._append_log(f"已选择目录: {path}")
            self.report_status("已选择交付目录", level=StatusLevel.INFO)

    def _build_context(self) -> DeliveryReportContext | None:
        root = self._root.text().strip()
        if not root:
            show_warning(self, "请先选择班级交付目录。")
            return None
        try:
            return DeliveryReportContext.from_root(root)
        except ValueError as e:
            show_warning(self, str(e))
            return None

    def _output_dir(self, ctx: DeliveryReportContext, *, batch: bool = False) -> Path:
        out_root = module_output_dir(self.page_id, create=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if batch:
            return out_root / f"{ctx.base_dir_name}_交付报告_{stamp}"
        return out_root

    def _on_export_word(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return

        def _run() -> None:
            out_dir = self._output_dir(ctx)
            path = export_word_report(
                ctx,
                out_dir / f"{ctx.base_dir_name}_交付报告.docx",
                self._service_log,
            )
            self.report_status(f"Word 已导出 · {path.name}", level=StatusLevel.SUCCESS)
            show_saved(self, f"Word 报告已保存：\n{path}", path.parent)

        self.run_safe(_run, title="Word 导出失败")

    def _on_export_excel(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return

        def _run() -> None:
            out_dir = self._output_dir(ctx)
            path = export_excel_report(
                ctx,
                out_dir / f"{ctx.base_dir_name}_目录统计.xlsx",
                self._service_log,
            )
            self.report_status(f"Excel 已导出 · {path.name}", level=StatusLevel.SUCCESS)
            show_saved(self, f"Excel 统计已保存：\n{path}", path.parent)

        self.run_safe(_run, title="Excel 导出失败")

    def _on_export_all(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return

        def _run() -> None:
            out_dir = self._output_dir(ctx, batch=True)
            word_path, excel_path = export_all_reports(ctx, out_dir, self._service_log)
            self._append_log("全部导出完成！")
            self.report_status("Word + Excel 已导出", level=StatusLevel.SUCCESS)
            show_saved(
                self,
                f"已导出：\n{word_path.name}\n{excel_path.name}\n\n目录：\n{out_dir}",
                out_dir,
            )

        self.run_safe(_run, title="导出失败")

    def on_enter(self) -> None:
        self.report_status("生成交付报告")
        self.schedule_primary_focus()
