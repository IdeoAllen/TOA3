# -*- coding: utf-8 -*-
"""邮箱客户端编排：绑定 / 同步 / 发信（网络在调用方线程）。"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from modules.email_client import mail_store
from services.mail.credentials import (
    clear_mail_password,
    credential_backend_label,
    get_mail_password,
    set_mail_password,
)
from services.mail.diagnose import diagnose_mail_error
from services.mail.imap_sync import sync_account_folders, test_imap_login
from services.mail.presets import apply_preset_to_account, get_preset, list_presets
from services.mail.smtp_send import (
    MAX_ATTACHMENT_BYTES,
    send_mail,
    test_smtp_login,
    validate_attachments,
)

ProgressCb = Callable[[str, int, int], None]


def ensure_store() -> None:
    mail_store.init_db()


def presets() -> list[dict[str, Any]]:
    return list(list_presets())


def current_account() -> dict[str, Any] | None:
    ensure_store()
    return mail_store.get_primary_account()


def has_password(account_id: str) -> bool:
    return bool(get_mail_password(account_id))


def bind_account(
    form: dict[str, Any],
    password: str,
    *,
    verify: bool = True,
    progress: ProgressCb | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any] | None]:
    """验证并保存账户。返回 (ok, diagnosis_or_ok, account)。"""
    ensure_store()
    provider_id = str(form.get("provider_id") or "custom")
    account = apply_preset_to_account(provider_id, form)
    account["email"] = str(form.get("email") or "").strip()
    account["display_name"] = str(form.get("display_name") or "").strip()
    # 手填可覆盖预设
    for key in (
        "imap_host",
        "imap_port",
        "imap_ssl",
        "smtp_host",
        "smtp_port",
        "smtp_ssl",
        "smtp_starttls",
    ):
        if key in form and form[key] is not None and str(form[key]) != "":
            account[key] = form[key]

    if not account["email"] or not str(password or "").strip():
        diag = diagnose_mail_error(
            "请填写邮箱地址与授权码",
            provider_id=provider_id,
            phase="bind",
        )
        return False, diag, None

    if verify:
        if progress:
            progress("验证 IMAP…", 1, 2)
        ok_imap, diag_imap = test_imap_login(account, password)
        if not ok_imap:
            return False, diag_imap, None
        if progress:
            progress("验证 SMTP…", 2, 2)
        ok_smtp, diag_smtp = test_smtp_login(account, password)
        if not ok_smtp:
            return False, diag_smtp, None

    existing = mail_store.get_primary_account()
    if existing and existing.get("email") == account["email"]:
        account["id"] = existing["id"]
    else:
        account["id"] = str(form.get("id") or uuid.uuid4().hex)

    aid = mail_store.upsert_account(account)
    set_mail_password(aid, password)
    account["id"] = aid
    return True, {
        "code": "ok",
        "title": "绑定成功",
        "human": f"已绑定 {account['email']}（凭证：{credential_backend_label()}）",
        "steps": [],
    }, account


def unbind_account() -> None:
    ensure_store()
    acc = mail_store.get_primary_account()
    if not acc:
        return
    clear_mail_password(str(acc["id"]))
    mail_store.delete_account(str(acc["id"]))


def sync_now(
    *,
    roles: tuple[str, ...] = ("inbox", "sent"),
    progress: ProgressCb | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """增量同步。返回 (ok, human_status, meta)。"""
    ensure_store()
    acc = mail_store.get_primary_account()
    if not acc:
        return False, "尚未绑定邮箱", {"diagnosis": diagnose_mail_error("未绑定", phase="sync")}
    pwd = get_mail_password(str(acc["id"]))
    if not pwd:
        return False, "找不到授权码，请重新绑定", {
            "diagnosis": diagnose_mail_error("授权码缺失", provider_id=acc.get("provider_id"), phase="sync")
        }

    cursors = mail_store.get_uid_cursors(str(acc["id"]))
    batches, results = sync_account_folders(
        acc,
        pwd,
        uid_cursors=cursors,
        roles=roles,
        progress=progress,
    )
    total_new = 0
    for role, folder, msgs, last_uid in batches:
        n = mail_store.upsert_parsed_messages(str(acc["id"]), role, msgs)
        total_new += n
        if last_uid:
            mail_store.set_folder_cursor(str(acc["id"]), role, folder, last_uid)

    hard_fail = [r for r in results if r.role == "*" and r.error]
    if hard_fail:
        diag = hard_fail[0].diagnosis or diagnose_mail_error(hard_fail[0].error, phase="sync")
        return False, diag.get("human") or hard_fail[0].error, {
            "diagnosis": diag,
            "results": [_result_dict(r) for r in results],
            "new_count": total_new,
        }

    parts = []
    for r in results:
        if r.error:
            parts.append(f"{r.role}失败")
        else:
            parts.append(f"{r.role}+{r.fetched}")
    status = f"同步完成：新增约 {total_new} 封（{' · '.join(parts)}）"
    return True, status, {"results": [_result_dict(r) for r in results], "new_count": total_new}


def _result_dict(r: Any) -> dict[str, Any]:
    return {
        "folder": r.folder,
        "role": r.role,
        "fetched": r.fetched,
        "last_uid": r.last_uid,
        "error": r.error,
        "diagnosis": r.diagnosis,
    }


def list_folder(folder_role: str = "inbox", *, limit: int = 200) -> list[dict[str, Any]]:
    ensure_store()
    acc = mail_store.get_primary_account()
    if not acc:
        return []
    return mail_store.list_messages(str(acc["id"]), folder_role, limit=limit)


def get_message(message_id: str) -> dict[str, Any] | None:
    ensure_store()
    msg = mail_store.get_message(message_id)
    if msg:
        mail_store.mark_seen(message_id, True)
        msg["is_seen"] = 1
    return msg


def send_now(
    *,
    to_addrs: list[str],
    subject: str,
    body_text: str,
    cc_addrs: list[str] | None = None,
    attachment_paths: list[str | Path] | None = None,
    progress: ProgressCb | None = None,
) -> tuple[bool, dict[str, Any]]:
    ensure_store()
    acc = mail_store.get_primary_account()
    if not acc:
        return False, diagnose_mail_error("尚未绑定邮箱", phase="send")
    pwd = get_mail_password(str(acc["id"]))
    if not pwd:
        return False, diagnose_mail_error("授权码缺失，请重新绑定", provider_id=acc.get("provider_id"), phase="send")
    return send_mail(
        acc,
        pwd,
        to_addrs=to_addrs,
        subject=subject,
        body_text=body_text,
        cc_addrs=cc_addrs,
        attachment_paths=attachment_paths,
        progress=progress,
    )


def export_attachment(local_path: str) -> Path:
    return mail_store.export_attachment(local_path)


def attachment_limits() -> dict[str, int]:
    return {
        "max_single_bytes": MAX_ATTACHMENT_BYTES,
        "max_single_mb": MAX_ATTACHMENT_BYTES // (1024 * 1024),
    }


def provider_auth_hint(provider_id: str) -> str:
    return str(get_preset(provider_id).get("auth_hint") or "")


def check_attachments(paths: list[str | Path]) -> tuple[bool, str]:
    ok, err, _ = validate_attachments(paths)
    return ok, err
