# -*- coding: utf-8 -*-
"""定时任务列表与编辑（原系统设置「任务与通知」页签）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from services.job_scheduler import get_scheduler
from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton
from widgets.list_edit import FormEditDialog, ListPanel, confirm_delete


class JobsSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("定时任务")
        self._page = parent
        self._sched = get_scheduler()

        self.add_widget(
            HintLabel(
                "间隔任务落盘于 data/module/job_scheduler/jobs.json；"
                f"可用动作：{', '.join(self._sched.list_actions())}"
            )
        )

        self._list = ListPanel(
            add_label="新增",
            edit_label="编辑",
            delete_label="删除",
            refresh_label="刷新",
            hint="选中后可「立即执行」。",
        )
        self._list.bind_add(self._on_add)
        self._list.bind_edit(self._on_edit)
        self._list.bind_delete(self._on_delete)
        self._list.bind_refresh(self._reload)
        self.add_widget(self._list)

        row = QHBoxLayout()
        self._btn_run = PrimaryButton("立即执行")
        self._btn_run.clicked.connect(self._on_run)
        row.addWidget(self._btn_run)
        btn_toggle = SecondaryButton("启用/停用")
        btn_toggle.clicked.connect(self._on_toggle)
        row.addWidget(btn_toggle)
        row.addStretch(1)
        self.add_layout(row)
        self._reload()

    def primary_focus_widget(self):
        return self._btn_run

    def reload(self) -> None:
        self._reload()

    def _reload(self) -> None:
        jobs = self._sched.list_jobs()
        lines = []
        for j in jobs:
            state = "开" if j.enabled else "停"
            lines.append(
                f"[{state}] {j.name} · {j.action} · 每{j.interval_seconds}s · "
                f"上次 {j.last_run or '—'} {j.last_result}"
            )
        self._list.set_items(lines)
        self._page.report_status(f"定时任务 {len(jobs)} 条")

    def _current(self):
        row = self._list.current_row()
        jobs = self._sched.list_jobs()
        if 0 <= row < len(jobs):
            return jobs[row]
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
