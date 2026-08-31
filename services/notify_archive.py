# -*- coding: utf-8 -*-
"""通知留档：信息类 / 邮件 / 任务执行 — 落盘可追溯（提示类仅会话内）。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

logger = logging.getLogger("TOA3.notify.archive")

_ARCHIVE_MAX = 500


def _archive_path() -> Path:
    return module_data_dir("notifications", create=True) / "records.jsonl"


def email_config_summary() -> dict[str, Any]:
    """邮件通道配置摘要（供任务/通知页展示）。"""
    try:
        from services.integrations.config import integration_config, integration_enabled
    except Exception:
        return {"enabled": False, "recipient": "", "sender": "", "ready": False, "hint": "无法读取 integrations 配置"}

    enabled = integration_enabled("email")
    cfg = integration_config("email") or {}
    recipient = str(cfg.get("recipient_email") or "").strip()
    sender = str(cfg.get("sender_email") or "").strip()
    host = str(cfg.get("smtp_server") or "").strip()
    ready = bool(enabled and host and sender and recipient)
    if not enabled:
        hint = "未启用：系统设置 → 能力接入 → 邮件"
    elif not recipient:
        hint = "未填收件人：系统设置 → 能力接入 → 填写 recipient_email"
    elif not host or not sender:
        hint = "SMTP 未配齐：系统设置 → 能力接入"
    else:
        hint = f"发件 {sender} → 收件 {recipient}"
    return {
        "enabled": enabled,
        "recipient": recipient,
        "sender": sender,
        "ready": ready,
        "hint": hint,
    }


def email_delivery_preview(title: str, body: str) -> str:
    """用户可见：邮件对方收到什么。"""
    info = email_config_summary()
    subj = (title or "TOA 通知").strip()
    text = (body or title or "").strip()
    if info.get("recipient"):
        to = info["recipient"]
    else:
        to = "（未配置收件人）"
    return f"主题：{subj}\n正文：{text or '（空）'}（纯文本）\n收件：{to}"


def append_record(
    *,
    notice_kind: str,
    channel: str,
    title: str = "",
    body: str = "",
    level: str = "info",
    source: str = "",
    email_to: str = "",
    email_ok: bool | None = None,
    extra: dict | None = None,
) -> None:
    """写入留档（信息类 / 邮件 / 任务执行）。"""
    row = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "notice_kind": str(notice_kind or "record"),
        "channel": str(channel or ""),
        "level": str(level or "info"),
        "title": str(title or ""),
        "body": str(body or ""),
        "source": str(source or ""),
        "email_to": str(email_to or ""),
    }
    if email_ok is not None:
        row["email_ok"] = bool(email_ok)
    if extra:
        row.update({k: v for k, v in extra.items() if k not in row})
    path = _archive_path()
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        _trim_archive(path)
    except Exception:
        logger.debug("append notify record failed", exc_info=True)


def list_records(*, limit: int = 80, notice_kind: str | None = None) -> list[dict[str, Any]]:
    path = _archive_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if notice_kind and str(row.get("notice_kind") or "") != notice_kind:
                continue
            rows.append(row)
    except Exception:
        logger.debug("read notify records failed", exc_info=True)
        return []
    rows.reverse()
    n = max(0, int(limit or 0))
    return rows[:n] if n else rows


def format_record_line(row: dict[str, Any]) -> str:
    ts = str(row.get("ts") or "—")
    ch = str(row.get("channel") or "?")
    title = str(row.get("title") or "")
    body = str(row.get("body") or "")
    src = str(row.get("source") or "")
    email_to = str(row.get("email_to") or "")
    email_ok = row.get("email_ok")
    head = f"{ts} · [{ch}] {title}".strip()
    if body and body != title:
        head = f"{head} — {body}"
    if src:
        head = f"{head} ← {src}"
    if email_to:
        flag = "✓" if email_ok else ("✗" if email_ok is False else "?")
        head = f"{head} · 邮件→{email_to} {flag}"
    return head


def _trim_archive(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _ARCHIVE_MAX:
            return
        keep = lines[-_ARCHIVE_MAX :]
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except Exception:
        pass
