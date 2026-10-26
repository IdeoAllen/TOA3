# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import AdminUser
from services.auth_service import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AdminUser:
    if creds is None or not creds.credentials:
        raise HTTPException(401, "请先登录")
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(401, "登录已失效，请重新登录") from None
    uid = int(payload.get("sub") or 0)
    user = db.query(AdminUser).filter(AdminUser.id == uid, AdminUser.is_active.is_(True)).first()
    if not user:
        raise HTTPException(401, "用户不存在或已禁用")
    user._jwt_payload = payload  # type: ignore[attr-defined]
    return user


def require_perm(*perms: str) -> Callable:
    def _dep(user: AdminUser = Depends(get_current_admin)) -> AdminUser:
        payload = getattr(user, "_jwt_payload", {}) or {}
        mapping = {
            "toa_license:read": bool(payload.get("can_read", user.can_read)),
            "toa_license:write": bool(payload.get("can_write", user.can_write)),
            "toa_license:delete": bool(payload.get("can_delete", user.can_delete)),
            "toa_release:read": bool(payload.get("can_read", user.can_read)),
            "toa_release:write": bool(payload.get("can_write", user.can_write)),
        }
        if not any(mapping.get(p, False) for p in perms):
            raise HTTPException(403, "无权限")
        return user

    return _dep
