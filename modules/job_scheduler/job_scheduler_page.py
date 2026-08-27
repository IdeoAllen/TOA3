# -*- coding: utf-8 -*-
"""系统 · 任务：定时任务管理（原设置页「任务与通知」中的任务半边）。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.base_page import BasePage
from modules.job_scheduler.jobs_section import JobsSection
from widgets import HintLabel, PageHeader, ScrollPage


class JobSchedulerPage(BasePage):
    page_id = "job_scheduler"
    page_title = "任务"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "任务",
                "管理间隔定时任务：日志清理、状态心跳、打开模块、日程扫描等。",
            )
        )
        scroll.add_widget(
            HintLabel(
                "任务在后台由调度器执行；本页可新增、编辑、启用/停用并立即试跑。"
                "通知通道请到侧栏「通知」。"
            )
        )
        self._section = JobsSection(self)
        scroll.add_widget(self._section)
        scroll.add_stretch(1)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._section.primary_focus_widget()

    def focus_tab_widgets(self) -> list[QWidget]:
        w = self.primary_focus_widget()
        return [w] if w is not None else []

    def on_enter(self) -> None:
        self._section.reload()
        self.report_status("任务")
