# -*- coding: utf-8 -*-
"""日程到期扫描（services 入口；实现见 schedule_events）。"""
from __future__ import annotations

from datetime import datetime

from services.schedule_events import scan_due_events as _scan


def scan_due_events(*, now: datetime | None = None, mark_notified: bool = True) -> int:
    return _scan(now=now, mark_notified=mark_notified)
