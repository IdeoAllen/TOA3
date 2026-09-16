# -*- coding: utf-8 -*-
"""邮箱厂商预设（绑定页模板 + 授权码人话说明）。"""
from __future__ import annotations

from typing import Any, TypedDict


class ProviderPreset(TypedDict, total=False):
    id: str
    name: str
    imap_host: str
    imap_port: int
    imap_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_ssl: bool
    smtp_starttls: bool
    auth_hint: str
    imap_enable_hint: str
    sent_folder_hints: list[str]
    trash_folder_hints: list[str]


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "qq": {
        "id": "qq",
        "name": "QQ 邮箱",
        "imap_host": "imap.qq.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "smtp_ssl": True,
        "smtp_starttls": False,
        "auth_hint": (
            "QQ 邮箱需使用「授权码」，不是登录密码。\n"
            "路径：QQ 邮箱网页 → 设置 → 账户 → POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务 → "
            "开启 IMAP/SMTP → 生成授权码。"
        ),
        "imap_enable_hint": "请先在 QQ 邮箱设置中开启 IMAP/SMTP 服务，再用授权码登录。",
        "sent_folder_hints": ["Sent Messages", "已发送", "INBOX.Sent"],
        "trash_folder_hints": ["Trash", "已删除", "Deleted Messages", "INBOX.Trash"],
    },
    "netease_163": {
        "id": "netease_163",
        "name": "网易 163",
        "imap_host": "imap.163.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
        "smtp_ssl": True,
        "smtp_starttls": False,
        "auth_hint": (
            "163 邮箱需开启 IMAP/SMTP 并使用「客户端授权密码」。\n"
            "路径：163 网页邮箱 → 设置 → POP3/SMTP/IMAP → 开启 IMAP/SMTP → 生成授权密码。"
        ),
        "imap_enable_hint": "请先开启 163 的 IMAP/SMTP，并用客户端授权密码（非网页登录密码）。",
        "sent_folder_hints": ["已发送", "Sent Messages", "INBOX.Sent"],
        "trash_folder_hints": ["已删除", "Trash", "Deleted Messages"],
    },
    "outlook": {
        "id": "outlook",
        "name": "Outlook.com",
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "auth_hint": (
            "Outlook.com / 个人微软账号通常需「应用密码」（若已开启两步验证）。\n"
            "路径：account.microsoft.com → 安全 → 高级安全选项 → 应用密码。\n"
            "企业 Microsoft 365 / Exchange 本版不支持 OAuth，请另开。"
        ),
        "imap_enable_hint": "确认账号已允许 IMAP；企业账号若强制 OAuth，本版无法绑定。",
        "sent_folder_hints": ["Sent", "Sent Items", "已发送邮件"],
        "trash_folder_hints": ["Deleted", "Deleted Items", "Junk", "Trash"],
    },
    "gmail": {
        "id": "gmail",
        "name": "Gmail",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "smtp_ssl": True,
        "smtp_starttls": False,
        "auth_hint": (
            "Gmail 需开启两步验证后生成「应用专用密码」。\n"
            "路径：Google 账号 → 安全性 → 两步验证 → 应用专用密码。\n"
            "本版不支持 Google OAuth 登录。"
        ),
        "imap_enable_hint": "请确认已开启 IMAP（Gmail 设置 → 转发和 POP/IMAP）。",
        "sent_folder_hints": ["[Gmail]/Sent Mail", "Sent Mail", "已发送邮件"],
        "trash_folder_hints": ["[Gmail]/Trash", "Trash", "已删除邮件"],
    },
    "custom": {
        "id": "custom",
        "name": "手动填写",
        "imap_host": "",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "",
        "smtp_port": 465,
        "smtp_ssl": True,
        "smtp_starttls": False,
        "auth_hint": (
            "请向邮箱管理员索取 IMAP/SMTP 主机、端口与加密方式。\n"
            "多数国内邮箱使用「授权码/应用密码」，不是网页登录密码。"
        ),
        "imap_enable_hint": "请确认服务器已开启 IMAP，且账号允许第三方客户端登录。",
        "sent_folder_hints": ["Sent", "Sent Messages", "已发送"],
        "trash_folder_hints": ["Trash", "Deleted", "已删除"],
    },
}


def list_presets() -> list[ProviderPreset]:
    order = ("qq", "netease_163", "outlook", "gmail", "custom")
    return [PROVIDER_PRESETS[k] for k in order if k in PROVIDER_PRESETS]


def get_preset(provider_id: str) -> ProviderPreset:
    pid = str(provider_id or "").strip().lower() or "custom"
    return dict(PROVIDER_PRESETS.get(pid) or PROVIDER_PRESETS["custom"])


def apply_preset_to_account(provider_id: str, account: dict[str, Any] | None = None) -> dict[str, Any]:
    """用预设填充账户连接字段（不覆盖已有邮箱地址）。"""
    preset = get_preset(provider_id)
    out = dict(account or {})
    out["provider_id"] = preset["id"]
    out["imap_host"] = preset.get("imap_host") or out.get("imap_host") or ""
    out["imap_port"] = int(preset.get("imap_port") or out.get("imap_port") or 993)
    out["imap_ssl"] = bool(preset.get("imap_ssl", True))
    out["smtp_host"] = preset.get("smtp_host") or out.get("smtp_host") or ""
    out["smtp_port"] = int(preset.get("smtp_port") or out.get("smtp_port") or 465)
    out["smtp_ssl"] = bool(preset.get("smtp_ssl", True))
    out["smtp_starttls"] = bool(preset.get("smtp_starttls", False))
    return out
