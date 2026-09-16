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

# 动作导向短名（看板标题）；完整语义见 QUADRANT_HINTS
QUADRANT_LABELS: dict[str, str] = {
    "important_urgent": "Ⅰ 立刻做",
    "important_not_urgent": "Ⅱ 计划做",
    "not_important_urgent": "Ⅲ 速办/委派",
    "not_important_not_urgent": "Ⅳ 可延后",
}

QUADRANT_HINTS: dict[str, str] = {
    "important_urgent": "重要且紧急 · 当天优先处理",
    "important_not_urgent": "重要不紧急 · 排进计划投入",
    "not_important_urgent": "紧急不重要 · 尽快办完或委派",
    "not_important_not_urgent": "不重要不紧急 · 少做或删掉",
}

QUADRANT_SHORT: dict[str, str] = {
    "important_urgent": "Ⅰ",
    "important_not_urgent": "Ⅱ",
    "not_important_urgent": "Ⅲ",
    "not_important_not_urgent": "Ⅳ",
}

# 优先级语义色（与进度三色互不撞车）
# 红立刻 · 紫计划 · 青速办 · 灰延后 —— 不用蓝/橙/绿（留给进度）
QUADRANT_KINDS: dict[str, str] = {
    "important_urgent": "danger",
    "important_not_urgent": "violet",
    "not_important_urgent": "cyan",
    "not_important_not_urgent": "muted",
}

# 日历色点回退（优先读主题 palette 同名键 danger/violet/cyan/muted）
QUADRANT_BAR_COLORS: dict[str, str] = {
    "important_urgent": "#B91C1C",
    "important_not_urgent": "#6D28D9",
    "not_important_urgent": "#0E7490",
    "not_important_not_urgent": "#475569",
}

QUADRANT_PALETTE_KEYS: dict[str, str] = {
    "important_urgent": "danger",
    "important_not_urgent": "violet",
    "not_important_urgent": "cyan",
    "not_important_not_urgent": "muted",
}

# 进度状态（任务看板按状态追踪）
STATUS_IDS = ("todo", "doing", "done")

STATUS_LABELS: dict[str, str] = {
    "todo": "待办",
    "doing": "进行中",
    "done": "已完成",
}

STATUS_HEADERS: dict[str, str] = {
    "todo": "① 待办",
    "doing": "② 进行中",
    "done": "③ 已完成",
}

STATUS_HINTS: dict[str, str] = {
    "todo": "还没开始 · 拖到「进行中」即开工",
    "doing": "正在推进 · 做完拖到「已完成」",
    "done": "已经做完 · 勾选也会进这里",
}

STATUS_SUBTITLES: dict[str, str] = {
    "todo": "",
    "doing": "",
    "done": "",
}

# 进度只用蓝/橙/绿 —— 不用红/紫/青/灰（留给优先级）
STATUS_KINDS: dict[str, str] = {
    "todo": "info",
    "doing": "warning",
    "done": "success",
}

STATUS_BAR_COLORS: dict[str, str] = {
    "todo": "#2563EB",
    "doing": "#B45309",
    "done": "#15803D",
}

STATUS_PALETTE_KEYS: dict[str, str] = {
    "todo": "info",
    "doing": "warning",
    "done": "success",
}

COLOR_LEGEND = "看板/日历：条与列头=进度（蓝橙绿）　｜　优先级视图：列头=优先级（红紫青灰）　｜　行内ⅠⅡⅢⅣ仅文字　｜　右键送记事本"


def _theme_palette() -> dict[str, Any]:
    try:
        from app.app_state import AppState

        return dict(AppState.get().palette or {})
    except Exception:
        return {}


def resolve_status_color(status: str) -> str:
    """进度色：主题 palette → 回退常量。"""
    st = normalize_status(status)
    key = STATUS_PALETTE_KEYS.get(st, "info")
    hex_c = str(_theme_palette().get(key) or "").strip()
    return hex_c or STATUS_BAR_COLORS.get(st, STATUS_BAR_COLORS["todo"])


def resolve_quadrant_color(quadrant: str) -> str:
    """优先级色：主题 palette → 回退常量。"""
    q = normalize_quadrant(quadrant)
    key = QUADRANT_PALETTE_KEYS.get(q, "muted")
    hex_c = str(_theme_palette().get(key) or "").strip()
    return hex_c or QUADRANT_BAR_COLORS.get(q, QUADRANT_BAR_COLORS["not_important_not_urgent"])


