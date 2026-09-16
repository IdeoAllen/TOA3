# -*- coding: utf-8 -*-
"""IMAP 增量同步（UID · 可断点续同）。"""
from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from typing import Any, Callable

from services.mail.diagnose import diagnose_mail_error
from services.mail.presets import get_preset

logger = logging.getLogger("TOA3.mail.imap")

ProgressCb = Callable[[str, int, int], None]  # message, current, total


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    payload: bytes
    size: int


@dataclass
class ParsedMessage:
    uid: str
    message_id: str
    subject: str
    from_addr: str
    to_addrs: str
    cc_addrs: str
    date_iso: str
    flags: list[str]
    is_seen: bool
    body_text: str
    body_html: str
    attachments: list[ParsedAttachment] = field(default_factory=list)
    raw_size: int = 0


@dataclass
class SyncFolderResult:
    folder: str
    role: str  # inbox | sent | trash | other
    fetched: int
    last_uid: int
    error: str = ""
    diagnosis: dict[str, Any] | None = None


def _decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts: list[str] = []
    try:
        for chunk, charset in email.header.decode_header(raw):
            if isinstance(chunk, bytes):
                parts.append(chunk.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(str(chunk))
    except Exception:
        return str(raw)
    return "".join(parts).strip()


def _addr_list(msg: Message, key: str) -> str:
    raw = msg.get(key) or ""
    try:
        addrs = email.utils.getaddresses([raw])
        return ", ".join(
            f"{name} <{addr}>".strip() if name else addr for name, addr in addrs if addr
        )
    except Exception:
        return _decode_header(raw)


def _parse_date(msg: Message) -> str:
    raw = msg.get("Date") or ""
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _walk_bodies(msg: Message) -> tuple[str, str, list[ParsedAttachment]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[ParsedAttachment] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = str(part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if filename:
                filename = _decode_header(filename)
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            if filename or "attachment" in disp:
                attachments.append(
                    ParsedAttachment(
                        filename=filename or "attachment.bin",
                        content_type=ctype or "application/octet-stream",
                        payload=payload,
                        size=len(payload),
                    )
                )
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        ctype = (msg.get_content_type() or "text/plain").lower()
        payload = msg.get_payload(decode=True)
        if payload is None:
            payload = b""
        charset = msg.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except Exception:
            decoded = payload.decode("utf-8", errors="replace")
        if ctype == "text/html":
            html_parts.append(decoded)
        else:
            text_parts.append(decoded)

    return "\n".join(text_parts).strip(), "\n".join(html_parts).strip(), attachments


def parse_rfc822(raw: bytes, *, uid: str, flags: list[str] | None = None) -> ParsedMessage:
    msg = email.message_from_bytes(raw)
    flags = list(flags or [])
    text, html, atts = _walk_bodies(msg)
    return ParsedMessage(
        uid=str(uid),
        message_id=str(msg.get("Message-ID") or "").strip(),
        subject=_decode_header(msg.get("Subject")),
        from_addr=_addr_list(msg, "From"),
        to_addrs=_addr_list(msg, "To"),
        cc_addrs=_addr_list(msg, "Cc"),
        date_iso=_parse_date(msg),
        flags=flags,
        is_seen=any(f.strip("\\").lower() == "seen" for f in flags),
        body_text=text,
        body_html=html,
        attachments=atts,
        raw_size=len(raw),
    )


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def connect_imap(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    use_ssl: bool = True,
    timeout: float = 30.0,
) -> imaplib.IMAP4:
    host = str(host or "").strip()
    user = str(user or "").strip()
    if not host or not user or not password:
        raise ValueError("IMAP 主机、邮箱或授权码为空")
    if use_ssl:
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(
            host, int(port or 993), ssl_context=_ssl_context(), timeout=timeout
        )
    else:
        client = imaplib.IMAP4(host, int(port or 143), timeout=timeout)
        try:
            client.starttls(ssl_context=_ssl_context())
        except Exception:
            pass
    typ, _ = client.login(user, password)
    if typ != "OK":
        raise RuntimeError(f"IMAP 登录失败: {typ}")
    return client


def test_imap_login(account: dict[str, Any], password: str) -> tuple[bool, dict[str, Any]]:
    provider_id = str(account.get("provider_id") or "custom")
    try:
        client = connect_imap(
            host=str(account.get("imap_host") or ""),
            port=int(account.get("imap_port") or 993),
            user=str(account.get("email") or ""),
            password=password,
            use_ssl=bool(account.get("imap_ssl", True)),
        )
        try:
            client.logout()
        except Exception:
            pass
        return True, {"code": "ok", "title": "IMAP 连接成功", "human": "IMAP 连接成功", "steps": []}
    except Exception as exc:
        return False, diagnose_mail_error(exc, provider_id=provider_id, phase="imap_login")


def _select_folder(client: imaplib.IMAP4, folder: str) -> tuple[bool, str]:
    for candidate in (folder, f'"{folder}"'):
        try:
            typ, _ = client.select(candidate, readonly=True)
            if typ == "OK":
                return True, candidate
        except Exception:
            continue
    return False, folder


def list_mailboxes(client: imaplib.IMAP4) -> list[str]:
    typ, data = client.list()
    if typ != "OK" or not data:
        return ["INBOX"]
    names: list[str] = []
    for item in data:
        if not item:
            continue
        line = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
        # 末段文件夹名
        m = re.search(r' "?(.*?)"?$', line)
        name = m.group(1) if m else line.split()[-1].strip('"')
        if name and name not in names:
            names.append(name)
    return names or ["INBOX"]


def resolve_folder_roles(
    mailboxes: list[str],
    provider_id: str,
) -> dict[str, str]:
    """role -> mailbox name。"""
    preset = get_preset(provider_id)
    lower_map = {m.lower(): m for m in mailboxes}
    roles: dict[str, str] = {"inbox": "INBOX"}
    if "inbox" in lower_map:
        roles["inbox"] = lower_map["inbox"]

    def _pick(hints: list[str], fallback_sub: tuple[str, ...]) -> str | None:
        for h in hints:
            if h.lower() in lower_map:
                return lower_map[h.lower()]
        for box in mailboxes:
            bl = box.lower()
            if any(s in bl for s in fallback_sub):
                return box
        return None

    sent = _pick(list(preset.get("sent_folder_hints") or []), ("sent", "已发送"))
    trash = _pick(list(preset.get("trash_folder_hints") or []), ("trash", "deleted", "已删除"))
    if sent:
        roles["sent"] = sent
    if trash:
        roles["trash"] = trash
    return roles


def fetch_uid_range(
    client: imaplib.IMAP4,
    folder: str,
    *,
    since_uid: int = 0,
    limit: int = 100,
    progress: ProgressCb | None = None,
) -> tuple[list[ParsedMessage], int]:
    ok, selected = _select_folder(client, folder)
    if not ok:
        raise RuntimeError(f"无法打开文件夹: {folder}")

    if since_uid > 0:
        criteria = f"UID {since_uid + 1}:*"
    else:
        criteria = "ALL"
    typ, data = client.uid("SEARCH", None, criteria)
    if typ != "OK":
        raise RuntimeError(f"UID SEARCH 失败: {typ}")
    raw_ids = (data[0] or b"").split() if data else []
    uids: list[int] = []
    for x in raw_ids:
        try:
            uids.append(int(x))
        except Exception:
            continue
    uids = sorted(uids)
    if since_uid > 0:
        uids = [u for u in uids if u > since_uid]
    if limit > 0:
        uids = uids[:limit]

    messages: list[ParsedMessage] = []
    last_uid = since_uid
    total = len(uids)
    for i, uid in enumerate(uids, 1):
        if progress:
            progress(f"收取 {folder} ({i}/{total})", i, total)
        typ, fetched = client.uid("FETCH", str(uid), "(FLAGS BODY.PEEK[])")
        if typ != "OK" or not fetched:
            continue
        raw = b""
        flags: list[str] = []
        for part in fetched:
            if not isinstance(part, tuple) or len(part) < 2:
                continue
            meta = part[0]
            if isinstance(meta, bytes):
                meta_s = meta.decode("utf-8", errors="replace")
            else:
                meta_s = str(meta)
            fm = re.search(r"FLAGS \(([^)]*)\)", meta_s)
            if fm:
                flags = [f for f in fm.group(1).split() if f]
            body = part[1]
            if isinstance(body, bytes):
                raw = body
        if not raw:
            continue
        parsed = parse_rfc822(raw, uid=str(uid), flags=flags)
        messages.append(parsed)
        last_uid = max(last_uid, uid)
    return messages, last_uid


def sync_account_folders(
    account: dict[str, Any],
    password: str,
    *,
    uid_cursors: dict[str, int] | None = None,
    roles: tuple[str, ...] = ("inbox", "sent"),
    limit_per_folder: int = 80,
    progress: ProgressCb | None = None,
) -> tuple[list[tuple[str, str, list[ParsedMessage], int]], list[SyncFolderResult]]:
    """返回 ([(role, folder, messages, last_uid), ...], results)。"""
    provider_id = str(account.get("provider_id") or "custom")
    cursors = dict(uid_cursors or {})
    batches: list[tuple[str, str, list[ParsedMessage], int]] = []
    results: list[SyncFolderResult] = []
    client = None
    try:
        if progress:
            progress("连接邮箱…", 0, 0)
        client = connect_imap(
            host=str(account.get("imap_host") or ""),
            port=int(account.get("imap_port") or 993),
            user=str(account.get("email") or ""),
            password=password,
            use_ssl=bool(account.get("imap_ssl", True)),
        )
        boxes = list_mailboxes(client)
        role_map = resolve_folder_roles(boxes, provider_id)
        for role in roles:
            folder = role_map.get(role)
            if not folder:
                results.append(
                    SyncFolderResult(folder="", role=role, fetched=0, last_uid=0, error="未找到文件夹")
                )
                continue
            since = int(cursors.get(folder) or cursors.get(role) or 0)
            try:
                msgs, last_uid = fetch_uid_range(
                    client,
                    folder,
                    since_uid=since,
                    limit=limit_per_folder,
                    progress=progress,
                )
                batches.append((role, folder, msgs, last_uid))
                results.append(
                    SyncFolderResult(folder=folder, role=role, fetched=len(msgs), last_uid=last_uid)
                )
            except Exception as exc:
                diag = diagnose_mail_error(exc, provider_id=provider_id, phase=f"sync:{role}")
                results.append(
                    SyncFolderResult(
                        folder=folder,
                        role=role,
                        fetched=0,
                        last_uid=since,
                        error=str(exc),
                        diagnosis=diag,
                    )
                )
    except Exception as exc:
        diag = diagnose_mail_error(exc, provider_id=provider_id, phase="sync")
        results.append(
            SyncFolderResult(
                folder="",
                role="*",
                fetched=0,
                last_uid=0,
                error=str(exc),
                diagnosis=diag,
            )
        )
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
    return batches, results
