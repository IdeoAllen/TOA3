# -*- coding: utf-8 -*-
"""定时任务列表与编辑（原系统设置「任务与通知」页签）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from services.job_scheduler import JobSpec, get_scheduler
from widgets import DangerButton, DataTable, FormSection, HintLabel, PrimaryButton, SecondaryButton
from widgets.list_edit import FormEditDialog, confirm_delete


class JobsSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("定时任务")
        self._page = parent
        self._sched = get_scheduler()
        self._jobs: list[JobSpec] = []

        self.add_widget(HintLabel("任务在本机后台运行；双击行可编辑。"))

        self._table = DataTable()
        self._table.set_headers(["状态", "名称", "动作", "间隔", "上次运行", "结果"])
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
            interval = f"{job.interval_seconds}s"
            last = job.last_run or "—"
            result = job.last_result or "—"
            values = (state, job.name, job.action, interval, last, result)
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
        dlg = FormEditDialog(
            self._page,
            title="新增定时任务",
            fields=[
                ("名称", "name"),
                ("动作", "action"),
                ("间隔秒", "interval_seconds"),
                ("参数 JSON 可选", "params"),
            ],
        )
        dlg.set_values(
            {
                "name": "心跳",
                "action": "status_ping",
                "interval_seconds": "3600",
                "params": "",
            }
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        params = {}
        raw = (v.get("params") or "").strip()
        if raw:
            import json

            try:
                params = json.loads(raw)
            except Exception:
                params = {"message": raw}
        try:
            interval = int(v.get("interval_seconds") or "3600")
        except ValueError:
            interval = 3600
        self._sched.add_job(
            str(v.get("name") or "任务"),
            str(v.get("action") or "status_ping"),
            interval_seconds=interval,
            params=params,
        )
        self._reload()

    def _on_edit(self) -> None:
        job = self._current()
        if not job:
            show_warning(self._page, "请先选择任务。")
            return
        dlg = FormEditDialog(
            self._page,
            title="编辑定时任务",
            fields=[
                ("名称", "name"),
                ("动作", "action"),
                ("间隔秒", "interval_seconds"),
            ],
        )
        dlg.set_values(
            {
                "name": job.name,
                "action": job.action,
                "interval_seconds": str(job.interval_seconds),
            }
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            interval = int(v.get("interval_seconds") or job.interval_seconds)
        except ValueError:
            interval = job.interval_seconds
        self._sched.update_job(
            job.id,
            name=str(v.get("name") or job.name),
            action=str(v.get("action") or job.action),
            interval_seconds=interval,
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
