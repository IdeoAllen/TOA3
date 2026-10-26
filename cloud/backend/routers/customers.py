# -*- coding: utf-8 -*-
"""运营台 · 社区账号管理。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import require_perm
from models import AdminUser
from services import customer_service as cust

router = APIRouter(prefix="/api/toa/customers", tags=["toa-customers"])


@router.get("")
def list_customers(
    q: str = Query(""),
    enabled: bool | None = Query(None),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    return {"items": cust.list_customers(db, q=q, enabled=enabled)}


@router.get("/{customer_id}")
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    row = cust.get_customer(db, customer_id)
    if not row:
        raise HTTPException(404, "账号不存在")
    return cust.customer_to_dict(row, with_stats=True, db=db)


@router.post("/{customer_id}/enable")
def enable_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        row = cust.set_customer_enabled(db, customer_id, enabled=True)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "customer": cust.customer_to_dict(row, with_stats=True, db=db)}


@router.post("/{customer_id}/disable")
def disable_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        row = cust.set_customer_enabled(db, customer_id, enabled=False)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "customer": cust.customer_to_dict(row, with_stats=True, db=db)}
