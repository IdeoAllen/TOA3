# -*- coding: utf-8 -*-
"""假订单：创建 → 模拟付款 → 按 pack 签发授权码。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from models import AdminUser, ToaLicense, ToaOrder
from services import pack_service as packs
from services import toa_license_service as lic


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_order_no() -> str:
    return f"TOA{_now().strftime('%Y%m%d')}{secrets.token_hex(3).upper()}"


def order_to_dict(row: ToaOrder, *, include_license_key: bool = False, db: Session | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
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
        "payment_channel": row.payment_channel or "mock",
        "payment_provider": getattr(row, "payment_provider", "") or "",
        "payment_ref": getattr(row, "payment_ref", "") or "",
        "license_id": row.license_id,
        "machine_id": getattr(row, "machine_id", "") or "",
        "remark": row.remark or "",
        "paid_at": row.paid_at.isoformat() if row.paid_at else "",
        "fulfilled_at": row.fulfilled_at.isoformat() if row.fulfilled_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_license_key and row.license_id and db is not None:
        lic_row = db.query(ToaLicense).filter(ToaLicense.id == row.license_id).first()
        if lic_row:
            out["license_key"] = lic_row.license_key
            out["code_fingerprint"] = lic_row.code_fingerprint
    return out


def list_orders(db: Session, *, status: str = "", limit: int = 100) -> list[ToaOrder]:
    q = db.query(ToaOrder)
    if status:
        q = q.filter(ToaOrder.status == status.strip())
    return q.order_by(ToaOrder.id.desc()).limit(max(1, min(limit, 500))).all()


def get_order(db: Session, order_id: int) -> Optional[ToaOrder]:
    return db.query(ToaOrder).filter(ToaOrder.id == order_id).first()


def get_order_by_no(db: Session, order_no: str) -> Optional[ToaOrder]:
    no = str(order_no or "").strip()
    if not no:
        return None
    return db.query(ToaOrder).filter(ToaOrder.order_no == no).first()


def _mock_payment_enabled() -> bool:
    try:
        return packs.mock_payment_enabled()
    except Exception:
        return True


def _fulfill_order_license(
    db: Session,
    row: ToaOrder,
    *,
    operator: Optional[AdminUser] = None,
    payment_provider: str = "mock",
    payment_ref: str = "",
) -> ToaOrder:
    pack = packs.get_pack(row.pack_id, db=db)
    if not pack:
        raise ValueError(f"产品方案不存在：{row.pack_id}")
    if not pack.get("sellable"):
        raise ValueError("该产品方案不可售")
    catalog_price = int(pack.get("price_yuan") or 0)
    if int(row.amount_yuan or 0) != catalog_price:
        raise ValueError(f"订单金额 ¥{row.amount_yuan} 与方案定价 ¥{catalog_price} 不一致，拒绝履约")
    validation = pack.get("menu_validation") or {}
    if validation and not validation.get("ok", True):
        raise ValueError("方案含未发布 module，请先由终端管理员同步菜单目录")
    if row.license_id:
        row.status = "fulfilled"
        row.paid_at = row.paid_at or _now()
        row.fulfilled_at = row.fulfilled_at or _now()
        if payment_provider:
            row.payment_provider = payment_provider
        if payment_ref:
            row.payment_ref = payment_ref
        db.commit()
        db.refresh(row)
        return row

    lic_row = lic.issue_license_for_order(
        db,
        name=row.customer_name,
        phone=row.phone,
        plan_id=row.pack_id,
        days=row.license_days,
        order_no=row.order_no,
        remark=f"订单 {row.order_no} 履约",
        issued_by=operator,
    )

    row.status = "fulfilled"
    row.payment_channel = payment_provider or "mock"
    row.payment_provider = payment_provider or "mock"
    if payment_ref:
        row.payment_ref = payment_ref
    row.license_id = lic_row.id
    row.paid_at = _now()
    row.fulfilled_at = _now()
    row.remark = (row.remark or "").strip()
    pay_note = "已发卡"
    if pay_note not in row.remark:
        row.remark = f"{row.remark}；{pay_note}".strip("；")
    db.commit()
    db.refresh(row)
    return row


def create_order(
    db: Session,
    data: dict,
    *,
    created_by: Optional[AdminUser] = None,
) -> ToaOrder:
    pack_id = str(data.get("plan_id") or data.get("pack_id") or "").strip()
    if not pack_id:
        raise ValueError("请选择产品方案 plan_id")
    pack = packs.get_pack(pack_id, db=db)
    if not pack:
        raise ValueError(f"未知产品方案：{pack_id}")
    if not pack.get("sellable"):
        raise ValueError(f"「{pack.get('name')}」不可售（local_free 为单机免费层）")
    validation = pack.get("menu_validation") or {}
    if validation and not validation.get("ok", True):
        unknown = validation.get("unknown") or []
        raise ValueError(f"产品方案未对齐菜单目录：{', '.join(unknown)}")

    name = str(data.get("customer_name") or data.get("name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    if not name:
        raise ValueError("请填写客户姓名")
    if not phone or not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")

    plan_days = int(pack.get("validity_days") or packs.default_license_days())
    if created_by is not None and data.get("license_days") not in (None, ""):
        try:
            plan_days = max(1, int(data.get("license_days") or data.get("days") or plan_days))
        except Exception as e:
            raise ValueError("有效天数无效") from e
    days = plan_days
    if days <= 0:
        raise ValueError("有效天数必须大于 0")

    amount = data.get("amount_yuan")
    if amount is None or amount == "":
        amount_yuan = int(pack.get("price_yuan") or 0)
    else:
        try:
            amount_yuan = max(0, int(amount))
        except Exception as e:
            raise ValueError("金额无效") from e
        if amount_yuan != int(pack.get("price_yuan") or 0):
            raise ValueError("订单金额须与产品方案定价一致")

    remark = str(data.get("remark") or "").strip() or "终端订单·待付款"
    machine_id = str(data.get("machine_id") or "").strip()

    row = ToaOrder(
        order_no=_gen_order_no(),
        pack_id=pack_id,
        pack_name=str(pack.get("name") or pack_id),
        customer_name=name,
        phone=phone,
        amount_yuan=amount_yuan,
        license_days=days,
        status="pending",
        payment_channel="mock",
        remark=remark,
        machine_id=machine_id,
        created_by_id=created_by.id if created_by else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def client_order_status(
    db: Session,
    order_no: str,
    *,
    phone: str,
    include_key: bool = False,
) -> dict[str, Any]:
    row = get_order_by_no(db, order_no)
    if not row:
        raise ValueError("订单不存在")
    if str(phone or "").strip() != str(row.phone or "").strip():
        raise ValueError("手机号与订单不匹配")
    out = order_to_dict(row, include_license_key=include_key and row.status == "fulfilled", db=db)
    out["message"] = {
        "pending": "待付款",
        "fulfilled": "已付款并开通授权",
        "cancelled": "订单已取消",
    }.get(row.status or "", "")
    return out


def client_pay_and_fulfill(
    db: Session,
    order_no: str,
    *,
    phone: str,
    machine_id: str = "",
) -> ToaOrder:
    row = get_order_by_no(db, order_no)
    if not row:
        raise ValueError("订单不存在")
    if str(phone or "").strip() != str(row.phone or "").strip():
        raise ValueError("手机号与订单不匹配")
    if row.status == "cancelled":
        raise ValueError("订单已取消")
    if machine_id:
        row.machine_id = str(machine_id).strip()
        db.commit()
    if row.status == "fulfilled":
        db.refresh(row)
        return row
    if not _mock_payment_enabled():
        raise ValueError("当前未开放终端自助支付，请联系管理员在运营台确认付款")
    return mock_pay_and_fulfill(db, row.id)


def mock_pay_and_fulfill(
    db: Session,
    order_id: int,
    *,
    operator: Optional[AdminUser] = None,
    payment_ref: str = "",
) -> ToaOrder:
    row = get_order(db, order_id)
    if not row:
        raise ValueError("订单不存在")
    if row.status == "fulfilled":
        return row
    if row.status == "cancelled":
        raise ValueError("订单已取消")
    return _fulfill_order_license(
        db,
        row,
        operator=operator,
        payment_provider="mock",
        payment_ref=payment_ref or f"mock-{row.order_no}",
    )


def fulfill_order_by_payment(
    db: Session,
    *,
    order_no: str = "",
    order_id: int | None = None,
    phone: str = "",
    payment_provider: str = "wechat",
    payment_ref: str = "",
    operator: Optional[AdminUser] = None,
) -> ToaOrder:
    """支付回调 / webhook 履约（幂等：同一 payment_ref 不重复发卡）。"""
    ref = str(payment_ref or "").strip()
    if ref:
        existing = (
            db.query(ToaOrder)
            .filter(ToaOrder.payment_ref == ref, ToaOrder.status == "fulfilled")
            .first()
        )
        if existing:
            return existing

    if order_id:
        row = get_order(db, order_id)
    elif order_no:
        row = get_order_by_no(db, order_no)
    else:
        raise ValueError("缺少 order_no 或 order_id")
    if not row:
        raise ValueError("订单不存在")
    if phone and str(phone).strip() != str(row.phone or "").strip():
        raise ValueError("手机号与订单不匹配")
    if row.status == "cancelled":
        raise ValueError("订单已取消")
    if row.status == "fulfilled":
        return row
    channel = str(payment_provider or "webhook").strip().lower() or "webhook"
    return _fulfill_order_license(
        db,
        row,
        operator=operator,
        payment_provider=channel,
        payment_ref=ref or f"{channel}-{row.order_no}",
    )


def cancel_order(db: Session, order_id: int) -> ToaOrder:
    row = get_order(db, order_id)
    if not row:
        raise ValueError("订单不存在")
    if row.status == "fulfilled":
        raise ValueError("已履约订单不可取消")
    row.status = "cancelled"
    db.commit()
    db.refresh(row)
    return row
