# -*- coding: utf-8 -*-
"""邮箱连接失败 → 人话诊断（授权码优先于协议术语）。"""
from __future__ import annotations

from typing import Any

from services.mail.presets import get_preset


def diagnose_mail_error(
    exc: BaseException | str,
    *,
    provider_id: str = "custom",
    phase: str = "connect",
) -> dict[str, Any]:
    """返回 {code, title, steps, detail}。"""
    text = str(exc or "").strip()
    low = text.lower()
    preset = get_preset(provider_id)
    auth_hint = str(preset.get("auth_hint") or "")
    imap_hint = str(preset.get("imap_enable_hint") or "")

    code = "unknown"
    title = "连接失败"
    steps: list[str] = []

    auth_markers = (
        "authentication failed",
        "invalid credentials",
        "login failed",
        "auth",
        "535",
        "534",
        "username and password not accepted",
        "application-specific password",
        "please log in via your web browser",
    )
    imap_markers = (
        "imap",
        "please enable",
        "not enabled",
        "unsafe login",
        "login to your account via a web browser",
    )
    net_markers = (
        "timed out",
        "timeout",
        "connection refused",
        "name or service not known",
        "getaddrinfo",
        "network is unreachable",
        "temporarily unavailable",
        "ssl",
        "certificate",
        "eof occurred",
        "connection reset",
    )
    size_markers = ("message size", "552", "file too large", "exceeds", "too big")

    if any(m in low for m in auth_markers) or "密码" in text or "授权" in text:
        code = "auth"
        title = "账号或授权码不正确"
        steps = [
            "请确认填写的是「授权码 / 应用密码」，不是网页登录密码。",
            auth_hint or "到邮箱网页设置里重新生成授权码后再试。",
            imap_hint,
        ]
    elif any(m in low for m in imap_markers):
        code = "imap_disabled"
        title = "邮箱未开启 IMAP / 第三方客户端"
        steps = [
            imap_hint or "请先在邮箱网页设置中开启 IMAP/SMTP。",
            auth_hint,
        ]
    elif any(m in low for m in size_markers):
        code = "size_limit"
        title = "附件或邮件过大"
        steps = [
            "请缩小附件，或拆成多封发送。",
            "本客户端默认单附件上限 25MB（含编码开销建议更小）。",
        ]
    elif any(m in low for m in net_markers):
        code = "network"
        title = "网络或服务器不可达"
        steps = [
            "检查本机网络，稍后点「重试」。",
            "确认 IMAP/SMTP 主机与端口无误；公司网络可能拦截 993/465。",
            "断线后可再次同步，本地已收邮件不会丢。",
        ]
    else:
        code = "unknown"
        title = "操作失败"
        steps = [
            auth_hint or "核对邮箱地址与授权码。",
            imap_hint or "确认已开启 IMAP/SMTP。",
            "可稍后重试；进页不会因联网卡死。",
        ]

    steps = [s for s in steps if s]
    return {
        "code": code,
        "title": title,
        "steps": steps,
        "detail": text[:800],
        "phase": phase,
        "provider_id": preset.get("id") or provider_id,
        "human": _format_human(title, steps, text),
    }


def _format_human(title: str, steps: list[str], detail: str) -> str:
    lines = [title, ""]
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step}")
    if detail:
        lines.append("")
        lines.append(f"（技术细节：{detail[:240]}）")
    return "\n".join(lines).strip()
