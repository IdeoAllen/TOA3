# -*- coding: utf-8 -*-
"""目录结构检查：递归路径清单 + 空目录/命名问题（≠ 班级交付 Word 贴图检查）。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QSizePolicy, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_saved, show_warning
from modules.directory_inspector.directory_inspector_service import (
    export_report,
    export_report_excel,
    export_report_word,
    inspect_directory,
)
from services.storage_paths import module_output_dir
from widgets import (
    CheckBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
)


class DirectoryInspectorPage(BasePage):
    page_id = "directory_inspector"
    page_title = "目录结构检查"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_report = None
        self._last_text = ""

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(12)

        outer.addWidget(
            PageHeader(
                "目录结构检查",
                "列出相对路径，检查空目录与命名问题；导出 TXT/Word/Excel 报告。"
                "（班级交付 Word 贴图请用业务侧「生成交付报告」。）",
            )
        )

        path_box = FormSection("检查根目录")
        row = QHBoxLayout()
        self._root = LineEdit()
        self._root.setPlaceholderText("选择要检查的根目录…")
        row.addWidget(self._root, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        path_box.add_layout(row)

        self._include_dirs = CheckBox("目录（路径列表中显示目录路径）")
        self._include_dirs.setChecked(True)
        self._include_dirs.setToolTip("关闭后列表仅显示文件相对路径，目录路径不列出")
        self._include_dirs.toggled.connect(self._on_include_dirs_toggled)
        path_box.add_widget(self._include_dirs)
        path_box.add_widget(HintLabel("开启「目录」：列表含文件夹与文件；关闭：仅文件。"))
        outer.addWidget(path_box)

        actions = QHBoxLayout()
        btn_scan = PrimaryButton("开始检查")
        btn_scan.clicked.connect(self._on_scan)
        actions.addWidget(btn_scan)
        btn_txt = SecondaryButton("导出 TXT")
        btn_txt.clicked.connect(lambda: self._on_export("txt"))
        actions.addWidget(btn_txt)
        btn_docx = SecondaryButton("导出 Word")
        btn_docx.clicked.connect(lambda: self._on_export("docx"))
        actions.addWidget(btn_docx)
        btn_xlsx = SecondaryButton("导出 Excel")
        btn_xlsx.clicked.connect(lambda: self._on_export("xlsx"))
        actions.addWidget(btn_xlsx)
        btn_copy = SecondaryButton("复制")
        btn_copy.setToolTip("复制相对路径列表到剪贴板")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)
        actions.addStretch(1)
        outer.addLayout(actions)

        report_box = FormSection("路径列表 / 检查报告")
        self._report = ReadOnlyPlainTextEdit()
        self._report.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._report.setMinimumHeight(200)
        report_box.add_widget(self._report, stretch=1)
        report_box.add_widget(
            HintLabel("含文件类型统计、相对路径列表；下方为空目录与命名问题。可点「复制」拷贝路径。")
        )
        report_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        outer.addWidget(report_box, 1)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择根目录")
        if path:
            self._root.setText(path)

    def _include_dirs_flag(self) -> bool:
        return bool(self._include_dirs.isChecked())

    def _refresh_report_text(self) -> None:
        if self._last_report is None:
            return
        self._last_report.include_dirs = self._include_dirs_flag()
        self._last_text = self._last_report.as_text()
        self._report.setPlainText(self._last_text)

    def _on_include_dirs_toggled(self, _checked: bool) -> None:
        if self._last_report is None:
            return
        self._refresh_report_text()
        n = len(self._last_report.relative_paths())
        self.report_status(f"列表已刷新 · {n} 条", level=StatusLevel.INFO)

    def _on_scan(self) -> None:
        root = self._root.text().strip()
        if not root:
            show_warning(self, "请先选择根目录。")
            return

        include_dirs = self._include_dirs_flag()

        def _run() -> None:
            report = inspect_directory(root, include_dirs=include_dirs)
            self._last_report = report
            self._last_text = report.as_text()
            self._report.setPlainText(self._last_text)
            n = len(report.relative_paths())
            types_n = len(report.ext_counts)
            self.report_status(
                f"路径 {n} 条 · 类型 {types_n} 种 · 空目录 {len(report.empty_dirs)}",
                level=StatusLevel.SUCCESS,
            )

        self.run_safe(_run, title="目录检查失败")

    def _on_copy(self) -> None:
        if self._last_report is None:
            show_warning(self, "没有可复制的内容，请先检查。")
            return
        self._last_report.include_dirs = self._include_dirs_flag()
        paths = self._last_report.relative_paths()
        if not paths:
            show_warning(self, "相对路径列表为空。")
            return
        text = "\n".join(paths)
        QGuiApplication.clipboard().setText(text)
        self.report_status(f"已复制 {len(paths)} 条路径", level=StatusLevel.SUCCESS)

    def _on_export(self, kind: str = "txt") -> None:
        if not self._last_text.strip() or self._last_report is None:
            show_warning(self, "没有可导出的报告，请先检查。")
            return

        def _run() -> None:
            self._last_report.include_dirs = self._include_dirs_flag()
            self._last_text = self._last_report.as_text()
            out_dir = module_output_dir(self.page_id, create=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if kind == "docx":
                path = export_report_word(
                    self._last_report, out_dir / f"directory_report_{stamp}.docx"
                )
            elif kind == "xlsx":
                path = export_report_excel(
                    self._last_report, out_dir / f"directory_report_{stamp}.xlsx"
                )
            else:
                path = export_report(self._last_text, out_dir / f"directory_report_{stamp}.txt")
            self.report_status(f"已导出 {path.name}", level=StatusLevel.SUCCESS)
            show_saved(self, f"报告已保存：\n{path}", path)

        self.run_safe(_run, title="导出失败")

    def on_enter(self) -> None:
        self.report_status("目录结构检查")
