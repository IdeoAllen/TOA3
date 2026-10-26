# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_admin
from models import AdminUser
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, body.username.strip(), body.password)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    token = auth_service.issue_token(user)
    return {
        "token": token,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "permissions": {
            "toa_license:read": user.can_read,
            "toa_license:write": user.can_write,
            "toa_license:delete": user.can_delete,
            "toa_release:read": user.can_read,
            "toa_release:write": user.can_write,
        },
    }


@router.get("/me")
def me(user: AdminUser = Depends(get_current_admin)):
    return {
        "username": user.username,
        "display_name": user.display_name or user.username,
        "permissions": {
            "toa_license:read": user.can_read,
            "toa_license:write": user.can_write,
            "toa_license:delete": user.can_delete,
            "toa_release:read": user.can_read,
            "toa_release:write": user.can_write,
        },
    }
