# -*- coding: utf-8 -*-
"""排程格式转换（对标 TOA2：排期↔教学计划）。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.schedule_format_converter.schedule_format_converter_service import (
    convert_schedule_to_teaching_plan,
    generate_schedule_from_teaching_plan,
)
from widgets import (
    ComboBox,
    DataTable,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    TabWidget,
)


class ScheduleFormatConverterPage(BasePage):
    page_id = "schedule_format_converter"
    page_title = "排程格式转换"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "排程格式转换",
                "支持：①开班信息确认表（扁平明细）②合并单元格排期表 → 教学计划；亦可反向生成排期。",
            )
        )

        self._tabs = TabWidget()
        scroll.add_widget(self._tabs)
        self._build_forward_tab()
        self._build_reverse_tab()

        out = FormSection("结果 / 日志")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(120)
        out.add_widget(self._log)
        scroll.add_widget(out)
        scroll.add_stretch(1)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._src

    def _build_forward_tab(self) -> None:
        tab = QWidget()
        lay = QVBoxLayout(tab)

        box = FormSection("排期 → 教学计划")
        row = QHBoxLayout()
        self._src = LineEdit()
        self._src.setPlaceholderText("选择排期 Excel 或开班信息确认表…")
        row.addWidget(self._src, 1)
        btn = SecondaryButton("浏览…")
        btn.clicked.connect(self._browse_forward)
        row.addWidget(btn)
        box.add_layout(row)

        ym = QHBoxLayout()
        ym.addWidget(HintLabel("年份"))
        self._year = ComboBox()
        now = datetime.now()
        for y in (now.year - 1, now.year, now.year + 1):
            self._year.addItem(str(y), y)
        self._year.setCurrentIndex(1)
        ym.addWidget(self._year)

        ym.addWidget(HintLabel("月份"))
        self._month = ComboBox()
        for m in range(1, 13):
            self._month.addItem(f"{m:02d}", m)
        self._month.setCurrentIndex(now.month - 1)
        ym.addWidget(self._month)
        ym.addStretch(1)
        box.add_layout(ym)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("转换为教学计划")
        btn_go.clicked.connect(self._on_forward)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        box.add_layout(actions)
        box.add_widget(
            HintLabel(
                "开班信息确认表选「开班信息」汇总即可；年月按开始日期过滤。输出写入本模块 output。"
            )
        )
        lay.addWidget(box)

        stats = FormSection("课程识别统计")
        self._stats = ReadOnlyPlainTextEdit()
        self._stats.setMaximumHeight(72)
        stats.add_widget(self._stats)
        lay.addWidget(stats)

        preview = FormSection("课程详情预览")
        self._details = DataTable(0, 0)
        self._details.set_headers(
            ["原课程名", "城市", "开始", "结束", "天数", "课程名", "项目归属"]
        )
        self._details.setMinimumHeight(180)
        preview.add_widget(self._details)
        lay.addWidget(preview)
        lay.addStretch(1)

        self._tabs.addTab(tab, "排期 → 教学计划")

    def _build_reverse_tab(self) -> None:
        tab = QWidget()
        lay = QVBoxLayout(tab)

        box = FormSection("教学计划 → 排期")
        row = QHBoxLayout()
        self._rev_src = LineEdit()
        self._rev_src.setPlaceholderText("选择教学计划 Excel（含「课程详情」表）…")
        row.addWidget(self._rev_src, 1)
        btn = SecondaryButton("浏览…")
        btn.clicked.connect(self._browse_reverse)
        row.addWidget(btn)
        box.add_layout(row)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("生成排期")
        btn_go.clicked.connect(self._on_reverse)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        box.add_layout(actions)
        box.add_widget(
            HintLabel("根据教学计划生成标准排期格式，并自动校验与原计划一致性。")
        )
        lay.addWidget(box)
        lay.addStretch(1)

        self._tabs.addTab(tab, "教学计划 → 排期")

    def _browse_forward(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择排期 / 开班信息确认表",
            "",
            "Excel (*.xlsx *.xls);;所有文件 (*.*)",
        )
        if path:
            self._src.setText(path)
            self._maybe_sync_year_month(path)

    def _maybe_sync_year_month(self, path: str) -> None:
        """开班信息确认表：根据首条开始日期对齐年月下拉。"""
        try:
            from pathlib import Path

            import pandas as pd

            from modules.schedule_format_converter.schedule_format_converter_service import (
                _parse_date,
                detect_open_class_confirm_sheet,
            )

            p = Path(path)
            sheet = detect_open_class_confirm_sheet(p)
            if not sheet:
                return
            df = pd.read_excel(p, sheet_name=sheet, dtype=object)
            if df.empty or "开始日期" not in df.columns:
                return
            for val in df["开始日期"].tolist():
                d = _parse_date(val)
                if d is None:
                    continue
                yi = self._year.findData(d.year)
                if yi >= 0:
                    self._year.setCurrentIndex(yi)
                mi = self._month.findData(d.month)
                if mi >= 0:
                    self._month.setCurrentIndex(mi)
                break
        except Exception:
            return

    def _browse_reverse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择教学计划文件",
            "",
            "Excel (*.xlsx *.xls);;所有文件 (*.*)",
        )
        if path:
            self._rev_src.setText(path)

    def _on_forward(self) -> None:
        src = self._src.text().strip()
        if not src:
            show_warning(self, "请先选择排期文件。")
            return
        year = int(self._year.currentData())
        month = int(self._month.currentData())

        def _run() -> None:
            result = convert_schedule_to_teaching_plan(src, year, month)
            self._fill_preview(result.schedule_data, result.course_stats)
            self._log.setPlainText(result.message)
            if not result.ok:
                show_warning(self, result.message)
                self.report_status("转换失败", level=StatusLevel.WARNING)
                return
            self.report_status("教学计划已导出", level=StatusLevel.SUCCESS)
            show_saved(self, result.message, result.output_path)

        self.run_safe(_run, title="转换失败")

    def _on_reverse(self) -> None:
        src = self._rev_src.text().strip()
        if not src:
            show_warning(self, "请先选择教学计划文件。")
            return

        def _run() -> None:
            result = generate_schedule_from_teaching_plan(src)
            self._log.setPlainText(result.message)
            if not result.ok:
                show_warning(self, result.message)
                self.report_status("生成失败", level=StatusLevel.WARNING)
                return
            self.report_status("排期已生成", level=StatusLevel.SUCCESS)
            show_saved(self, result.message, result.output_path)

        self.run_safe(_run, title="生成失败")

    def _fill_preview(self, schedule_data: list, course_stats: dict) -> None:
        stats = course_stats or {}
        lines = [
            f"合计: {stats.get('total', 0)}",
            f"破晓突击: {stats.get('破晓突击课程', 0)}",
            f"利刃出鞘: {stats.get('利刃出鞘课程', 0)}",
        ]
        if "销售顾问课程" in stats:
            lines.append(f"销售顾问: {stats.get('销售顾问课程', 0)}")
        self._stats.setPlainText("  |  ".join(lines))

        rows: list[tuple[str, ...]] = []
        for course in schedule_data or []:
            rows.append(
                (
                    str(course.get("original_course_name") or course.get("course_name") or ""),
                    str(course.get("city") or ""),
                    str(course.get("start_date") or ""),
                    str(course.get("end_date") or ""),
                    str(course.get("course_days") or ""),
                    str(course.get("course_name") or ""),
                    str(course.get("project_belonging") or ""),
                )
            )
        self._details.set_rows(rows)

    def on_enter(self) -> None:
        self.report_status("排程格式转换")
        self.schedule_primary_focus()
