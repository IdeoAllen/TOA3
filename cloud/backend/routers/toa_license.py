# -*- coding: utf-8 -*-
"""运营助手（TOA）授权 API — 与 DMS / TOA3 桌面协议兼容。"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from deps import require_perm
from models import AdminUser
from services import platform_bridge
from services import toa_license_service as svc

router = APIRouter(prefix="/api/toa-license", tags=["toa-license"])


def require_julong_internal(request: Request) -> None:
    """巨龙服务间调用：只认本机直连（经 nginx 转发会带 X-Real-IP）+ 共享密钥。"""
    from config import JULONG_INTERNAL_SECRET

    if not JULONG_INTERNAL_SECRET:
        raise HTTPException(503, "服务间密钥未配置")
    if request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for"):
        raise HTTPException(403, "仅限服务间调用")
    got = request.headers.get("x-internal-secret", "")
    if not hmac.compare_digest(got.encode(), JULONG_INTERNAL_SECRET.encode()):
        raise HTTPException(401, "服务间密钥无效")


@router.post("/platform-issue", dependencies=[Depends(require_julong_internal)])
def platform_issue(data: dict, db: Session = Depends(get_db)):
    """巨龙注册 / 个人中心：按手机号签发或返回当前 TOA 注册码。"""
    try:
        return platform_bridge.platform_issue(
            db,
            phone=str((data or {}).get("phone") or ""),
            name=str((data or {}).get("name") or ""),
            platform_user_id=str((data or {}).get("platform_user_id") or ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/platform-verify", dependencies=[Depends(require_julong_internal)])
def platform_verify(data: dict, db: Session = Depends(get_db)):
    """巨龙用注册码换密钥 / 校验推送权益。"""
    return platform_bridge.platform_verify(db, license_key=str((data or {}).get("license_key") or ""))


@router.post("/trial-start")
def trial_start(data: dict, db: Session = Depends(get_db)):
    """桌面登录「开始试用」：手机 + machine_id → 短期授权码并绑机。"""
    try:
        return svc.start_trial(
            db,
            phone=str((data or {}).get("phone") or ""),
            machine_id=str((data or {}).get("machine_id") or ""),
            name=str((data or {}).get("name") or ""),
            app_version=str((data or {}).get("app_version") or ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/activate")
def activate_license(data: dict, db: Session = Depends(get_db)):
    try:
        return svc.activate_online(
            db,
            license_key=str((data or {}).get("license_key") or ""),
            machine_id=str((data or {}).get("machine_id") or ""),
            app_version=str((data or {}).get("app_version") or ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/check")
def check_license(data: dict, db: Session = Depends(get_db)):
    try:
        return svc.check_online(
            db,
            code_id=str((data or {}).get("code_id") or ""),
            license_key=str((data or {}).get("license_key") or ""),
            machine_id=str((data or {}).get("machine_id") or ""),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/upgrade")
def upgrade_subscription(data: dict, db: Session = Depends(get_db)):
    """续费/拉码：已履约订单回传授权码；或管理员 extend（phone+pack+days+secret）。"""
    body = data or {}
    order_no = str(body.get("order_no") or "").strip()
    phone = str(body.get("phone") or "").strip()
    machine_id = str(body.get("machine_id") or "").strip()
    if order_no and phone:
        try:
            return svc.upgrade_from_fulfilled_order(
                db,
                order_no=order_no,
                phone=phone,
                machine_id=machine_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    raise HTTPException(
        400,
        "请提供 order_no + phone（已支付订单拉码）；新购请走 /api/toa/orders",
    )


@router.post("/register")
def register_license(data: dict, db: Session = Depends(get_db)):
    try:
        row = svc.register_signed_license(db, license_key=str((data or {}).get("license_key") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.license_to_dict(row)


@router.post("/sync")
def sync_license(data: dict, db: Session = Depends(get_db)):
    try:
        row = svc.sync_from_terminal(db, data or {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if row is None:
        return {"ok": True, "op": "delete"}
    if isinstance(row, dict):
        return row
    return svc.license_to_dict(row)


@router.post("/reconcile")
def reconcile_licenses(data: dict, db: Session = Depends(get_db)):
    try:
        payload = svc._verify_terminal_sync(data or {})
        if str(payload.get("op") or "").strip().lower() != "reconcile":
            raise ValueError("对账请求无效")
        return svc.reconcile_non_protected(db, payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("")
def list_licenses(
    q: str = Query(""),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    rows = svc.list_licenses(db, q=q)
    pid = svc.protected_admin_id(db)
    return [svc.license_to_dict(r, protected_id=pid) for r in rows]


@router.post("")
def create_license(
    data: dict,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        row = svc.create_license(db, data or {}, issued_by=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.license_to_dict(row, include_key=True, protected_id=svc.protected_admin_id(db))


@router.post("/clear")
def clear_other_licenses(
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:delete")),
):
    try:
        return svc.clear_other_licenses(db)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{license_id}")
def get_license(
    license_id: int,
    include_key: bool = Query(False),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    row = svc.get_license(db, license_id)
    if not row:
        raise HTTPException(404, "授权记录不存在")
    return svc.license_to_dict(row, include_key=include_key, protected_id=svc.protected_admin_id(db))


@router.delete("/{license_id}")
def delete_license(
    license_id: int,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:delete")),
):
    try:
        svc.delete_license(db, license_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.post("/{license_id}/revoke")
def revoke_license(
    license_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        svc._terminal_maintain_only()
        row = svc.revoke_license(db, license_id, revoked_by=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.license_to_dict(row, protected_id=svc.protected_admin_id(db))


@router.post("/{license_id}/unbind")
def unbind_license(
    license_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        svc._terminal_maintain_only()
        row = svc.unbind_machine(db, license_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.license_to_dict(row, protected_id=svc.protected_admin_id(db))


@router.post("/{license_id}/reissue")
def reissue_license(
    license_id: int,
    data: dict | None = None,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    try:
        svc._terminal_maintain_only()
        body = data or {}
        days = body.get("days", None)
        if days is not None and days != "":
            days = int(days)
        else:
            days = None
        row = svc.reissue_license(db, license_id, days=days, issued_by=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.license_to_dict(row, include_key=True, protected_id=svc.protected_admin_id(db))
