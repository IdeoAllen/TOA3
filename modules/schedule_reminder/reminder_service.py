# -*- coding: utf-8 -*-
"""班级日程提醒（兼容入口；实现已迁至 services.schedule_events）。"""
from __future__ import annotations

from services.schedule_events import (  # noqa: F401
    EVENTS_CSV,
    EVENTS_JSON,
    ScheduleEvent,
    add_event,
    delete_event,
    events_path,
    load_events,
    save_events,
    scan_due_events,
    update_event,
)
