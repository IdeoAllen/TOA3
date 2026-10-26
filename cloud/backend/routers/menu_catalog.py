# -*- coding: utf-8 -*-
"""终端菜单目录 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_admin, require_perm
from models import AdminUser
from services import product_catalog_service as cat
from services import toa_license_service as lic

router = APIRouter(prefix="/api/toa/menu-catalog", tags=["toa-menu-catalog"])


@router.get("/modules")
def list_modules(
    q: str = "",
    show_hidden: bool = True,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    modules = cat.list_menu_modules(db, q=q, show_hidden=show_hidden)
    return {
        "menu_catalog": cat.catalog_meta_db(db),
        "modules": modules,
        "query": {"q": q or "", "show_hidden": bool(show_hidden)},
    }


@router.post("/admin/publish")
def admin_publish(
    data: dict,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    modules = (data or {}).get("modules") or []
    try:
        result = cat.publish_menu_modules(
            db,
            modules,
            app_version=str((data or {}).get("app_version") or ""),
            published_by=f"ops:{user.username}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, **result}


@router.post("/publish")
def terminal_publish(data: dict, db: Session = Depends(get_db)):
    """终端管理员：维护菜单后上传 module 目录（需 admin 授权码 + 绑机）。"""
    body = data or {}
    license_key = str(body.get("license_key") or "").strip()
    machine_id = str(body.get("machine_id") or "").strip()
    modules = body.get("modules") or []
    app_version = str(body.get("app_version") or "").strip()
    if not license_key:
        raise HTTPException(400, "缺少授权码")
    if not machine_id:
        raise HTTPException(400, "缺少 machine_id")
    try:
        lic.assert_catalog_publisher(db, license_key=license_key, machine_id=machine_id)
        result = cat.publish_menu_modules(
            db,
            modules,
            app_version=app_version,
            published_by=f"terminal-admin:{machine_id[:8]}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, **result}
