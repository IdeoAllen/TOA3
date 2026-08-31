# -*- coding: utf-8 -*-
"""通知通道扩展：邮件（SMTP，需 integrations.email 启用）。"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger("TOA3.notify.email")


def send_email_notification(title: str, body: str, *, to: str | None = None) -> tuple[bool, str]:
    """发送纯文本邮件。返回 (成功与否, 收件人)。"""
    try:
        from services.integrations.config import integration_config, integration_enabled
    except Exception:
        return False, ""
    if not integration_enabled("email"):
        logger.info("email 通道未启用")
        return False, ""
    cfg: dict[str, Any] = integration_config("email") or {}
    host = str(cfg.get("smtp_server") or "").strip()
    port = int(cfg.get("port") or 587)
    sender = str(cfg.get("sender_email") or "").strip()
    password = str(cfg.get("password") or "").strip()
    recipient = (to or str(cfg.get("recipient_email") or "")).strip()
    if not all([host, sender, recipient]):
        logger.warning("email 配置不完整")
        return False, recipient
    msg = MIMEText(body or title, "plain", "utf-8")
    msg["Subject"] = title or "TOA 通知"
    msg["From"] = sender
    msg["To"] = recipient
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if cfg.get("use_tls", True):
                smtp.starttls()
            if password:
                smtp.login(sender, password)
            smtp.sendmail(sender, [recipient], msg.as_string())
        return True, recipient
    except Exception:
        logger.exception("发送邮件失败")
        return False, recipient
