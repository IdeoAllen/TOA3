# -*- coding: utf-8 -*-
"""巨龙数变场一码通：服务间签发 / 校验 TOA 注册码。

协议：julong-platform/docs/protocol/一码通_注册码与账号.md
- 同一手机号同一时刻只有一个当前码（_store_signed_key 按手机号合并）。
- 巨龙预发的码 remark 带 platform 标记、不预先绑机，首次激活时绑定。
- 预发码过期且从未激活：再次获取时重签新码，避免“没下载就把体验期耗光”。
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import ToaLicense
from services import toa_license_service as lic


def _current_row(db: Session, phone: str) -> Optional[ToaLicense]:
    rows = (
        db.query(ToaLicense)
        .filter(ToaLicense.phone == phone, ToaLicense.status != "revoked")
        .order_by(ToaLicense.id.desc())
        .all()
    )
    for row in rows:
        if not lic._is_admin_license(row):
            return row
    return None


def _days_left(expire_date: str) -> int:
    try:
        exp = datetime.datetime.strptime((expire_date or "")[:10], "%Y-%m-%d").date()
    except Exception:
        return 0
    return max(0, (exp - lic._today()).days)


def _describe(row: ToaLicense, *, created: bool) -> Dict[str, Any]:
    return {
        "license_key": row.license_key,
        "entitlement": lic._infer_entitlement(row),
        "plan_id": lic._plan_id_from_row(row),
        "expire_date": row.expire_date,
        "days_left": _days_left(row.expire_date),
        "status": lic._effective_status(row),
        "activated": bool((row.activated_machine_id or "").strip()),
        "created": created,
    }


def platform_issue(
    db: Session, *, phone: str, name: str = "", platform_user_id: str = ""
) -> Dict[str, Any]:
    phone = str(phone or "").strip()
    if not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")
    uid = str(platform_user_id or "").strip()[:64]

    row = _current_row(db, phone)
    if row is not None:
        reissue = lic._effective_status(row) == "expired" and lic.is_unclaimed_platform_code(row)
        if not reissue:
            if uid and row.platform_user_id != uid:
                row.platform_user_id = uid
                db.commit()
                db.refresh(row)
            return _describe(row, created=False)

    trial = lic.trial_settings()
    if not trial["enabled"]:
        raise ValueError("体验授权已关闭，请在 TOA 内购买或联系运营")

    from services import pack_service

    display = str(name or "").strip()[:40] or f"巨龙用户{phone[-4:]}"
    if display in ("管理员", "admin"):
        display = f"巨龙用户{phone[-4:]}"
    menus = pack_service.pack_menus_for_license(trial["pack_id"], db=db)
    code, payload = lic.issue_code(
        name=display,
        phone=phone,
        days=trial["days"],
        role="user",
        menus=menus,
        bind_machine=True,
    )
    row = lic._store_signed_key(
        db,
        license_key=code,
        payload=payload,
        issued_by=None,
        remark=f"trial|{trial['pack_id']}|{lic.PLATFORM_REMARK_TAG}",
        entitlement="trial",
        plan_id=trial["pack_id"],
    )
    if uid:
        row.platform_user_id = uid
    db.commit()
    db.refresh(row)
    return _describe(row, created=True)


def platform_verify(db: Session, *, license_key: str) -> Dict[str, Any]:
    key = str(license_key or "").strip().replace(" ", "")
    ok, msg, _payload = lic._parse_signed_payload(key)
    if not ok:
        return {"valid": False, "reason": msg or "注册码无效"}
    row = db.query(ToaLicense).filter(ToaLicense.code_id == lic._code_id(key)).first()
    if row is None or (row.license_key or "").strip().replace(" ", "") != key:
        return {"valid": False, "reason": "注册码未登记或已被新码替换"}
    status = lic._effective_status(row)
    return {
        "valid": status == "active",
        "status": status,
        "phone": row.phone,
        "name": row.name,
        "entitlement": lic._infer_entitlement(row),
        "features": lic._features_from_row(row),
        "expire_date": row.expire_date,
        "days_left": _days_left(row.expire_date),
        "platform_user_id": row.platform_user_id or "",
    }
