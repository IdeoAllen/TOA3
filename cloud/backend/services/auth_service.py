# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from sqlalchemy.orm import Session

from config import JWT_EXPIRE_HOURS, JWT_SECRET
from models import AdminUser


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$", 2)
        if scheme != "pbkdf2":
            return False
        expect = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
        return hmac.compare_digest(expect, digest)
    except Exception:
        return False


def ensure_admin(db: Session, username: str, password: str) -> AdminUser:
    row = db.query(AdminUser).filter(AdminUser.username == username).first()
    if row:
        return row
    row = AdminUser(
        username=username,
        password_hash=_hash_password(password),
        display_name="系统管理员",
        role="admin",
        can_read=True,
        can_write=True,
        can_delete=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def authenticate(db: Session, username: str, password: str) -> Optional[AdminUser]:
    row = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.is_active.is_(True)).first()
    if not row or not verify_password(password, row.password_hash):
        return None
    return row


def issue_token(user: AdminUser) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "can_read": bool(user.can_read),
        "can_write": bool(user.can_write),
        "can_delete": bool(user.can_delete),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
