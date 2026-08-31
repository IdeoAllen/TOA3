# -*- coding: utf-8 -*-
"""定时任务 · 用户口径：任务类型、通知通道、间隔与展示摘要。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from services.job_scheduler import JobSpec

# (action_key, 用户标签)
TASK_TYPES: tuple[tuple[str, str], ...] = (
    ("send_notify", "发送通知"),
    ("open_web", "打开网页"),
    ("open_app", "打开应用"),
    ("open_module", "打开功能模块"),
    ("schedule_reminder_scan", "扫描日程提醒"),
    ("log_cleanup", "清理旧日志"),
)

NOTIFY_CHANNELS: tuple[tuple[str, str], ...] = (
    ("status", "状态栏"),
    ("dialog", "对话框"),
    ("tray", "托盘气泡"),
    ("email", "邮件"),
    ("all", "全部通道"),
)

NOTIFY_LEVELS: tuple[tuple[str, str], ...] = (
    ("info", "信息"),
    ("warning", "警告"),
    ("error", "错误"),
)

NOTICE_KINDS: tuple[tuple[str, str], ...] = (
    ("prompt", "提示（看过即过）"),
    ("record", "留档（写入通知记录）"),
)

INTERVAL_PRESETS: tuple[tuple[int, str], ...] = (
    (300, "每 5 分钟"),
    (900, "每 15 分钟"),
    (1800, "每 30 分钟"),
    (3600, "每 1 小时"),
    (21600, "每 6 小时"),
    (43200, "每 12 小时"),
    (86400, "每 24 小时"),
)

CUSTOM_INTERVAL = -1


@dataclass(frozen=True)
class JobFormData:
    name: str
    action: str
    interval_seconds: int
    params: dict[str, Any]


def task_type_label(action: str) -> str:
    key = _normalize_action(action)
    for aid, label in TASK_TYPES:
        if aid == key:
            return label
    if action == "status_ping":
        return "发送通知"
    return action or "—"


def channel_label(channel: str) -> str:
    c = str(channel or "status").strip().lower()
    for cid, label in NOTIFY_CHANNELS:
        if cid == c:
            return label
    return c or "状态栏"


def interval_label(seconds: int) -> str:
    sec = max(30, int(seconds or 3600))
    for preset, label in INTERVAL_PRESETS:
        if preset == sec:
            return label
    if sec % 86400 == 0:
        return f"每 {sec // 86400} 天"
    if sec % 3600 == 0:
        return f"每 {sec // 3600} 小时"
    if sec % 60 == 0:
        return f"每 {sec // 60} 分钟"
    return f"每 {sec} 秒"


def notice_kind_label(kind: str) -> str:
    k = str(kind or "prompt").strip().lower()
    for kid, label in NOTICE_KINDS:
        if kid == k:
            return label.split("（")[0]
    return "提示" if k == "prompt" else "留档"


def job_summary(action: str, params: dict[str, Any] | None) -> str:
    p = dict(params or {})
    key = _normalize_action(action)
    if key == "send_notify":
        ch = channel_label(str(p.get("channel") or "status"))
        nk = notice_kind_label(str(p.get("notice_kind") or "prompt"))
        body = str(p.get("body") or p.get("message") or "").strip()
        title = str(p.get("title") or "").strip()
        text = title or body or "通知"
        if len(text) > 24:
            text = text[:24] + "…"
        return f"{nk} · {ch} · {text}"
    if key == "open_web":
        url = str(p.get("url") or "").strip()
        if len(url) > 36:
            return url[:36] + "…"
        return url or "—"
    if key == "open_app":
        path = str(p.get("path") or "").strip()
        if not path:
            return "—"
        name = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        return name or path
    if key == "open_module":
        mid = str(p.get("module_id") or "").strip()
        return _module_title(mid) if mid else "—"
    if key == "schedule_reminder_scan":
        return "检查到期日程并提醒"
    if key == "log_cleanup":
        days = int(p.get("keep_days") or 7)
        return f"保留最近 {days} 天日志"
    return "—"


def _normalize_action(action: str) -> str:
    a = str(action or "").strip()
    if a == "status_ping":
        return "send_notify"
    return a


def _module_title(module_id: str) -> str:
    try:
        from services.config_service import get_menu_item_by_id

        item = get_menu_item_by_id(module_id)
        if item:
            return str(item.get("name") or module_id)
    except Exception:
        pass
    return module_id


def navigable_modules() -> list[tuple[str, str]]:
    """(module_id, 展示名) 供下拉选择。"""
    try:
        from services.menu_registry import visible_menu_items

        out: list[tuple[str, str]] = []
        for item in visible_menu_items():
            mid = str(item.get("id") or "").strip()
            if not mid:
                continue
            name = str(item.get("name") or mid).strip()
            out.append((mid, name))
        out.sort(key=lambda x: x[1])
        return out
    except Exception:
        return []


def job_to_form(job: JobSpec) -> dict[str, Any]:
    action = _normalize_action(job.action)
    params = dict(job.params or {})
    if job.action == "status_ping" and "body" not in params:
        params["body"] = params.get("message") or "定时心跳"
        params.setdefault("channel", "status")
        params.setdefault("level", "info")
        params.setdefault("notice_kind", "prompt")
    preset = job.interval_seconds
    custom = preset
    matched = False
    for sec, _ in INTERVAL_PRESETS:
        if sec == preset:
            matched = True
            break
    if not matched:
        preset = CUSTOM_INTERVAL
    return {
        "name": job.name,
        "action": action,
        "interval_preset": preset,
        "interval_custom": custom,
        "params": params,
    }


def build_job_payload(form: dict[str, Any]) -> tuple[bool, str, JobFormData | None]:
    name = str(form.get("name") or "").strip()
    if not name:
        return False, "请填写任务名称。", None

    action = str(form.get("action") or "send_notify").strip()
    params = dict(form.get("params") or {})

    ok, err = _validate_params(action, params)
    if not ok:
        return False, err, None

    preset = int(form.get("interval_preset") or 3600)
    if preset == CUSTOM_INTERVAL:
        try:
            interval = max(30, int(form.get("interval_custom") or 3600))
        except (TypeError, ValueError):
            return False, "自定义间隔请填写不小于 30 的秒数。", None
    else:
        interval = max(30, preset)

    # 兼容旧 action 名
    stored_action = action
    if action == "send_notify":
        stored_action = "send_notify"

    return True, "", JobFormData(name=name, action=stored_action, interval_seconds=interval, params=params)


def _validate_params(action: str, params: dict[str, Any]) -> tuple[bool, str]:
    if action == "send_notify":
        body = str(params.get("body") or params.get("message") or "").strip()
        title = str(params.get("title") or "").strip()
        if not body and not title:
            return False, "请填写通知标题或正文。"
        channel = str(params.get("channel") or "status").strip().lower()
        if channel not in {c for c, _ in NOTIFY_CHANNELS}:
            return False, "请选择有效的通知通道。"
        nk = str(params.get("notice_kind") or "prompt").strip().lower()
        if nk not in {k for k, _ in NOTICE_KINDS}:
            return False, "请选择通知性质。"
        if channel == "email":
            from services.notify_archive import email_config_summary

            if not email_config_summary().get("ready"):
                return False, "邮件未就绪：请先在系统设置 → 能力接入配置 SMTP 与收件人。"
        return True, ""
    if action == "open_web":
        url = str(params.get("url") or "").strip()
        if not url:
            return False, "请填写网页地址。"
        parsed = urlparse(url if "://" in url else f"https://{url}")
        if not parsed.netloc and not parsed.path:
            return False, "网页地址格式不正确。"
        return True, ""
    if action == "open_app":
        path = str(params.get("path") or "").strip()
        if not path:
            return False, "请选择要打开的应用或文件。"
        return True, ""
    if action == "open_module":
        mid = str(params.get("module_id") or "").strip()
        if not mid:
            return False, "请选择要打开的功能模块。"
        return True, ""
    if action == "log_cleanup":
        try:
            days = int(params.get("keep_days") or 7)
        except (TypeError, ValueError):
            return False, "日志保留天数无效。"
        if days < 1:
            return False, "日志保留天数至少为 1。"
        return True, ""
    return True, ""
