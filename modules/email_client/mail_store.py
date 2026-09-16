# -*- coding: utf-8 -*-
"""邮箱本地 SQLite + 附件落盘。"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir, module_output_dir

MODULE_ID = "email_client"


def db_path() -> Path:
    return module_data_dir(MODULE_ID, create=True) / "mail.sqlite"


def attachments_dir(account_id: str, message_id: str) -> Path:
    d = module_data_dir(MODULE_ID, create=True) / "attachments" / account_id / message_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def export_dir() -> Path:
    return module_output_dir(MODULE_ID, create=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                display_name TEXT,
                provider_id TEXT,
                imap_host TEXT,
                imap_port INTEGER,
                imap_ssl INTEGER DEFAULT 1,
                smtp_host TEXT,
                smtp_port INTEGER,
                smtp_ssl INTEGER DEFAULT 1,
                smtp_starttls INTEGER DEFAULT 0,
                created_at REAL,
                updated_at REAL,
                extra_json TEXT
            );

            CREATE TABLE IF NOT EXISTS folders (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                role TEXT NOT NULL,
                remote_name TEXT NOT NULL,
                last_uid INTEGER DEFAULT 0,
                UNIQUE(account_id, role),
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                folder_role TEXT NOT NULL,
                remote_uid TEXT NOT NULL,
                message_id_hdr TEXT,
                subject TEXT,
                from_addr TEXT,
                to_addrs TEXT,
                cc_addrs TEXT,
                date_iso TEXT,
                is_seen INTEGER DEFAULT 0,
                has_attach INTEGER DEFAULT 0,
                body_text TEXT,
                body_html TEXT,
                raw_size INTEGER DEFAULT 0,
                UNIQUE(account_id, folder_role, remote_uid),
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                filename TEXT,
                content_type TEXT,
                size INTEGER,
                local_path TEXT,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_folder
                ON messages(account_id, folder_role, date_iso DESC);
            """
        )


def upsert_account(data: dict[str, Any]) -> str:
    init_db()
    aid = str(data.get("id") or "").strip() or uuid.uuid4().hex
    now = time.time()
    with _connect() as conn:
        row = conn.execute("SELECT created_at FROM accounts WHERE id=?", (aid,)).fetchone()
        created = float(row["created_at"]) if row else now
        conn.execute(
            """
            INSERT INTO accounts (
                id, email, display_name, provider_id,
                imap_host, imap_port, imap_ssl,
                smtp_host, smtp_port, smtp_ssl, smtp_starttls,
                created_at, updated_at, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                email=excluded.email,
                display_name=excluded.display_name,
                provider_id=excluded.provider_id,
                imap_host=excluded.imap_host,
                imap_port=excluded.imap_port,
                imap_ssl=excluded.imap_ssl,
                smtp_host=excluded.smtp_host,
                smtp_port=excluded.smtp_port,
                smtp_ssl=excluded.smtp_ssl,
                smtp_starttls=excluded.smtp_starttls,
                updated_at=excluded.updated_at,
                extra_json=excluded.extra_json
            """,
            (
                aid,
                str(data.get("email") or "").strip(),
                str(data.get("display_name") or "").strip(),
                str(data.get("provider_id") or "custom"),
                str(data.get("imap_host") or "").strip(),
                int(data.get("imap_port") or 993),
                1 if data.get("imap_ssl", True) else 0,
                str(data.get("smtp_host") or "").strip(),
                int(data.get("smtp_port") or 465),
                1 if data.get("smtp_ssl", True) else 0,
                1 if data.get("smtp_starttls", False) else 0,
                created,
                now,
                json.dumps(data.get("extra") or {}, ensure_ascii=False),
            ),
        )
    return aid


def get_primary_account() -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM accounts ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return _account_from_row(row)


def delete_account(account_id: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))


def _account_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"] or "",
        "provider_id": row["provider_id"] or "custom",
        "imap_host": row["imap_host"] or "",
        "imap_port": int(row["imap_port"] or 993),
        "imap_ssl": bool(row["imap_ssl"]),
        "smtp_host": row["smtp_host"] or "",
        "smtp_port": int(row["smtp_port"] or 465),
        "smtp_ssl": bool(row["smtp_ssl"]),
        "smtp_starttls": bool(row["smtp_starttls"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_uid_cursors(account_id: str) -> dict[str, int]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, remote_name, last_uid FROM folders WHERE account_id=?",
            (account_id,),
        ).fetchall()
    out: dict[str, int] = {}
    for r in rows:
        out[str(r["remote_name"])] = int(r["last_uid"] or 0)
        out[str(r["role"])] = int(r["last_uid"] or 0)
    return out


def set_folder_cursor(account_id: str, role: str, remote_name: str, last_uid: int) -> None:
    init_db()
    fid = f"{account_id}:{role}"
    uid = int(last_uid)
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_uid FROM folders WHERE account_id=? AND role=?",
            (account_id, role),
        ).fetchone()
        if row:
            uid = max(int(row["last_uid"] or 0), uid)
            conn.execute(
                "UPDATE folders SET remote_name=?, last_uid=? WHERE account_id=? AND role=?",
                (remote_name, uid, account_id, role),
            )
        else:
            conn.execute(
                """
                INSERT INTO folders (id, account_id, role, remote_name, last_uid)
                VALUES (?,?,?,?,?)
                """,
                (fid, account_id, role, remote_name, uid),
            )


