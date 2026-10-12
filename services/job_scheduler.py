# -*- coding: utf-8 -*-
"""轻量定时任务调度（内存 + JSON 落盘）。"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer

from services.storage_paths import module_data_dir

logger = logging.getLogger("TOA3.jobs")

ActionFn = Callable[[dict[str, Any]], None]


@dataclass
class JobSpec:
    id: str
    name: str
    action: str
    interval_seconds: int = 3600
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)
    last_run: str = ""
    last_result: str = ""


class JobScheduler(QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._jobs: dict[str, JobSpec] = {}
        self._timers: dict[str, QTimer] = {}
        self._actions: dict[str, ActionFn] = {}
        self._register_builtin_actions()
        self.load()

    def _path(self) -> Path:
        return module_data_dir("job_scheduler", create=True) / "jobs.json"

    def _register_builtin_actions(self) -> None:
        self.register_action("log_cleanup", self._action_log_cleanup)
        self.register_action("status_ping", self._action_status_ping)
        self.register_action("send_notify", self._action_send_notify)
        self.register_action("open_web", self._action_open_web)
        self.register_action("open_app", self._action_open_app)
        self.register_action("open_module", self._action_open_module)
        self.register_action("schedule_reminder_scan", self._action_schedule_scan)

    def register_action(self, name: str, fn: ActionFn) -> None:
        self._actions[name] = fn

    def list_actions(self) -> list[str]:
        return sorted(self._actions.keys())

    def list_jobs(self) -> list[JobSpec]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> JobSpec | None:
        return self._jobs.get(job_id)

    def add_job(
        self,
        name: str,
        action: str,
        *,
        interval_seconds: int = 3600,
        enabled: bool = True,
        params: dict | None = None,
        job_id: str | None = None,
    ) -> JobSpec:
        jid = job_id or uuid.uuid4().hex[:10]
        spec = JobSpec(
            id=jid,
            name=name,
            action=action,
            interval_seconds=max(30, int(interval_seconds)),
            enabled=enabled,
            params=dict(params or {}),
        )
        self._jobs[jid] = spec
        self._arm(spec)
        self.save()
        return spec

    def update_job(self, job_id: str, **kwargs) -> JobSpec | None:
        spec = self._jobs.get(job_id)
        if not spec:
            return None
        for k, v in kwargs.items():
            if hasattr(spec, k) and k != "id":
                setattr(spec, k, v)
        self._disarm(job_id)
        if spec.enabled:
            self._arm(spec)
        self.save()
        return spec

    def remove_job(self, job_id: str) -> bool:
        self._disarm(job_id)
        if job_id in self._jobs:
            del self._jobs[job_id]
            self.save()
            return True
        return False

    def run_now(self, job_id: str) -> str:
        spec = self._jobs.get(job_id)
        if not spec:
            return "任务不存在"
        return self._execute(spec)

    def start_all(self) -> None:
        for spec in self._jobs.values():
            if spec.enabled:
                self._arm(spec)

    def shutdown(self) -> None:
        for jid in list(self._timers.keys()):
            self._disarm(jid)

    def load(self) -> None:
        path = self._path()
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for row in raw if isinstance(raw, list) else []:
                if not isinstance(row, dict):
                    continue
                spec = JobSpec(
                    id=str(row.get("id") or uuid.uuid4().hex[:10]),
                    name=str(row.get("name") or "任务"),
                    action=str(row.get("action") or "status_ping"),
                    interval_seconds=int(row.get("interval_seconds") or 3600),
                    enabled=bool(row.get("enabled", True)),
                    params=dict(row.get("params") or {}),
                    last_run=str(row.get("last_run") or ""),
                    last_result=str(row.get("last_result") or ""),
                )
                self._jobs[spec.id] = spec
        except Exception:
            logger.exception("加载定时任务失败")

    def save(self) -> None:
        path = self._path()
        data = [asdict(j) for j in self._jobs.values()]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _arm(self, spec: JobSpec) -> None:
        self._disarm(spec.id)
        if not spec.enabled:
            return
        timer = QTimer(self)
        timer.setInterval(max(30, spec.interval_seconds) * 1000)
        timer.timeout.connect(lambda jid=spec.id: self._on_tick(jid))
        timer.start()
        self._timers[spec.id] = timer

    def _disarm(self, job_id: str) -> None:
        t = self._timers.pop(job_id, None)
        if t is not None:
            t.stop()
            t.deleteLater()

    def _on_tick(self, job_id: str) -> None:
        spec = self._jobs.get(job_id)
        if spec and spec.enabled:
            self._execute(spec)

    def _execute(self, spec: JobSpec) -> str:
        fn = self._actions.get(spec.action)
        result = "ok"
        payload = dict(spec.params or {})
        payload["_job_id"] = spec.id
        payload["_job_name"] = spec.name
        try:
            if fn is None:
                result = f"未知动作: {spec.action}"
            else:
                fn(payload)
                result = "ok"
        except Exception as e:
            logger.exception("任务执行失败 %s", spec.id)
            result = f"error: {e}"
        spec.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        spec.last_result = result
        self.save()
        try:
            from services.notify_archive import append_record

            append_record(
                notice_kind="record",
                channel="task",
                title=spec.name,
                body=result,
                level="success" if result == "ok" else "error",
                source=f"job:{spec.id}",
                extra={"action": spec.action},
            )
        except Exception:
            pass
        try:
            from services.notify_bus import get_bus

            get_bus().job_progress.emit(spec.id, f"{spec.name}: {result}")
        except Exception:
            pass
        return result

    def _action_log_cleanup(self, params: dict) -> None:
        from services.system_info import log_directory

        days = int(params.get("keep_days") or 7)
        cutoff = time.time() - days * 86400
        log_dir = log_directory()
        if not log_dir.is_dir():
            return
        for p in log_dir.glob("*.log*"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
            except OSError:
                pass

    def _action_status_ping(self, params: dict) -> None:
        self._action_send_notify(
            {
                "channel": params.get("channel") or "status",
                "title": params.get("title") or "",
                "body": params.get("message") or params.get("body") or "定时心跳",
                "level": params.get("level") or "info",
                "notice_kind": params.get("notice_kind") or "prompt",
                "_job_id": params.get("_job_id"),
                "_job_name": params.get("_job_name"),
            }
        )

    def _action_send_notify(self, params: dict) -> None:
        from services.notify_bus import NotifyLevel, notify

        level_raw = str(params.get("level") or "info").strip().lower()
        level_map = {
            "info": NotifyLevel.INFO,
            "warning": NotifyLevel.WARNING,
            "error": NotifyLevel.ERROR,
        }
        level = level_map.get(level_raw, NotifyLevel.INFO)
        channel = str(params.get("channel") or "status").strip().lower()
        notice_kind = str(params.get("notice_kind") or "prompt").strip().lower()
        title = str(params.get("title") or "定时任务").strip()
        body = str(params.get("body") or params.get("message") or "").strip()
        job_id = str(params.get("_job_id") or "").strip()
        job_name = str(params.get("_job_name") or "").strip()
        source = f"job:{job_id}" if job_id else ""
        if job_name and not title:
            title = job_name
        notify(
            level,
            title=title,
            body=body or title,
            channel=channel,
            notice_kind=notice_kind,
            source=source,
        )

    def _action_open_web(self, params: dict) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        url = str(params.get("url") or "").strip()
        if not url:
            raise ValueError("未配置网页地址")
        if "://" not in url:
            url = f"https://{url}"
        if not QDesktopServices.openUrl(QUrl(url)):
            raise RuntimeError(f"无法打开：{url}")

    def _action_open_app(self, params: dict) -> None:
        from services.os_open import open_path

        path = str(params.get("path") or "").strip()
        if not path:
            raise ValueError("未配置应用路径")
        if not open_path(path):
            raise RuntimeError(f"无法打开：{path}")

    def _action_open_module(self, params: dict) -> None:
        mid = str(params.get("module_id") or "").strip()
        if not mid:
            return
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for w in app.topLevelWidgets():
            if hasattr(w, "navigate"):
                w.navigate(mid)
                break

    def _action_schedule_scan(self, params: dict) -> None:
        try:
            from services.schedule_reminder_scan import scan_due_events

            n = scan_due_events()
            from services.notify_bus import NotifyLevel, notify

            notify(NotifyLevel.INFO, body=f"日程扫描完成，到期 {n} 项")
        except Exception as e:
            logger.info("schedule scan skip: %s", e)


_SCHEDULER: JobScheduler | None = None


def get_scheduler() -> JobScheduler:
    global _SCHEDULER
    if _SCHEDULER is None:
        _SCHEDULER = JobScheduler()
    return _SCHEDULER
