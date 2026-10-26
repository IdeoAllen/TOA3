# -*- coding: utf-8 -*-
"""终端用户（toa_customers）：授权/订单对齐后的用户主数据；兼社区投稿归因。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models import ToaCustomer, ToaLicense, ToaOrder, ToaSoftAsset, ToaSoftAssetEvent
from services import toa_license_service as lic


def _now() -> datetime:
    return datetime.now(timezone.utc)


def customer_to_dict(row: ToaCustomer, *, with_stats: bool = False, db: Session | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "phone": row.phone or "",
        "display_name": row.display_name or "",
        "code_id": row.code_id or "",
        "license_id": row.license_id,
        "enabled": bool(row.enabled),
        "remark": row.remark or "",
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        "entitlement": "",
        "entitlement_label": "—",
        "plan_id": "",
        "order_no": "",
        "expire_date": "",
        "license_status": "",
        "order_count": 0,
    }
    if with_stats and db is not None:
        out["plugin_count"] = (
            db.query(ToaSoftAsset).filter(ToaSoftAsset.customer_id == row.id).count()
        )
        out["upload_count"] = (
            db.query(ToaSoftAssetEvent)
            .filter(
                ToaSoftAssetEvent.customer_id == row.id,
                ToaSoftAssetEvent.event_kind == "upload",
            )
            .count()
        )
        out["download_count"] = (
            db.query(ToaSoftAssetEvent)
            .filter(
                ToaSoftAssetEvent.customer_id == row.id,
                ToaSoftAssetEvent.event_kind == "download",
            )
            .count()
        )
        phone = (row.phone or "").strip()
        if phone:
            out["order_count"] = (
                db.query(ToaOrder).filter(ToaOrder.phone == phone).count()
            )
        lic_row = None
        if row.license_id:
            lic_row = db.query(ToaLicense).filter(ToaLicense.id == int(row.license_id)).first()
        if lic_row is None and phone:
            lic_row = (
                db.query(ToaLicense)
                .filter(ToaLicense.phone == phone)
                .order_by(ToaLicense.id.desc())
                .first()
            )
        if lic_row is not None:
            ent = lic._infer_entitlement(lic_row)
            out["entitlement"] = ent
            out["entitlement_label"] = lic._entitlement_label(ent)
            out["plan_id"] = lic._plan_id_from_row(lic_row)
            out["order_no"] = str(getattr(lic_row, "order_no", None) or "").strip()
            out["expire_date"] = str(lic_row.expire_date or "")
            out["license_status"] = str(lic_row.status or "")
            out["license_id"] = lic_row.id
    return out


def list_customers(
    db: Session,
    *,
    q: str = "",
    enabled: bool | None = None,
    limit: int = 200,
    sync: bool = True,
) -> list[dict[str, Any]]:
    if sync:
        try:
            lic.sync_all_licenses_to_customers(db)
        except Exception:
            pass
    query = db.query(ToaCustomer)
    if enabled is not None:
        query = query.filter(ToaCustomer.enabled.is_(bool(enabled)))
    qq = (q or "").strip()
    if qq:
        like = f"%{qq}%"
        query = query.filter(
            (ToaCustomer.phone.like(like))
            | (ToaCustomer.display_name.like(like))
            | (ToaCustomer.code_id.like(like))
        )
    rows = query.order_by(ToaCustomer.id.desc()).limit(max(1, min(limit, 500))).all()
    return [customer_to_dict(r, with_stats=True, db=db) for r in rows]


def get_customer(db: Session, customer_id: int) -> ToaCustomer | None:
    return db.query(ToaCustomer).filter(ToaCustomer.id == int(customer_id)).first()


def set_customer_enabled(db: Session, customer_id: int, *, enabled: bool) -> ToaCustomer:
    row = get_customer(db, customer_id)
    if not row:
        raise ValueError("账号不存在")
    row.enabled = bool(enabled)
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def assert_customer_active(customer: ToaCustomer) -> None:
    if not customer.enabled:
        raise ValueError("账号已停用，无法上传或下载社区插件")


def upsert_from_license_row(db: Session, row: ToaLicense) -> ToaCustomer | None:
    """按手机号（优先）或 code_id 对齐用户主数据。管理员与同号普通用户各保留一条。"""
    if row is None:
        return None
    phone = str(row.phone or "").strip()
    name = str(row.name or "").strip() or phone or (row.code_id or "")[:8]
    cid = str(row.code_id or "").strip()
    is_admin = str(row.role or "").strip().lower() == "admin"

    customer = None
    if cid:
        customer = db.query(ToaCustomer).filter(ToaCustomer.code_id == cid).first()
    if customer is None and phone and not is_admin:
        # 普通用户：同号合并；管理员单独一条，避免被订单用户顶掉
        customer = (
            db.query(ToaCustomer)
            .filter(ToaCustomer.phone == phone, ToaCustomer.code_id != "")
            .order_by(ToaCustomer.id.asc())
            .first()
        )
        if customer is not None:
            # 若已绑到管理员码，另开一条
            linked = None
            if customer.license_id:
                linked = db.query(ToaLicense).filter(ToaLicense.id == customer.license_id).first()
            if linked is not None and str(linked.role or "").lower() == "admin":
                customer = None
    if customer is None and phone and is_admin:
        customer = (
            db.query(ToaCustomer)
            .filter(ToaCustomer.phone == phone, ToaCustomer.display_name.in_(("管理员", "admin")))
            .first()
        )
    if customer is None:
        customer = ToaCustomer(
            phone=phone,
            display_name=name,
            code_id=cid,
            license_id=row.id,
            enabled=True,
            remark="from-license",
        )
        db.add(customer)
    else:
        customer.display_name = name or customer.display_name
        if phone:
            customer.phone = phone
        if cid:
            customer.code_id = cid
        customer.license_id = row.id
        if not (customer.remark or "").strip():
            customer.remark = "from-license"
    customer.updated_at = _now()
    db.commit()
    db.refresh(customer)
    return customer


def resolve_customer_from_license(
    db: Session,
    *,
    license_key: str,
    machine_id: str = "",
) -> tuple[ToaCustomer, ToaLicense]:
    """校验授权码并 upsert 社区账号。"""
    key = (license_key or "").strip().replace(" ", "")
    mid = (machine_id or "").strip()
    if not key:
        raise ValueError("缺少授权码")
    ok, msg, payload = lic._parse_signed_payload(key)  # noqa: SLF001 — 与 catalog 同源
    if not ok or not payload:
        raise ValueError(msg or "授权码无效")

    cid = lic._code_id(key)  # noqa: SLF001
    row = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
    if not row:
        try:
            row = lic.register_signed_license(db, key)
        except Exception as exc:
            raise ValueError(f"授权码未在云服务登记：{exc}") from exc

    if (row.status or "").lower() not in ("active", ""):
        raise ValueError(f"授权状态不可用：{row.status}")

    if row.bind_machine and mid and (row.activated_machine_id or "").strip():
        if (row.activated_machine_id or "").strip() != mid:
            raise ValueError("授权码已绑定其他设备")

    customer = upsert_from_license_row(db, row)
    if customer is None:
        raise ValueError("无法登记用户")
    customer.last_seen_at = _now()
    customer.updated_at = _now()
    db.commit()
    db.refresh(customer)
    assert_customer_active(customer)
    return customer, row
