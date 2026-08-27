# -*- coding: utf-8 -*-
"""班级日程提醒：事件存储 + 到期扫描（供 job_scheduler 调用）。"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

logger = logging.getLogger("TOA3.schedule_reminder")

EVENTS_JSON = "events.json"
EVENTS_CSV = "events.csv"


@dataclass
class ScheduleEvent:
    id: str
    title: str
    due_at: str  # YYYY-MM-DD HH:MM 或 YYYY-MM-DD
    note: str = ""
    notified: bool = False

    def due_dt(self) -> datetime | None:
        raw = (self.due_at or "").strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None


def _data_dir() -> Path:
    return module_data_dir("schedule_reminder", create=True)


def events_path() -> Path:
    return _data_dir() / EVENTS_JSON


def load_events() -> list[ScheduleEvent]:
    path = events_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items: list[ScheduleEvent] = []
            for row in raw if isinstance(raw, list) else []:
                if not isinstance(row, dict):
                    continue
                items.append(
                    ScheduleEvent(
                        id=str(row.get("id") or ""),
                        title=str(row.get("title") or ""),
                        due_at=str(row.get("due_at") or ""),
                        note=str(row.get("note") or ""),
                        notified=bool(row.get("notified", False)),
                    )
                )
            return [e for e in items if e.id]
        except Exception:
            logger.exception("加载日程 JSON 失败")

    # CSV 回退
    csv_path = _data_dir() / EVENTS_CSV
    if csv_path.is_file():
        return _load_csv(csv_path)
    return []


def _load_csv(path: Path) -> list[ScheduleEvent]:
    items: list[ScheduleEvent] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            items.append(
                ScheduleEvent(
                    id=str(row.get("id") or f"csv-{i}"),
                    title=str(row.get("title") or ""),
                    due_at=str(row.get("due_at") or row.get("due") or ""),
                    note=str(row.get("note") or ""),
                    notified=str(row.get("notified") or "").lower() in {"1", "true", "yes"},
                )
            )
    return items


def save_events(events: list[ScheduleEvent]) -> Path:
    path = events_path()
    data = [asdict(e) for e in events]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def add_event(title: str, due_at: str, note: str = "") -> ScheduleEvent:
    import uuid

    events = load_events()
    ev = ScheduleEvent(
        id=uuid.uuid4().hex[:10],
        title=title.strip(),
        due_at=due_at.strip(),
        note=note.strip(),
    )
    events.append(ev)
    save_events(events)
    return ev


def update_event(event_id: str, **kwargs: Any) -> ScheduleEvent | None:
    events = load_events()
    for ev in events:
        if ev.id == event_id:
            for k, v in kwargs.items():
                if hasattr(ev, k) and k != "id":
                    setattr(ev, k, v)
            save_events(events)
            return ev
    return None


def delete_event(event_id: str) -> bool:
    events = load_events()
    nxt = [e for e in events if e.id != event_id]
    if len(nxt) == len(events):
        return False
    save_events(nxt)
    return True


def scan_due_events(*, now: datetime | None = None, mark_notified: bool = True) -> int:
    """
    扫描已到期且未通知的事件。
    供 job_scheduler action `schedule_reminder_scan` 调用。
    返回到期条数。
    """
    now = now or datetime.now()
    events = load_events()
    due: list[ScheduleEvent] = []
    for ev in events:
        dt = ev.due_dt()
        if dt is None:
            continue
        if dt <= now and not ev.notified:
            due.append(ev)
            if mark_notified:
                ev.notified = True

    if mark_notified and due:
        save_events(events)

    if due:
        try:
            from services.notify_bus import NotifyLevel, notify

            titles = "、".join(e.title for e in due[:5])
            more = f" 等 {len(due)} 项" if len(due) > 5 else f" · 共 {len(due)} 项"
            notify(NotifyLevel.WARNING, body=f"日程到期：{titles}{more}")
        except Exception:
            logger.info("due events: %s", [e.title for e in due])

    return len(due)
