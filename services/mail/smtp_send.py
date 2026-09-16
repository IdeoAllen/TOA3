# -*- coding: utf-8 -*-
"""SMTP 发信（纯文本优先 · 附件上限与进度）。"""
from __future__ import annotations

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

from services.mail.diagnose import diagnose_mail_error

# 单附件上限（字节）；含 Base64 膨胀，对用户按原始文件计
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
# 全部附件合计
MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024

ProgressCb = Callable[[str, int, int], None]


def validate_attachments(paths: list[str | Path]) -> tuple[bool, str, list[Path]]:
    files: list[Path] = []
    total = 0
    for raw in paths or []:
        p = Path(raw)
        if not p.is_file():
            return False, f"附件不存在：{p}", []
        size = p.stat().st_size
        if size > MAX_ATTACHMENT_BYTES:
            return False, f"附件超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB 上限：{p.name}", []
        total += size
        files.append(p)
    if total > MAX_TOTAL_ATTACHMENT_BYTES:
        return False, f"附件合计超过 {MAX_TOTAL_ATTACHMENT_BYTES // (1024 * 1024)}MB 上限", []
    return True, "", files


def build_message(
    *,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    body_text: str,
    cc_addrs: list[str] | None = None,
    attachment_paths: list[Path] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(a for a in to_addrs if a)
    if cc_addrs:
        msg["Cc"] = ", ".join(a for a in cc_addrs if a)
    msg["Subject"] = subject or "(无主题)"
    # 纯文本优先
    msg.set_content(body_text or "", subtype="plain", charset="utf-8")

    for path in attachment_paths or []:
        ctype, _ = mimetypes.guess_type(str(path))
        if not ctype:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        data = path.read_bytes()
        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    return msg


def send_mail(
    account: dict[str, Any],
    password: str,
    *,
    to_addrs: list[str],
    subject: str,
    body_text: str,
    cc_addrs: list[str] | None = None,
    attachment_paths: list[str | Path] | None = None,
    progress: ProgressCb | None = None,
) -> tuple[bool, dict[str, Any]]:
    provider_id = str(account.get("provider_id") or "custom")
    from_addr = str(account.get("email") or "").strip()
    ok, err, files = validate_attachments(list(attachment_paths or []))
    if not ok:
        return False, diagnose_mail_error(err, provider_id=provider_id, phase="attach")

    recipients = [a.strip() for a in (to_addrs or []) if str(a).strip()]
    if not from_addr or not recipients:
        return False, diagnose_mail_error(
            "收件人或发件人为空", provider_id=provider_id, phase="compose"
        )

    if progress:
        progress("准备邮件…", 0, 100)
    msg = build_message(
        from_addr=from_addr,
        to_addrs=recipients,
        subject=subject,
        body_text=body_text,
        cc_addrs=cc_addrs,
        attachment_paths=files,
    )
    all_rcpt = recipients + [a.strip() for a in (cc_addrs or []) if str(a).strip()]

    host = str(account.get("smtp_host") or "").strip()
    port = int(account.get("smtp_port") or 465)
    use_ssl = bool(account.get("smtp_ssl", True))
    use_starttls = bool(account.get("smtp_starttls", False))
    if not host:
        return False, diagnose_mail_error("SMTP 主机为空", provider_id=provider_id, phase="smtp")

    try:
        if progress:
            progress("连接 SMTP…", 10, 100)
        ctx = ssl.create_default_context()
        if use_ssl and not use_starttls:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=60, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=60)
            if use_starttls or (not use_ssl):
                try:
                    smtp.starttls(context=ctx)
                except Exception:
                    if use_starttls:
                        raise
        with smtp:
            if progress:
                progress("登录…", 30, 100)
            smtp.login(from_addr, password)
            if progress:
                progress("发送中…", 60, 100)
            smtp.send_message(msg, from_addr=from_addr, to_addrs=all_rcpt)
        if progress:
            progress("发送完成", 100, 100)
        return True, {
            "code": "ok",
            "title": "已发送",
            "human": "邮件已发送",
            "steps": [],
            "attachment_count": len(files),
        }
    except Exception as exc:
        return False, diagnose_mail_error(exc, provider_id=provider_id, phase="smtp_send")


def test_smtp_login(account: dict[str, Any], password: str) -> tuple[bool, dict[str, Any]]:
    provider_id = str(account.get("provider_id") or "custom")
    host = str(account.get("smtp_host") or "").strip()
    port = int(account.get("smtp_port") or 465)
    use_ssl = bool(account.get("smtp_ssl", True))
    use_starttls = bool(account.get("smtp_starttls", False))
    user = str(account.get("email") or "").strip()
    try:
        ctx = ssl.create_default_context()
        if use_ssl and not use_starttls:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            if use_starttls or not use_ssl:
                smtp.starttls(context=ctx)
        with smtp:
            smtp.login(user, password)
        return True, {"code": "ok", "title": "SMTP 连接成功", "human": "SMTP 连接成功", "steps": []}
    except Exception as exc:
        return False, diagnose_mail_error(exc, provider_id=provider_id, phase="smtp_login")
