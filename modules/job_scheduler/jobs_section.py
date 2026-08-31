# -*- coding: utf-8 -*-
"""定时任务列表与编辑（原系统设置「任务与通知」页签）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from modules.job_scheduler.job_edit_dialog import JobEditDialog
from services.job_scheduler import JobSpec, get_scheduler
from services.job_task_catalog import interval_label, job_summary, task_type_label
from widgets import DangerButton, DataTable, FormSection, HintLabel, PrimaryButton, SecondaryButton
from widgets.list_edit import confirm_delete


class JobsSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("定时任务")
        self._page = parent
        self._sched = get_scheduler()
        self._jobs: list[JobSpec] = []

        self.add_widget(
            HintLabel(
                "怎么用：① 点「新增」选类型/通道/时间 → ②「立即执行」试跑 "
                "→ ③ 侧栏「通知」看留档（提示类仅当前会话）。"
                "邮件收件人在 系统设置 → 能力接入 配置。"
            )
        )

        self._table = DataTable()
        self._table.set_headers(["状态", "名称", "类型", "内容摘要", "间隔", "上次运行", "结果"])
        self._table.setMinimumHeight(300)
        self._table.itemDoubleClicked.connect(self._on_edit)
        self.add_widget(self._table, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        btn_add = PrimaryButton("新增")
        btn_add.clicked.connect(self._on_add)
        bar.addWidget(btn_add)
        btn_edit = SecondaryButton("编辑")
        btn_edit.clicked.connect(self._on_edit)
        bar.addWidget(btn_edit)
        btn_del = DangerButton("删除")
        btn_del.clicked.connect(self._on_delete)
        bar.addWidget(btn_del)
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(self._reload)
        bar.addWidget(btn_refresh)
        bar.addSpacing(16)
        self._btn_run = PrimaryButton("立即执行")
        self._btn_run.clicked.connect(self._on_run)
        bar.addWidget(self._btn_run)
        btn_toggle = SecondaryButton("启用/停用")
        btn_toggle.clicked.connect(self._on_toggle)
        bar.addWidget(btn_toggle)
        bar.addStretch(1)
        self.add_layout(bar)
        self._reload()

    def primary_focus_widget(self):
        return self._table

    def reload(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._jobs = self._sched.list_jobs()
        self._table.setRowCount(len(self._jobs))
        for row, job in enumerate(self._jobs):
            state = "启用" if job.enabled else "停用"
            kind = task_type_label(job.action)
            summary = job_summary(job.action, job.params)
            interval = interval_label(job.interval_seconds)
            last = job.last_run or "—"
            result = job.last_result or "—"
            values = (state, job.name, kind, summary, interval, last, result)
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job.id)
                self._table.setItem(row, col, item)
        if self._jobs:
            self._table.selectRow(0)
        self._page.report_status(f"定时任务 {len(self._jobs)} 条")

    def _current(self) -> JobSpec | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._jobs):
            return self._jobs[row]
        return None

    def _on_add(self) -> None:
        dlg = JobEditDialog(self._page)
        if dlg.exec() != dlg.DialogCode.Accepted or not dlg.payload:
            return
        p = dlg.payload
        self._sched.add_job(
            p["name"],
            p["action"],
            interval_seconds=int(p["interval_seconds"]),
            enabled=bool(p.get("enabled", True)),
            params=dict(p.get("params") or {}),
        )
        self._reload()

    def _on_edit(self) -> None:
        job = self._current()
        if not job:
            show_warning(self._page, "请先选择任务。")
            return
        dlg = JobEditDialog(self._page, job=job)
        if dlg.exec() != dlg.DialogCode.Accepted or not dlg.payload:
            return
        p = dlg.payload
        self._sched.update_job(
            job.id,
            name=p["name"],
            action=p["action"],
            interval_seconds=int(p["interval_seconds"]),
            enabled=bool(p.get("enabled", True)),
            params=dict(p.get("params") or {}),
        )
        self._reload()

    def _on_delete(self) -> None:
        job = self._current()
        if not job:
            return
        if not confirm_delete(self._page, job.name):
            return
        self._sched.remove_job(job.id)
        self._reload()

    def _on_run(self) -> None:
        job = self._current()
        if not job:
            show_warning(self._page, "请先选择任务。")
            return
        result = self._sched.run_now(job.id)
        show_info(self._page, f"执行结果：{result}")
        self._reload()
        self._page.report_status(f"已执行 {job.name}", level=StatusLevel.SUCCESS)

    def _on_toggle(self) -> None:
        job = self._current()
        if not job:
            return
        self._sched.update_job(job.id, enabled=not job.enabled)
        self._reload()