_STATUS_ALIASES = {
    "todo": "todo",
    "doing": "doing",
    "done": "done",
    "待办": "todo",
    "进行中": "doing",
    "已完成": "done",
    "in_progress": "doing",
    "wip": "doing",
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


def normalize_status(value: str | None, *, done: bool | None = None) -> str:
    key = str(value or "").strip().lower()
    if key in _STATUS_ALIASES:
        return _STATUS_ALIASES[key]
    if done is True:
        return "done"
    return "todo"


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
    description = str(raw.get("description") or raw.get("notes") or "").strip()
    done_flag = bool(raw.get("done"))
    status = normalize_status(str(raw.get("status") or ""), done=done_flag)
    done = status == "done"
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:12]),
        "title": title,
        "description": description,
        "quadrant": normalize_quadrant(str(raw.get("quadrant") or Q1)),
        "status": status,
        "start": start,
        "due": due,
        "done": done,
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


def tasks_in_status(status: str) -> list[dict[str, Any]]:
    st = normalize_status(status)
    return [t for t in load_tasks() if normalize_status(str(t.get("status") or ""), done=bool(t.get("done"))) == st]


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
    description: str = "",
    done: bool = False,
    status: str | None = None,
) -> dict[str, Any]:
    tasks = load_tasks()
    stamp = _now()
    st = normalize_status(status, done=done)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "title": (title or "").strip() or "无标题",
        "description": (description or "").strip(),
        "quadrant": normalize_quadrant(quadrant),
        "status": st,
        "start": (start or "").strip(),
        "due": (due or "").strip(),
        "done": st == "done",
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
    description: str | None = None,
    quadrant: str | None = None,
    due: str | None = None,
    start: str | None = None,
    done: bool | None = None,
    status: str | None = None,
) -> bool:
    tasks = load_tasks()
    for t in tasks:
        if t.get("id") != task_id:
            continue
        if title is not None:
            t["title"] = (title or "").strip() or "无标题"
        if description is not None:
            t["description"] = (description or "").strip()
        if quadrant is not None:
            t["quadrant"] = normalize_quadrant(quadrant)
        if due is not None:
            t["due"] = (due or "").strip()
        if start is not None:
            t["start"] = (start or "").strip()
        if status is not None:
            st = normalize_status(status)
            t["status"] = st
            t["done"] = st == "done"
        elif done is not None:
            t["done"] = bool(done)
            if done:
                t["status"] = "done"
            elif normalize_status(str(t.get("status") or "")) == "done":
                t["status"] = "todo"
        t["updated"] = _now()
        save_tasks(tasks)
        return True
    return False


def move_task(task_id: str, quadrant: str) -> bool:
    return update_task(task_id, quadrant=quadrant)


def set_task_status(task_id: str, status: str) -> bool:
    return update_task(task_id, status=status)


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


def format_note_handoff(task: dict[str, Any]) -> tuple[str, str]:
    """送入记事本：标题 + 正文（说明/象限/状态/日期）。"""
    title = str(task.get("title") or "任务").strip() or "任务"
    lines: list[str] = []
    desc = str(task.get("description") or "").strip()
    if desc:
        lines.append(desc)
        lines.append("")
    q = normalize_quadrant(str(task.get("quadrant") or Q1))
    st = normalize_status(str(task.get("status") or ""), done=bool(task.get("done")))
    lines.append(f"优先级：{QUADRANT_LABELS.get(q, q)}（{QUADRANT_HINTS.get(q, '')}）")
    lines.append(f"状态：{STATUS_LABELS.get(st, st)}")
    start = str(task.get("start") or "").strip()
    due = str(task.get("due") or "").strip()
    if start or due:
        if start and due and start != due:
            lines.append(f"日程：{start} → {due}")
        else:
            lines.append(f"日程：{due or start}")
    lines.append("")
    lines.append("（来自任务管理）")
    return f"任务 · {title}", "\n".join(lines).strip()


def count_overdue(*, today: date | None = None) -> int:
    day = today or date.today()
    return sum(1 for t in load_tasks() if is_overdue(t, today=day))