def upsert_parsed_messages(
    account_id: str,
    folder_role: str,
    messages: list[Any],
) -> int:
    """写入 ParsedMessage 列表；附件落盘。返回写入条数。"""
    init_db()
    count = 0
    with _connect() as conn:
        for msg in messages:
            mid = uuid.uuid4().hex
            existing = conn.execute(
                """
                SELECT id FROM messages
                WHERE account_id=? AND folder_role=? AND remote_uid=?
                """,
                (account_id, folder_role, str(msg.uid)),
            ).fetchone()
            if existing:
                mid = existing["id"]
                conn.execute(
                    """
                    UPDATE messages SET
                        message_id_hdr=?, subject=?, from_addr=?, to_addrs=?,
                        cc_addrs=?, date_iso=?, is_seen=?, has_attach=?,
                        body_text=?, body_html=?, raw_size=?
                    WHERE id=?
                    """,
                    (
                        msg.message_id,
                        msg.subject,
                        msg.from_addr,
                        msg.to_addrs,
                        msg.cc_addrs,
                        msg.date_iso,
                        1 if msg.is_seen else 0,
                        1 if msg.attachments else 0,
                        msg.body_text,
                        msg.body_html,
                        msg.raw_size,
                        mid,
                    ),
                )
                conn.execute("DELETE FROM attachments WHERE message_id=?", (mid,))
            else:
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, account_id, folder_role, remote_uid, message_id_hdr,
                        subject, from_addr, to_addrs, cc_addrs, date_iso,
                        is_seen, has_attach, body_text, body_html, raw_size
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        mid,
                        account_id,
                        folder_role,
                        str(msg.uid),
                        msg.message_id,
                        msg.subject,
                        msg.from_addr,
                        msg.to_addrs,
                        msg.cc_addrs,
                        msg.date_iso,
                        1 if msg.is_seen else 0,
                        1 if msg.attachments else 0,
                        msg.body_text,
                        msg.body_html,
                        msg.raw_size,
                    ),
                )
                count += 1

            att_dir = attachments_dir(account_id, mid)
            for att in msg.attachments or []:
                safe_name = Path(att.filename or "file.bin").name
                dest = att_dir / safe_name
                # 重名则加后缀
                if dest.exists():
                    dest = att_dir / f"{dest.stem}_{uuid.uuid4().hex[:6]}{dest.suffix}"
                dest.write_bytes(att.payload)
                conn.execute(
                    """
                    INSERT INTO attachments (id, message_id, filename, content_type, size, local_path)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        uuid.uuid4().hex,
                        mid,
                        safe_name,
                        att.content_type,
                        att.size,
                        str(dest),
                    ),
                )
    return count


def list_messages(
    account_id: str,
    folder_role: str = "inbox",
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, subject, from_addr, to_addrs, date_iso, is_seen, has_attach, remote_uid
            FROM messages
            WHERE account_id=? AND folder_role=?
            ORDER BY date_iso DESC
            LIMIT ?
            """,
            (account_id, folder_role, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


def get_message(message_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            return None
        atts = conn.execute(
            "SELECT id, filename, content_type, size, local_path FROM attachments WHERE message_id=?",
            (message_id,),
        ).fetchall()
    data = dict(row)
    data["attachments"] = [dict(a) for a in atts]
    return data


def mark_seen(message_id: str, seen: bool = True) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE messages SET is_seen=? WHERE id=?",
            (1 if seen else 0, message_id),
        )


def export_attachment(local_path: str, dest_name: str | None = None) -> Path:
    src = Path(local_path)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    out = export_dir() / (dest_name or src.name)
    if out.exists():
        out = export_dir() / f"{out.stem}_{uuid.uuid4().hex[:6]}{out.suffix}"
    out.write_bytes(src.read_bytes())
    return out


def message_count(account_id: str, folder_role: str = "inbox") -> int:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE account_id=? AND folder_role=?",
            (account_id, folder_role),
        ).fetchone()
    return int(row["c"] if row else 0)
