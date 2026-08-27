# -*- coding: utf-8 -*-
"""四象限任务本地 JSON 存储。"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

QUADRANT_IDS = (
    "important_urgent",
    "important_not_urgent",
    "not_important_urgent",
    "not_important_not_urgent",
)

QUADRANT_LABELS: dict[str, str] = {
    "important_urgent": "I. 重要且紧急",
    "important_not_urgent": "II. 重要不紧急",
    "not_important_urgent": "III. 紧急不重要",
    "not_important_not_urgent": "IV. 不重要不紧急",
}

# 象限标题语义色（SemanticLabel kind）
QUADRANT_KINDS: dict[str, str] = {
    "important_urgent": "danger",
    "important_not_urgent": "warning",
    "not_important_urgent": "success",
    "not_important_not_urgent": "info",
}

# 短别名（UI / 兼容）
Q1, Q2, Q3, Q4 = QUADRANT_IDS
_ALIASES = {
    "q1": Q1,
    "q2": Q2,
    "q3": Q3,
    "q4": Q4,
    Q1: Q1,
    Q2: Q2,
    Q3: Q3,
    Q4: Q4,
}

_STORE: list[dict[str, Any]] | None = None


def normalize_quadrant(value: str | None) -> str:
    key = str(value or "").strip()
    return _ALIASES.get(key, Q1)


def _path() -> Path:
    return module_data_dir("quadrant_tasks", create=True) / "tasks.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalize_task(raw: dict[str, Any]) -> dict[str, Any] | None:
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    due = str(raw.get("due") or "").strip()
    start = str(raw.get("start") or "").strip()
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:12]),
        "title": title,
        "quadrant": normalize_quadrant(str(raw.get("quadrant") or Q1)),
        "start": start,
        "due": due,
        "done": bool(raw.get("done")),
        "created": str(raw.get("created") or _now()),
        "updated": str(raw.get("updated") or _now()),
    }


def load_tasks() -> list[dict[str, Any]]:
    global _STORE
    if _STORE is not None:
        return _STORE
    path = _path()
    if not path.is_file():
        _STORE = []
        return _STORE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _STORE = []
        return _STORE
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, dict):
                t = _normalize_task(x)
                if t:
                    items.append(t)
    _STORE = items
    return _STORE


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    global _STORE
    _STORE = list(tasks)
    path = _path()
    path.write_text(json.dumps(_STORE, ensure_ascii=False, indent=2), encoding="utf-8")


def tasks_in_quadrant(quadrant: str) -> list[dict[str, Any]]:
    q = normalize_quadrant(quadrant)
    return [t for t in load_tasks() if t.get("quadrant") == q]


def find_task(task_id: str) -> dict[str, Any] | None:
    tid = str(task_id or "")
    for t in load_tasks():
        if t.get("id") == tid:
            return t
    return None


def add_task(
    title: str,
    quadrant: str,
    *,
    due: str = "",
    start: str = "",
    done: bool = False,
) -> dict[str, Any]:
    tasks = load_tasks()
    stamp = _now()
    entry = {
        "id": uuid.uuid4().hex[:12],
        "title": (title or "").strip() or "无标题",
        "quadrant": normalize_quadrant(quadrant),
        "start": (start or "").strip(),
        "due": (due or "").strip(),
        "done": bool(done),
        "created": stamp,
        "updated": stamp,
    }
    tasks.insert(0, entry)
    save_tasks(tasks)
    return entry


def update_task(
    task_id: str,
    *,
    title: str | None = None,
    quadrant: str | None = None,
    due: str | None = None,
    start: str | None = None,
    done: bool | None = None,
) -> bool:
    tasks = load_tasks()
    for t in tasks:
        if t.get("id") != task_id:
            continue
        if title is not None:
            t["title"] = (title or "").strip() or "无标题"
        if quadrant is not None:
            t["quadrant"] = normalize_quadrant(quadrant)
        if due is not None:
            t["due"] = (due or "").strip()
        if start is not None:
            t["start"] = (start or "").strip()
        if done is not None:
            t["done"] = bool(done)
        t["updated"] = _now()
        save_tasks(tasks)
        return True
    return False


def move_task(task_id: str, quadrant: str) -> bool:
    return update_task(task_id, quadrant=quadrant)


def delete_task(task_id: str) -> bool:
    tasks = load_tasks()
    new = [t for t in tasks if t.get("id") != task_id]
    if len(new) == len(tasks):
        return False
    save_tasks(new)
    return True


def parse_due(due: str) -> date | None:
    text = (due or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def task_span(task: dict[str, Any]) -> tuple[date, date] | None:
    """任务在日历上的起止日（含跨日）。无日期则 None。"""
    start = parse_due(str(task.get("start") or ""))
    due = parse_due(str(task.get("due") or ""))
    if start is None and due is None:
        return None
    if start is None:
        start = due
    if due is None:
        due = start
    assert start is not None and due is not None
    if due < start:
        start, due = due, start
    return start, due


def task_covers_day(task: dict[str, Any], day: date) -> bool:
    span = task_span(task)
    if span is None:
        return False
    a, b = span
    return a <= day <= b


def is_overdue(task: dict[str, Any], *, today: date | None = None) -> bool:
    return overdue_days(task, today=today) is not None


def overdue_days(task: dict[str, Any], *, today: date | None = None) -> int | None:
    """逾期天数；已完成或无截止/未逾期时返回 None。"""
    if task.get("done"):
        return None
    d = parse_due(str(task.get("due") or ""))
    if d is None:
        return None
    delta = ((today or date.today()) - d).days
    if delta <= 0:
        return None
    return delta


def is_due_today(task: dict[str, Any], *, today: date | None = None) -> bool:
    day = today or date.today()
    return task_covers_day(task, day)


def matches_filter(task: dict[str, Any], mode: str, *, today: date | None = None) -> bool:
    """mode: 'today' | 'all'。今日 = 覆盖今日或已逾期（未完成）。"""
    key = (mode or "all").strip().lower()
    if key == "all":
        return True
    if task.get("done"):
        return False
    day = today or date.today()
    return task_covers_day(task, day) or is_overdue(task, today=day)


def count_overdue(*, today: date | None = None) -> int:
    day = today or date.today()
    return sum(1 for t in load_tasks() if is_overdue(t, today=day))
