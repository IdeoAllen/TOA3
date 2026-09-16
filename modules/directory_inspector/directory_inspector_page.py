# -*- coding: utf-8 -*-
"""目录透视：路径清单 + 空目录/命名 + 文件类型占比饼图（≠ 班级交付 Word 贴图）。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

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
    SemanticLabel,
)
from widgets.charts import PieChartWidget


class DirectoryInspectorPage(BasePage):
    page_id = "directory_inspector"
    page_title = "目录透视"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_report = None
        self._last_text = ""

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(10)

        outer.addWidget(
            PageHeader(
                "目录透视",
                "左侧看文件类型占比，右侧看路径与问题。"
                "班级交付 Word 贴图请用业务侧「生成交付报告」。",
            )
        )

        # —— 扫描范围：路径 + 全部按钮一排 ——
        path_box = FormSection("扫描范围")
        row = QHBoxLayout()
        self._root = LineEdit()
        self._root.setPlaceholderText("选择要透视的根目录…")
        row.addWidget(self._root, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        path_box.add_layout(row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._include_dirs = CheckBox("路径列表含目录")
        self._include_dirs.setChecked(True)
        self._include_dirs.setToolTip("关闭后列表仅显示文件相对路径")
        self._include_dirs.toggled.connect(self._on_include_dirs_toggled)
        actions.addWidget(self._include_dirs)
        actions.addStretch(1)
        btn_scan = PrimaryButton("开始透视")
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
        btn_copy = SecondaryButton("复制路径")
        btn_copy.setToolTip("复制相对路径列表到剪贴板")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)
        path_box.add_layout(actions)
        outer.addWidget(path_box)

        # —— 左右分栏：左=大饼图，右=概览+路径 ——
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 4, 0)
        left_lay.setSpacing(8)
        chart_box = FormSection("文件类型占比")
        self._pie = PieChartWidget()
        self._pie.setMinimumSize(360, 360)
        self._pie.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        chart_box.add_widget(self._pie, stretch=1)
        chart_box.add_widget(HintLabel("悬停扇区或图例可查看占比；超过 7 种合并为「其它」。"))
        chart_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_lay.addWidget(chart_box, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 0, 0, 0)
        right_lay.setSpacing(10)

        overview = FormSection("目录概览")
        stats = QHBoxLayout()
        stats.setSpacing(8)
        self._stat_files = SemanticLabel("文件 —", kind="info", compact=True)
        self._stat_dirs = SemanticLabel("子目录 —", kind="info", compact=True)
        self._stat_types = SemanticLabel("类型 —", kind="info", compact=True)
        self._stat_empty = SemanticLabel("空目录 —", kind="warning", compact=True)
        self._stat_naming = SemanticLabel("命名问题 —", kind="warning", compact=True)
        for w in (
            self._stat_files,
            self._stat_dirs,
            self._stat_types,
            self._stat_empty,
            self._stat_naming,
        ):
            stats.addWidget(w)
        stats.addStretch(1)
        overview.add_layout(stats)
        right_lay.addWidget(overview)

        report_box = FormSection("路径清单与问题")
        self._report = ReadOnlyPlainTextEdit()
        self._report.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._report.setMinimumHeight(200)
        self._report.setPlaceholderText("点击「开始透视」后，此处显示相对路径、空目录与命名问题…")
        report_box.add_widget(self._report, stretch=1)
        report_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        right_lay.addWidget(report_box, 1)
        splitter.addWidget(right)

        # 左饼图、右路径；默认饼图侧略宽
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([520, 600])
        outer.addWidget(splitter, 1)

        self.apply_page_focus_policy()
        self._reset_overview()

    def primary_focus_widget(self):
        return self._root

    def _reset_overview(self) -> None:
        self._stat_files.setText("文件 —")
        self._stat_dirs.setText("子目录 —")
        self._stat_types.setText("类型 —")
        self._stat_empty.setText("空目录 —")
        self._stat_naming.setText("命名问题 —")
        self._pie.set_slices([])

    def _update_overview(self, report) -> None:
        self._stat_files.setText(f"文件 {report.file_count}")
        self._stat_dirs.setText(f"子目录 {report.dir_count}")
        self._stat_types.setText(f"类型 {len(report.ext_counts)} 种")
        empty_n = len(report.empty_dirs)
        naming_n = len(report.naming_issues)
        self._stat_empty.setText(f"空目录 {empty_n}")
        self._stat_naming.setText(f"命名问题 {naming_n}")
        for w, kind in (
            (self._stat_empty, "warning" if empty_n else "info"),
            (self._stat_naming, "warning" if naming_n else "info"),
        ):
            w.setProperty("class", f"semantic-{kind}")
            w.setProperty("compact", "true")
            st = w.style()
            if st is not None:
                st.unpolish(w)
                st.polish(w)
        slices = [(ext, n) for ext, n in report.ext_counts.items()]
        self._pie.set_slices(slices)

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
            self._update_overview(report)
            n = len(report.relative_paths())
            types_n = len(report.ext_counts)
            self.report_status(
                f"路径 {n} 条 · 类型 {types_n} 种 · 空目录 {len(report.empty_dirs)}",
                level=StatusLevel.SUCCESS,
            )

        self.run_safe(_run, title="目录透视失败")

    def _on_copy(self) -> None:
        if self._last_report is None:
            show_warning(self, "没有可复制的内容，请先透视。")
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
            show_warning(self, "没有可导出的报告，请先透视。")
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

    def apply_class_context(self, session) -> None:
        root = str(getattr(session, "root_path", "") or "").strip()
        if root:
            self._root.setText(root)
        name = str(getattr(session, "class_name", "") or "").strip()
        self.report_status(
            f"已载入班级「{name}」" if name else "已载入班级目录",
            level=StatusLevel.SUCCESS,
        )

    def on_enter(self) -> None:
        self.report_status("目录透视")
        self.schedule_primary_focus()

    def on_theme_changed(self) -> None:
        self._pie.update()
