# -*- coding: utf-8 -*-
"""本机邮箱协议层（IMAP/SMTP）。与 integrations.email 通知通道分轨。"""
from __future__ import annotations

from services.mail.credentials import (
    clear_mail_password,
    get_mail_password,
    set_mail_password,
)
from services.mail.diagnose import diagnose_mail_error
from services.mail.presets import PROVIDER_PRESETS, get_preset, list_presets

__all__ = [
    "PROVIDER_PRESETS",
    "clear_mail_password",
    "diagnose_mail_error",
    "get_mail_password",
    "get_preset",
    "list_presets",
    "set_mail_password",
]
