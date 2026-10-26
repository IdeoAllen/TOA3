# -*- coding: utf-8 -*-
"""假订单 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from deps import require_perm
from models import AdminUser
from services import order_service as svc

router = APIRouter(prefix="/api/toa/orders", tags=["toa-orders"])


def order_to_client(row) -> dict:
    return {
        "id": row.id,
        "order_no": row.order_no,
        "pack_id": row.pack_id,
        "pack_name": row.pack_name,
        "plan_id": row.pack_id,
        "plan_name": row.pack_name,
        "customer_name": row.customer_name,
        "phone": row.phone,
        "amount_yuan": row.amount_yuan,
        "license_days": row.license_days,
        "validity_days": row.license_days,
        "status": row.status,
        "payment_channel": row.payment_channel,
        "payment_provider": getattr(row, "payment_provider", "") or "",
        "payment_ref": getattr(row, "payment_ref", "") or "",
        "license_id": row.license_id,
        "machine_id": getattr(row, "machine_id", "") or "",
        "remark": row.remark,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "message": _status_message(row.status),
    }


def _status_message(status: str) -> str:
    return {
        "pending": "订单已创建，请完成支付",
        "fulfilled": "已付款并签发授权码",
        "cancelled": "订单已取消",
    }.get(status or "", "")


@router.get("/by-no/{order_no}")
def client_order_status(
    order_no: str,
    phone: str = Query(..., min_length=11, max_length=11),
    include_key: bool = Query(False),
    db: Session = Depends(get_db),
):
    """终端轮询订单状态（需订单号 + 手机号）。"""
    try:
        return svc.client_order_status(db, order_no, phone=phone, include_key=include_key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/by-no/{order_no}/pay")
def client_pay_order(order_no: str, data: dict, db: Session = Depends(get_db)):
    """终端发起支付（现阶段 mock；真实支付接入后同路径 webhook 履约）。"""
    body = data or {}
    phone = str(body.get("phone") or "").strip()
    machine_id = str(body.get("machine_id") or "").strip()
    if not phone:
        raise HTTPException(400, "请提供手机号")
    try:
        row = svc.client_pay_and_fulfill(db, order_no, phone=phone, machine_id=machine_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.order_to_dict(row, include_license_key=True, db=db)


@router.post("")
def create_order_public(data: dict, db: Session = Depends(get_db)):
    """创建待付款假订单（暂无真实支付，运营模拟付款后发卡）。"""
    try:
        row = svc.create_order(db, data or {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return order_to_client(row)


@router.get("")
def list_orders_admin(
    status: str = Query(""),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    rows = svc.list_orders(db, status=status)
    return [order_to_client(r) for r in rows]


@router.get("/{order_id}")
def get_order_admin(
    order_id: int,
    include_key: bool = Query(False),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    row = svc.get_order(db, order_id)
    if not row:
        raise HTTPException(404, "订单不存在")
    return svc.order_to_dict(row, include_license_key=include_key, db=db)


@router.post("/{order_id}/mock-pay")
def mock_pay_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        row = svc.mock_pay_and_fulfill(db, order_id, operator=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.order_to_dict(row, include_license_key=True, db=db)


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        row = svc.cancel_order(db, order_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return order_to_client(row)
