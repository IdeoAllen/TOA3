# -*- coding: utf-8 -*-
"""系统 · 任务：定时任务管理（原设置页「任务与通知」中的任务半边）。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.base_page import BasePage
from core.ui_spec import page_content_margins
from modules.job_scheduler.jobs_section import JobsSection
from widgets import PageHeader


class JobSchedulerPage(BasePage):
    page_id = "job_scheduler"
    page_title = "定时任务"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(12)

        outer.addWidget(
            PageHeader(
                "任务",
                "按间隔执行；通知分「提示/留档」，邮件与执行结果在「通知」页可查。",
            )
        )
        self._section = JobsSection(self)
        outer.addWidget(self._section, 1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._section.primary_focus_widget()

    def focus_tab_widgets(self) -> list[QWidget]:
        w = self.primary_focus_widget()
        return [w] if w is not None else []

    def on_enter(self) -> None:
        self._section.reload()
        self.report_status("任务")
