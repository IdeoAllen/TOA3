# -*- coding: utf-8 -*-
"""运营助手（TOA）授权：TOA 云服务台账 + 联网校验。

与 TOA/common/license_manager.py 使用同一套 HMAC 算法（TOA2-...）。
固定保留 1 个管理员账号不可清除；其他账号可在本页新增/清除，也可由终端同步。
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import AdminUser, ToaLicense

# 与 TOA license_manager 保持一致（勿单独改一侧）
_P1 = bytes([0x59, 0x43, 0x5A, 0x48, 0x2D, 0x54, 0x4F, 0x41])  # YCZH-TOA
_P2 = b"YunYingBao"
_P3 = bytes.fromhex("a7c3e91f4b6280d5e2f7a04c91b6d83e")
_P4 = b"license-v2-hmac"
_CODE_PREFIX = "TOA2"
_SCHEMA_VER = 2


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text or "") + pad)


def _issuer_secret() -> bytes:
    material = _P1 + b"|" + _P2 + b"|" + _P3 + b"|" + _P4 + b"|v2"
    return hashlib.sha256(material).digest()


def _hmac_trunc(message: bytes, n: int = 16) -> bytes:
    return hmac.new(_issuer_secret(), message, hashlib.sha256).digest()[:n]


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _today() -> datetime.date:
    return datetime.datetime.now().date()


def _code_id(license_key: str) -> str:
    return hashlib.sha256((license_key or "").encode("utf-8")).hexdigest()


def _code_fingerprint(license_key: str) -> str:
    key = (license_key or "").strip()
    if len(key) < 12:
        return key
    return f"{key[:10]}…{key[-6:]}"


def _normalize_menus(menus=None) -> List[str]:
    if menus is None:
        return ["all"]
    if isinstance(menus, str):
        menus = [menus]
    cleaned = []
    seen = set()
    for m in list(menus or []):
        mid = str(m or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        cleaned.append(mid)
    if not cleaned or "all" in cleaned or "*" in cleaned:
        return ["all"]
    return cleaned


def _parse_signed_payload(license_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    key = (license_key or "").strip().replace(" ", "")
    if not key:
        return False, "请输入授权码", None
    if not key.startswith(f"{_CODE_PREFIX}-"):
        return False, "授权码格式无效（需 TOA2- 开头）", None
    try:
        rest = key[len(_CODE_PREFIX) + 1 :]
        body, sig = rest.rsplit(".", 1)
    except Exception:
        return False, "授权码格式无效", None
    try:
        expect = _b64e(_hmac_trunc(body.encode("ascii"), 16))
        if not hmac.compare_digest(sig, expect):
            return False, "授权码签名校验失败", None
        payload = json.loads(_b64d(body).decode("utf-8"))
    except Exception:
        return False, "授权码无法解析", None
    if int(payload.get("v") or 0) != _SCHEMA_VER:
        return False, "授权码版本不兼容", None
    return True, "ok", payload


def issue_code(
    *,
    name: str,
    phone: str = "",
    days: int = 365,
    expire_date: str = "",
    role: str = "user",
    menus=None,
    bind_machine: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """生成 TOA2 授权码与载荷。expire_date 优先于 days。"""
    name = (name or "").strip()
    phone = (phone or "").strip()
    role = (role or "user").strip() or "user"
    features = _normalize_menus(menus)
    if role == "admin":
        features = ["all"]
    if not name:
        raise ValueError("姓名不能为空")
    if name in ("管理员", "admin"):
        raise ValueError("「管理员」为系统固定账号，请换一个姓名")
    if not phone or not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")
    exp_raw = (expire_date or "").strip()
    if exp_raw:
        try:
            exp_d = datetime.datetime.strptime(exp_raw[:10], "%Y-%m-%d").date()
        except Exception as e:
            raise ValueError("到期日格式无效") from e
        if exp_d < _today():
            raise ValueError("到期日已过，请先延长有效期后再换码")
    else:
        if days <= 0:
            raise ValueError("有效期天数必须大于 0")
        exp_d = _today() + datetime.timedelta(days=int(days))
    payload = {
        "v": _SCHEMA_VER,
        "name": name,
        "phone": phone,
        "role": role,
        "exp": exp_d.strftime("%Y-%m-%d"),
        "iat": int(time.time()),
        "nonce": secrets.token_hex(8),
        "bind": 1 if bind_machine else 0,
        "menus": features,
    }
    body = _b64e(_canonical_json(payload).encode("utf-8"))
    sig = _b64e(_hmac_trunc(body.encode("ascii"), 16))
    code = f"{_CODE_PREFIX}-{body}.{sig}"
    return code, payload


def _infer_entitlement_from_remark(remark: str) -> str:
    text = str(remark or "")
    low = text.lower()
    if "订单" in text or "plan=" in text:
        return "paid"
    if "trial" in low or "试用" in text or "体验" in text:
        return "trial"
    return "trial"


def _entitlement_label(ent: str) -> str:
    # 与终端档位对齐：管理员/体验授权/正式版；「授权版」= 邀请码后续用 invited
    mapping = {
        "trial": "体验授权",
        "paid": "正式版",
        "admin": "管理员",
        "invited": "授权版",
    }
    return mapping.get(str(ent or "").strip().lower(), "—")


def _infer_entitlement(row: ToaLicense) -> str:
    ent = str(getattr(row, "entitlement", None) or "").strip().lower()
    if ent in ("trial", "paid", "admin"):
        return ent
    if str(getattr(row, "role", None) or "").strip().lower() == "admin":
        return "admin"
    remark = str(getattr(row, "remark", None) or "")
    order_no = str(getattr(row, "order_no", None) or "").strip()
    if order_no or "订单" in remark or "plan=" in remark:
        return "paid"
    low = remark.lower()
    if "trial" in low or "试用" in remark or "体验" in remark:
        return "trial"
    return "trial"


def _plan_id_from_row(row: ToaLicense) -> str:
    plan = str(getattr(row, "plan_id", None) or "").strip()
    if plan:
        return plan
    remark = str(getattr(row, "remark", None) or "")
    if "|" in remark:
        parts = remark.split("|")
        if len(parts) >= 2 and parts[1].strip():
            return parts[1].strip()
    if "plan=" in remark:
        tail = remark.split("plan=", 1)[-1].strip()
        return tail.split()[0].strip(" ·")
    return ""


def license_to_dict(
    row: ToaLicense,
    *,
    include_key: bool = False,
    protected_id: Optional[int] = None,
) -> Dict[str, Any]:
    expired = False
    try:
        expired = datetime.datetime.strptime(row.expire_date[:10], "%Y-%m-%d").date() < _today()
    except Exception:
        pass
    status = row.status or "active"
    if status == "active" and expired:
        status = "expired"
    out = {
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "role": row.role or "user",
        "expire_date": row.expire_date,
        "status": status,
        "entitlement": _infer_entitlement(row),
        "entitlement_label": _entitlement_label(_infer_entitlement(row)),
        "plan_id": _plan_id_from_row(row),
        "order_no": str(getattr(row, "order_no", None) or "").strip(),
        "activated": bool((row.activated_machine_id or "").strip()),
        "code_fingerprint": row.code_fingerprint or _code_fingerprint(row.license_key or ""),
        "code_id": row.code_id,
        "bind_machine": bool(row.bind_machine),
        "activated_at": row.activated_at.isoformat() if row.activated_at else "",
        "last_check_at": row.last_check_at.isoformat() if row.last_check_at else "",
        "remark": row.remark or "",
        "protected": bool(protected_id is not None and row.id == protected_id),
    }
    if include_key:
        out["license_key"] = row.license_key
    return out


def list_licenses(
    db: Session,
    *,
    q: str = "",
    limit: int = 200,
) -> List[ToaLicense]:
    query = db.query(ToaLicense)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((ToaLicense.name.like(like)) | (ToaLicense.phone.like(like)))
    return query.order_by(ToaLicense.id.desc()).limit(max(1, min(limit, 500))).all()


def create_license(
    db: Session,
    data: dict,
    *,
    issued_by: Optional[AdminUser] = None,
) -> ToaLicense:
    """签发规则与运营宝终端管理员一致：姓名/11 位手机/天数，普通用户、绑定本机、全部功能。"""
    name = str(data.get("name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    role = str(data.get("role") or "user").strip() or "user"
    if role not in ("user", "admin"):
        raise ValueError("角色只能是 user 或 admin")
    if role == "admin":
        raise ValueError("本页只签发普通终端用户；固定管理员不可再签发")
    try:
        days = int(data.get("days") or 365)
    except Exception as e:
        raise ValueError("有效期天数无效") from e
    if days <= 0:
        raise ValueError("有效期天数必须大于 0")
    if not name:
        raise ValueError("姓名不能为空")
    if name in ("管理员", "admin"):
        raise ValueError("「管理员」为系统固定账号，请换一个姓名")
    if not phone or not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")

    pack_id = str(data.get("pack_id") or "").strip()
    entitlement = str(data.get("entitlement") or "trial").strip().lower()
    if entitlement not in ("trial", "paid"):
        raise ValueError("授权类型只能是 trial（体验版）或 paid（付费版）")
    menus_raw = data.get("menus")
    if pack_id:
        from services import pack_service

        menus = pack_service.pack_menus_for_license(pack_id, db=db)
    elif menus_raw is not None:
        menus = list(menus_raw) if isinstance(menus_raw, list) else [menus_raw]
    else:
        menus = ["all"]
    remark = str(data.get("remark") or "").strip()
    if not remark:
        remark = f"{entitlement}|{pack_id or 'all'}"

    code, payload = issue_code(
        name=name,
        phone=phone,
        days=days,
        role="user",
        menus=menus,
        bind_machine=True,
    )
    return _store_signed_key(
        db,
        license_key=code,
        payload=payload,
        issued_by=issued_by,
        remark=remark,
        entitlement=entitlement,
        plan_id=pack_id,
        order_no=str(data.get("order_no") or "").strip(),
    )


def issue_license_for_order(
    db: Session,
    *,
    name: str,
    phone: str,
    plan_id: str,
    days: int,
    order_no: str = "",
    remark: str = "",
    issued_by: Optional[AdminUser] = None,
) -> ToaLicense:
    """一订单一授权码：每次履约新建 license，不合并同手机号旧码。"""
    from services import pack_service

    phone = str(phone or "").strip()
    name = str(name or "").strip()
    plan_id = str(plan_id or "").strip()
    if not phone or not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")
    if days <= 0:
        raise ValueError("有效天数必须大于 0")
    if not plan_id:
        raise ValueError("产品方案不能为空")

    menus = pack_service.pack_menus_for_license(plan_id, db=db)
    note = remark or f"订单 {order_no} · plan={plan_id}".strip()
    return create_license(
        db,
        {
            "name": name,
            "phone": phone,
            "days": days,
            "pack_id": plan_id,
            "menus": menus,
            "remark": note,
            "entitlement": "paid",
            "order_no": order_no,
        },
        issued_by=issued_by,
    )


def extend_or_create_for_subscription(
    db: Session,
    *,
    name: str,
    phone: str,
    pack_id: str,
    days: int,
    remark: str = "",
    issued_by: Optional[AdminUser] = None,
) -> Tuple[ToaLicense, bool]:
    """同手机号续费：延长到期日并换码（保留绑机）；无记录则新签发。

    Returns:
        (license_row, renewed) — renewed=True 表示续费而非新客。
    """
    from services import pack_service

    phone = str(phone or "").strip()
    name = str(name or "").strip()
    if not phone or not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")
    if days <= 0:
        raise ValueError("有效天数必须大于 0")

    menus = pack_service.pack_menus_for_license(pack_id, db=db)
    row = (
        db.query(ToaLicense)
        .filter(ToaLicense.phone == phone, ToaLicense.status != "revoked")
        .order_by(ToaLicense.id.desc())
        .first()
    )

    if row is not None:
        try:
            base = datetime.datetime.strptime(str(row.expire_date or "")[:10], "%Y-%m-%d").date()
        except Exception:
            base = _today()
        start = max(_today(), base)
        new_exp = start + datetime.timedelta(days=int(days))

        code, payload = issue_code(
            name=name or row.name,
            phone=phone,
            expire_date=new_exp.strftime("%Y-%m-%d"),
            role=str(row.role or "user"),
            menus=menus,
            bind_machine=bool(row.bind_machine),
        )
        new_cid = _code_id(code)
        clash = db.query(ToaLicense).filter(ToaLicense.code_id == new_cid, ToaLicense.id != row.id).first()
        if clash:
            raise ValueError("授权码冲突，请重试")

        preserved_mid = row.activated_machine_id or ""
        preserved_at = row.activated_at

        row.code_id = new_cid
        row.code_fingerprint = _code_fingerprint(code)
        row.license_key = code
        row.expire_date = new_exp.strftime("%Y-%m-%d")
        row.status = "active"
        row.menus_json = json.dumps(_normalize_menus(menus), ensure_ascii=False)
        if name:
            row.name = name
        note = f"续费至 {new_exp.strftime('%Y-%m-%d')} · pack={pack_id}"
        prev = (row.remark or "").strip()
        row.remark = f"{prev}；{note}" if prev and note not in prev else (prev or note)
        if remark:
            row.remark = f"{row.remark}；{remark}".strip("；")
        row.activated_machine_id = preserved_mid
        row.activated_at = preserved_at
        row.revoke_reason = ""
        row.revoked_at = None
        row.revoked_by_id = None
        if issued_by:
            row.issued_by_id = issued_by.id
        db.commit()
        db.refresh(row)
        return row, True

    lic_row = create_license(
        db,
        {
            "name": name,
            "phone": phone,
            "days": days,
            "pack_id": pack_id,
            "menus": menus,
            "remark": remark or f"新订阅 · pack={pack_id}",
        },
        issued_by=issued_by,
    )
    return lic_row, False


def upgrade_from_fulfilled_order(
    db: Session,
    *,
    order_no: str,
    phone: str,
    machine_id: str = "",
) -> Dict[str, Any]:
    """终端拉取已履约订单的授权码（用于 Portal 支付后回跳）。"""
    from services import order_service as orders

    row = orders.get_order_by_no(db, order_no)
    if not row:
        raise ValueError("订单不存在")
    if str(phone or "").strip() != str(row.phone or "").strip():
        raise ValueError("手机号与订单不匹配")
    if row.status != "fulfilled" or not row.license_id:
        raise ValueError("订单尚未履约，请完成支付或联系管理员")
    lic_row = db.query(ToaLicense).filter(ToaLicense.id == row.license_id).first()
    if not lic_row or not (lic_row.license_key or "").strip():
        raise ValueError("授权记录异常，请联系管理员")
    if machine_id and not (row.machine_id or "").strip():
        row.machine_id = str(machine_id).strip()
        db.commit()
    return {
        "ok": True,
        "renewed": False,
        "order_no": row.order_no,
        "pack_id": row.pack_id,
        "plan_id": row.pack_id,
        "plan_name": row.pack_name,
        "validity_days": row.license_days,
        "expire_date": lic_row.expire_date,
        "license_key": lic_row.license_key,
        "code_fingerprint": lic_row.code_fingerprint,
    }


def register_signed_license(db: Session, license_key: str) -> ToaLicense:
    """本机签发后登记到云服务：验签通过则入库（幂等）。"""
    ok, msg, payload = _parse_signed_payload(license_key)
    if not ok or not payload:
        raise ValueError(msg or "授权码无效")
    key = (license_key or "").strip().replace(" ", "")
    cid = _code_id(key)
    existing = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
    if existing:
        if existing.status == "revoked":
            raise ValueError("该授权码已在云服务停用")
        return existing
    return _store_signed_key(
        db,
        license_key=key,
        payload=payload,
        issued_by=None,
        remark="本机签发同步",
        entitlement="admin" if str(payload.get("role") or "").strip().lower() == "admin" else "",
    )


def _verify_terminal_sync(body: dict) -> Dict[str, Any]:
    """终端 HMAC 签名同步包。"""
    if not isinstance(body, dict):
        raise ValueError("同步数据无效")
    payload = body.get("data")
    sig = str(body.get("sig") or "")
    if not isinstance(payload, dict) or not sig:
        raise ValueError("缺少同步签名")
    expect = _b64e(_hmac_trunc(_canonical_json(payload).encode("utf-8"), 16))
    if not hmac.compare_digest(sig, expect):
        raise ValueError("同步签名校验失败")
    try:
        iat = int(payload.get("iat") or 0)
    except Exception as e:
        raise ValueError("同步时间戳无效") from e
    if abs(int(time.time()) - iat) > 600:
        raise ValueError("同步请求已过期，请重试")
    if int(payload.get("v") or 0) != _SCHEMA_VER:
        raise ValueError("同步协议版本不兼容")
    return payload


def _find_license_for_upsert(
    db: Session,
    *,
    code_id: str = "",
    license_key: str = "",
    phone: str = "",
) -> Optional[ToaLicense]:
    """同一授权码或同一手机号只对应一条台账，避免同步重复插入。"""
    cid = (code_id or "").strip()
    if cid:
        row = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
        if row:
            return row
    key = (license_key or "").strip().replace(" ", "")
    if key:
        kid = _code_id(key)
        if kid != cid:
            row = db.query(ToaLicense).filter(ToaLicense.code_id == kid).first()
            if row:
                return row
    ph = (phone or "").strip()
    if ph:
        return (
            db.query(ToaLicense)
            .filter(ToaLicense.phone == ph)
            .order_by(ToaLicense.id.asc())
            .first()
        )
    return None


def reconcile_non_protected(db: Session, payload: dict) -> Dict[str, Any]:
    """以终端名单为准：保留 keep 中的记录，删除其它非固定管理员。"""
    keep_cids = {str(x or "").strip() for x in (payload.get("keep_code_ids") or []) if str(x or "").strip()}
    keep_phones = {str(x or "").strip() for x in (payload.get("keep_phones") or []) if str(x or "").strip()}
    prot = _protected_admin_row(db)
    deleted = 0
    rows = db.query(ToaLicense).order_by(ToaLicense.id.asc()).all()
    for row in rows:
        if prot is not None and row.id == prot.id:
            continue
        cid = str(row.code_id or "").strip()
        phone = str(row.phone or "").strip()
        if cid and cid in keep_cids:
            continue
        if phone and phone in keep_phones:
            continue
        db.delete(row)
        deleted += 1
    db.commit()
    return {"ok": True, "op": "reconcile", "deleted": deleted}


def sync_from_terminal(db: Session, body: dict):
    """终端维护结果写入云服务台账（运营台不在此签发换码）。"""
    payload = _verify_terminal_sync(body)
    op = str(payload.get("op") or "upsert").strip().lower()
    if op == "reconcile":
        return reconcile_non_protected(db, payload)

    cid = str(payload.get("code_id") or "").strip()
    key = str(payload.get("license_key") or "").strip().replace(" ", "")
    signed: Dict[str, Any] = {}
    if key:
        ok, msg, parsed = _parse_signed_payload(key)
        if not ok or not parsed:
            raise ValueError(msg or "授权码无效")
        signed = parsed
        cid = cid or _code_id(key)
    if not cid:
        raise ValueError("缺少 code_id")

    name = str(payload.get("name") or signed.get("name") or "").strip()
    phone = str(payload.get("phone") or signed.get("phone") or "").strip()
    role = str(payload.get("role") or signed.get("role") or "user").strip() or "user"
    expire = str(payload.get("expire_date") or signed.get("exp") or "").strip()
    revoked = bool(payload.get("revoked"))
    bind = 1 if payload.get("bind_machine", True) else 0
    menus = payload.get("features") or payload.get("menus") or signed.get("menus") or ["all"]
    remark = str(payload.get("remark") or "终端同步")

    row = _find_license_for_upsert(db, code_id=cid, license_key=key, phone=phone)

    if op == "delete":
        if row is None:
            return None
        if _is_protected_admin(db, row):
            raise ValueError("固定管理员账号不能清除")
        db.delete(row)
        db.commit()
        return None

    if op == "unbind":
        if row is None:
            raise ValueError("授权记录不存在")
        if _is_protected_admin(db, row):
            raise ValueError("固定管理员账号不可解绑")
        row.activated_machine_id = ""
        row.activated_at = None
        row.remark = remark or row.remark or "终端解绑"
        db.commit()
        db.refresh(row)
        return row

    if op == "revoke":
        revoked = True

    if row is None:
        if not key:
            raise ValueError("新记录须带授权码才能同步到云服务")
        row = _store_signed_key(
            db,
            license_key=key,
            payload={
                "name": name,
                "phone": phone,
                "role": role,
                "exp": expire,
                "bind": bind,
                "menus": menus,
            },
            issued_by=None,
            remark=remark or "终端同步",
        )
    else:
        if _is_protected_admin(db, row) and (revoked or op in ("revoke", "delete")):
            raise ValueError("固定管理员账号不可停用")
        if name:
            row.name = name
        if phone:
            row.phone = phone
        if role:
            row.role = role
        if expire:
            row.expire_date = expire
        row.bind_machine = bind
        try:
            row.menus_json = json.dumps(_normalize_menus(menus), ensure_ascii=False)
        except Exception:
            pass
        if key and (row.license_key or "").strip() != key:
            new_cid = _code_id(key)
            other = (
                db.query(ToaLicense)
                .filter(ToaLicense.code_id == new_cid, ToaLicense.id != row.id)
                .first()
            )
            if other is None:
                row.code_id = new_cid
            row.license_key = key
            row.code_fingerprint = _code_fingerprint(key)
        row.remark = remark or row.remark or "终端同步"

    if revoked:
        row.status = "revoked"
        row.revoke_reason = str(payload.get("reason") or "终端停用")
        row.revoked_at = datetime.datetime.now(datetime.timezone.utc)
    elif op == "upsert" and row.status == "revoked" and not revoked:
        row.status = "active"
        row.revoke_reason = ""
        row.revoked_at = None
        row.revoked_by_id = None

    db.commit()
    db.refresh(row)
    return row


def _terminal_maintain_only() -> None:
    raise ValueError("停用 / 换机解绑 / 换码请在运营宝终端操作后同步")


def _store_signed_key(
    db: Session,
    *,
    license_key: str,
    payload: Dict[str, Any],
    issued_by: Optional[AdminUser] = None,
    remark: str = "",
    entitlement: str = "",
    plan_id: str = "",
    order_no: str = "",
) -> ToaLicense:
    key = (license_key or "").strip().replace(" ", "")
    cid = _code_id(key)
    incoming_admin = str(payload.get("role") or "").strip().lower() == "admin"
    existing = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
    if existing:
        # 再次登记管理员码时纠正被订单污染的字段
        if incoming_admin or str(existing.role or "").strip().lower() == "admin":
            dirty = False
            if str(payload.get("name") or "").strip():
                if existing.name != str(payload.get("name") or "").strip():
                    existing.name = str(payload.get("name") or "").strip()
                    dirty = True
            if existing.role != "admin":
                existing.role = "admin"
                dirty = True
            if str(existing.entitlement or "").strip().lower() != "admin":
                existing.entitlement = "admin"
                dirty = True
            if existing.order_no or existing.plan_id:
                existing.order_no = ""
                existing.plan_id = ""
                dirty = True
            if dirty:
                db.commit()
                db.refresh(existing)
        _touch_customer_for_license(db, existing)
        return existing
    phone = str(payload.get("phone") or "").strip()
    if phone:
        by_phone = (
            db.query(ToaLicense)
            .filter(ToaLicense.phone == phone)
            .order_by(ToaLicense.id.asc())
            .first()
        )
        if by_phone is not None:
            existing_admin = _is_admin_license(by_phone)
            # 固定管理员与普通用户可同号并存，禁止互相覆盖（曾导致管理员码被订单顶掉）
            merge_ok = (existing_admin and incoming_admin) or (
                not existing_admin and not incoming_admin
            )
            if merge_ok:
                by_phone.code_id = cid
                by_phone.code_fingerprint = _code_fingerprint(key)
                by_phone.license_key = key
                if str(payload.get("name") or "").strip():
                    by_phone.name = str(payload.get("name") or "").strip()
                if str(payload.get("role") or "").strip():
                    by_phone.role = str(payload.get("role") or "").strip()
                if str(payload.get("exp") or "").strip():
                    by_phone.expire_date = str(payload.get("exp") or "").strip()
                by_phone.remark = remark or by_phone.remark or ""
                if incoming_admin:
                    by_phone.entitlement = "admin"
                    by_phone.role = "admin"
                    # 管理员不挂测试订单
                    by_phone.order_no = ""
                    if not plan_id:
                        by_phone.plan_id = ""
                elif entitlement:
                    by_phone.entitlement = entitlement
                if plan_id and not incoming_admin:
                    by_phone.plan_id = plan_id
                if order_no and not incoming_admin:
                    by_phone.order_no = order_no
                db.commit()
                db.refresh(by_phone)
                _touch_customer_for_license(db, by_phone)
                return by_phone

    exp = str(payload.get("exp") or "")
    try:
        if datetime.datetime.strptime(exp[:10], "%Y-%m-%d").date() < _today():
            raise ValueError("授权码已过期，无法登记")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("授权码缺少有效期") from e

    row = ToaLicense(
        code_id=cid,
        code_fingerprint=_code_fingerprint(key),
        license_key=key,
        name=str(payload.get("name") or "").strip(),
        phone=str(payload.get("phone") or "").strip(),
        role=str(payload.get("role") or "user").strip() or "user",
        menus_json=json.dumps(payload.get("menus") or ["all"], ensure_ascii=False),
        expire_date=exp,
        status="active",
        bind_machine=1 if int(payload.get("bind") or 0) else 1,
        remark=remark or "",
        entitlement=entitlement
        or ("admin" if incoming_admin else _infer_entitlement_from_remark(remark)),
        plan_id=plan_id,
        order_no=order_no,
        issued_by_id=issued_by.id if issued_by else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _touch_customer_for_license(db, row)
    return row


def _touch_customer_for_license(db: Session, row: ToaLicense) -> None:
    """授权落库后同步用户主数据（账号管理可见）。"""
    try:
        from services import customer_service as cust

        cust.upsert_from_license_row(db, row)
    except Exception:
        # 不阻断发卡主路径
        pass


# 与终端 config/admin_bootstrap_code.txt 同源（固定管理员；发版包不含此文件）
_BOOTSTRAP_ADMIN_KEY = (
    "TOA2-eyJiaW5kIjowLCJleHAiOiIyMDM2LTA4LTExIiwiaWF0IjoxNzg2Njg5Mzc1LCJtZW51cyI6WyJhbGwiXSwi"
    "bmFtZSI6IueuoeeQhuWRmCIsIm5vbmNlIjoiY2ZlODBlZDA3NTI4Yjg2ZiIsInBob25lIjoiMTIzNDU2Nzg5MDEi"
    "LCJyb2xlIjoiYWRtaW4iLCJ2IjoyfQ.E-bELhivS2H8fVKlIUKWQA"
)


def ensure_bootstrap_admin_license(db: Session) -> Optional[ToaLicense]:
    """启动时确保固定管理员授权在云台账；可被 TOA_CLOUD_BOOTSTRAP_ADMIN=0 关闭。"""
    import os

    if os.environ.get("TOA_CLOUD_BOOTSTRAP_ADMIN", "1").strip() == "0":
        return _protected_admin_row(db)
    if _protected_admin_row(db) is not None:
        # 仍回填用户表
        prot = _protected_admin_row(db)
        if prot:
            _touch_customer_for_license(db, prot)
        return prot
    key = os.environ.get("TOA_ADMIN_BOOTSTRAP_KEY", "").strip() or _BOOTSTRAP_ADMIN_KEY
    try:
        row = register_signed_license(db, key)
        if row and not str(row.entitlement or "").strip():
            row.entitlement = "admin"
            row.role = "admin"
            row.remark = (row.remark or "") or "bootstrap-admin"
            db.commit()
            db.refresh(row)
        _touch_customer_for_license(db, row)
        return row
    except Exception:
        return _protected_admin_row(db)


def sync_all_licenses_to_customers(db: Session) -> int:
    """把已有授权回填到用户表。"""
    n = 0
    for row in db.query(ToaLicense).order_by(ToaLicense.id.asc()).all():
        try:
            from services import customer_service as cust

            if cust.upsert_from_license_row(db, row):
                n += 1
        except Exception:
            continue
    return n


def get_license(db: Session, license_id: int) -> Optional[ToaLicense]:
    return db.query(ToaLicense).filter(ToaLicense.id == license_id).first()


def _is_admin_license(row: ToaLicense) -> bool:
    return str(getattr(row, "role", None) or "").strip().lower() == "admin"


def _protected_admin_row(db: Session) -> Optional[ToaLicense]:
    """唯一不可清除的管理员：优先「管理员」占位，否则取最早一条 admin。"""
    rows = db.query(ToaLicense).order_by(ToaLicense.id.asc()).all()
    named: List[ToaLicense] = []
    admins: List[ToaLicense] = []
    for row in rows:
        if not _is_admin_license(row):
            continue
        admins.append(row)
        if str(row.name or "").strip() in ("管理员", "admin"):
            named.append(row)
    if named:
        return named[0]
    return admins[0] if admins else None


def protected_admin_id(db: Session) -> Optional[int]:
    row = _protected_admin_row(db)
    return row.id if row else None


def _is_protected_admin(db: Session, row: Optional[ToaLicense]) -> bool:
    if row is None:
        return False
    prot = _protected_admin_row(db)
    return prot is not None and prot.id == row.id


def _assert_admin_mutable(db: Session, row: ToaLicense, action: str) -> None:
    """固定管理员锁定，禁止停用/换码/解绑/清除，避免误操作锁死。"""
    if _is_protected_admin(db, row):
        raise ValueError(f"固定管理员账号不可{action}")


def delete_license(db: Session, license_id: int) -> None:
    row = get_license(db, license_id)
    if not row:
        raise ValueError("授权记录不存在")
    _assert_admin_mutable(db, row, "清除")
    db.delete(row)
    db.commit()


def clear_other_licenses(db: Session) -> Dict[str, Any]:
    """清除除固定管理员外的全部授权账号。"""
    prot = _protected_admin_row(db)
    query = db.query(ToaLicense)
    if prot is not None:
        query = query.filter(ToaLicense.id != prot.id)
    rows = query.all()
    deleted = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return {
        "ok": True,
        "deleted": deleted,
        "kept_id": prot.id if prot else None,
        "kept_name": (prot.name or "") if prot else "",
        "kept_phone": (prot.phone or "") if prot else "",
    }


def revoke_license(
    db: Session,
    license_id: int,
    *,
    revoked_by: Optional[AdminUser] = None,
) -> ToaLicense:
    row = get_license(db, license_id)
    if not row:
        raise ValueError("授权记录不存在")
    if row.status == "revoked":
        return row
    _assert_admin_mutable(db, row, "停用")
    row.status = "revoked"
    row.revoke_reason = "管理员停用"
    row.revoked_at = datetime.datetime.now(datetime.timezone.utc)
    row.revoked_by_id = revoked_by.id if revoked_by else None
    db.commit()
    db.refresh(row)
    return row


def _features_from_row(row: ToaLicense) -> List[str]:
    if str(row.role or "").strip().lower() == "admin":
        return ["all"]
    try:
        parsed = json.loads(row.menus_json or "[]")
        if isinstance(parsed, list) and parsed:
            from services import pack_service

            expanded = pack_service.expand_features(parsed)
            if expanded:
                return _normalize_menus(expanded)
    except Exception:
        pass
    return ["all"]


def _effective_status(row: ToaLicense) -> str:
    if row.status == "revoked":
        return "revoked"
    try:
        if datetime.datetime.strptime(row.expire_date[:10], "%Y-%m-%d").date() < _today():
            return "expired"
    except Exception:
        pass
    return "active"


PLATFORM_REMARK_TAG = "platform"


def trial_settings() -> Dict[str, Any]:
    """读取 cloud/config/commerce.yml 的 trial 段（试用与巨龙预发共用）。"""
    from pathlib import Path

    import yaml

    commerce_path = Path(__file__).resolve().parents[2] / "config" / "commerce.yml"
    trial_cfg: Dict[str, Any] = {}
    if commerce_path.is_file():
        data = yaml.safe_load(commerce_path.read_text(encoding="utf-8")) or {}
        trial_cfg = data.get("trial") or {}
    return {
        "enabled": trial_cfg.get("enabled") is not False,
        "days": int(trial_cfg.get("days") or 14),
        "pack_id": str(trial_cfg.get("pack_id") or "tiyan").strip() or "tiyan",
    }


def is_unclaimed_platform_code(row: ToaLicense) -> bool:
    """巨龙预发且从未在任何机器激活过的码。"""
    remark = str(row.remark or "")
    return PLATFORM_REMARK_TAG in remark.split("|") and not (row.activated_machine_id or "").strip()


def _bind_and_describe(
    db: Session, row: ToaLicense, machine_id: str, *, pack_id: str, days: int
) -> Dict[str, Any]:
    now = datetime.datetime.now(datetime.timezone.utc)
    row.activated_machine_id = machine_id
    row.activated_at = now
    row.last_check_at = now
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "license_key": row.license_key,
        "expire_date": row.expire_date,
        "name": row.name,
        "phone": row.phone,
        "pack_id": pack_id,
        "trial_days": days,
        "code_id": row.code_id,
        "entitlement": _infer_entitlement(row),
        "features": _features_from_row(row),
    }


def start_trial(
    db: Session,
    *,
    phone: str,
    machine_id: str,
    name: str = "",
    app_version: str = "",
) -> Dict[str, Any]:
    """手机号试用：每手机/每机器限一次；签发短期码并绑定。"""
    mid = (machine_id or "").strip()
    phone = str(phone or "").strip()
    if not mid:
        raise ValueError("缺少机器 ID")
    if not phone or not (len(phone) == 11 and phone.isdigit()):
        raise ValueError("请填写 11 位手机号")

    trial = trial_settings()
    if not trial["enabled"]:
        raise ValueError("试用入口已关闭，请联系运营台获取授权码")

    days = trial["days"]
    pack_id = trial["pack_id"]
    display = str(name or "").strip() or f"试用用户{phone[-4:]}"

    existing_phone = (
        db.query(ToaLicense)
        .filter(ToaLicense.phone == phone, ToaLicense.status != "revoked")
        .order_by(ToaLicense.id.desc())
        .first()
    )
    if existing_phone is not None:
        st = _effective_status(existing_phone)
        if st == "active" and is_unclaimed_platform_code(existing_phone):
            # 巨龙注册时预发、尚未激活的码：本机直接认领，路径 B 与路径 A 汇合
            return _bind_and_describe(db, existing_phone, mid, pack_id=pack_id, days=days)
        if st == "active":
            raise ValueError("该手机号已有有效授权，请直接使用授权码登录或续费")
        remark = str(existing_phone.remark or "")
        never_used = is_unclaimed_platform_code(existing_phone)
        if not never_used and ("trial" in remark.lower() or "试用" in remark):
            raise ValueError("该手机号已使用过试用，请购买正式授权")

    existing_machine = (
        db.query(ToaLicense)
        .filter(ToaLicense.activated_machine_id == mid, ToaLicense.status != "revoked")
        .order_by(ToaLicense.id.desc())
        .first()
    )
    if existing_machine is not None:
        remark = str(existing_machine.remark or "")
        if "trial" in remark.lower() or "试用" in remark:
            raise ValueError("本机已使用过试用，请购买正式授权")

    from services import pack_service

    menus = pack_service.pack_menus_for_license(pack_id, db=db)
    code, payload = issue_code(
        name=display,
        phone=phone,
        days=days,
        role="user",
        menus=menus,
        bind_machine=True,
    )
    row = _store_signed_key(
        db,
        license_key=code,
        payload=payload,
        issued_by=None,
        remark=f"trial|{pack_id}|v{app_version}",
        entitlement="trial",
        plan_id=pack_id,
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    row.activated_machine_id = mid
    row.activated_at = now
    row.last_check_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "license_key": code,
        "expire_date": row.expire_date,
        "name": row.name,
        "phone": row.phone,
        "pack_id": pack_id,
        "trial_days": days,
        "code_id": row.code_id,
        "entitlement": "trial",
        "features": _features_from_row(row),
    }


def activate_online(
    db: Session,
    *,
    license_key: str,
    machine_id: str,
    app_version: str = "",
) -> Dict[str, Any]:
    """TOA 客户端激活：验签 → 必须已在云服务台账登记 → 绑定机器。"""
    mid = (machine_id or "").strip()
    if not mid:
        raise ValueError("缺少 machine_id")
    ok, msg, payload = _parse_signed_payload(license_key)
    if not ok or not payload:
        raise ValueError(msg or "授权码无效")

    key = (license_key or "").strip().replace(" ", "")
    cid = _code_id(key)
    row = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
    if row is None:
        raise ValueError("授权码未在云服务登记，请先在运营台或运营宝签发并同步")

    # 防窜改：库中明文与请求码必须一致
    if (row.license_key or "").strip().replace(" ", "") != key:
        raise ValueError("授权码与登记记录不一致")

    status = _effective_status(row)
    if status == "revoked":
        raise ValueError("授权已停用")
    if status == "expired":
        raise ValueError("授权已到期")

    if row.bind_machine:
        bound = (row.activated_machine_id or "").strip()
        if bound and bound != mid:
            raise ValueError("该授权码已绑定其它电脑，请联系管理员换机解绑")

    now = datetime.datetime.now(datetime.timezone.utc)
    row.activated_machine_id = mid
    row.activated_at = now
    row.last_check_at = now
    db.commit()
    db.refresh(row)

    return {
        "status": "active",
        "code_id": row.code_id,
        "name": row.name,
        "phone": row.phone,
        "role": row.role or "user",
        "expire_date": row.expire_date,
        "features": _features_from_row(row),
        "entitlement": _infer_entitlement(row),
        "plan_id": _plan_id_from_row(row),
        "order_no": str(getattr(row, "order_no", None) or "").strip(),
        "machine_id": mid,
    }


def unbind_machine(db: Session, license_id: int) -> ToaLicense:
    """清除机器绑定，便于换机重新激活。"""
    row = get_license(db, license_id)
    if not row:
        raise ValueError("授权记录不存在")
    if row.status == "revoked":
        raise ValueError("已停用，无法解绑")
    _assert_admin_mutable(db, row, "换机解绑")
    row.activated_machine_id = ""
    row.activated_at = None
    db.commit()
    db.refresh(row)
    return row


def reissue_license(
    db: Session,
    license_id: int,
    *,
    days: Optional[int] = None,
    issued_by: Optional[AdminUser] = None,
) -> ToaLicense:
    """更换授权码：旧码立即失效，同记录写入新码并清除机器绑定。

    默认保留原到期日；若传入 days，则从今天起重新计算有效期。
    """
    row = get_license(db, license_id)
    if not row:
        raise ValueError("授权记录不存在")
    if row.status == "revoked":
        raise ValueError("已停用，无法换码；请重新签发")
    _assert_admin_mutable(db, row, "更换授权码")

    menus = ["all"]
    try:
        parsed = json.loads(row.menus_json or "[]")
        if isinstance(parsed, list) and parsed:
            menus = parsed
    except Exception:
        pass

    issue_kwargs: Dict[str, Any] = {
        "name": row.name,
        "phone": row.phone,
        "role": row.role or "user",
        "menus": menus,
        "bind_machine": bool(row.bind_machine),
    }
    if days is not None:
        try:
            d = int(days)
        except Exception as e:
            raise ValueError("有效期天数无效") from e
        if d <= 0:
            raise ValueError("有效期天数必须大于 0")
        issue_kwargs["days"] = d
    else:
        issue_kwargs["expire_date"] = row.expire_date or ""

    code, payload = issue_code(**issue_kwargs)
    new_cid = _code_id(code)
    clash = db.query(ToaLicense).filter(ToaLicense.code_id == new_cid).first()
    if clash and clash.id != row.id:
        raise ValueError("授权码冲突，请重试")

    row.code_id = new_cid
    row.code_fingerprint = _code_fingerprint(code)
    row.license_key = code
    row.expire_date = str(payload.get("exp") or row.expire_date)
    row.status = "active"
    row.activated_machine_id = ""
    row.activated_at = None
    row.revoke_reason = ""
    row.revoked_at = None
    row.revoked_by_id = None
    if issued_by:
        row.issued_by_id = issued_by.id
    note = "已更换授权码"
    prev = (row.remark or "").strip()
    row.remark = f"{prev}；{note}" if prev and note not in prev else (prev or note)
    db.commit()
    db.refresh(row)
    return row


def check_online(
    db: Session,
    *,
    code_id: str = "",
    license_key: str = "",
    machine_id: str = "",
) -> Dict[str, Any]:
    """TOA 启动/心跳校验。"""
    mid = (machine_id or "").strip()
    cid = (code_id or "").strip()
    if not cid and license_key:
        cid = _code_id((license_key or "").strip().replace(" ", ""))
    if not cid:
        raise ValueError("缺少 code_id")

    row = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
    if row is None:
        return {"status": "missing", "message": "授权未在云服务登记", "code_id": cid}

    status = _effective_status(row)
    row.last_check_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()

    if status == "revoked":
        return {
            "status": "revoked",
            "message": "授权已停用",
            "code_id": row.code_id,
            "name": row.name,
            "phone": row.phone,
            "role": row.role or "user",
            "expire_date": row.expire_date,
        }
    if status == "expired":
        return {
            "status": "expired",
            "message": "授权已到期",
            "code_id": row.code_id,
            "name": row.name,
            "phone": row.phone,
            "role": row.role or "user",
            "expire_date": row.expire_date,
        }

    if row.bind_machine and mid:
        bound = (row.activated_machine_id or "").strip()
        if bound and bound != mid:
            return {
                "status": "bound_elsewhere",
                "message": "该授权码已绑定其它电脑",
                "code_id": row.code_id,
                "name": row.name,
                "phone": row.phone,
                "role": row.role or "user",
                "expire_date": row.expire_date,
            }

    return {
        "status": "active",
        "code_id": row.code_id,
        "name": row.name,
        "phone": row.phone,
        "role": row.role or "user",
        "expire_date": row.expire_date,
        "features": _features_from_row(row),
        "message": "ok",
    }


def assert_catalog_publisher(db: Session, *, license_key: str, machine_id: str) -> ToaLicense:
    """终端管理员发布菜单目录：须 admin 授权码 + 本机 machine_id。"""
    mid = (machine_id or "").strip()
    if not mid:
        raise ValueError("缺少 machine_id")
    key = (license_key or "").strip().replace(" ", "")
    if not key:
        raise ValueError("缺少授权码")
    ok, msg, _payload = _parse_signed_payload(license_key)
    if not ok:
        raise ValueError(msg or "授权码无效")
    cid = _code_id(key)
    row = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
    if row is None:
        raise ValueError("授权码未在云服务登记")
    if (row.license_key or "").strip().replace(" ", "") != key:
        raise ValueError("授权码与登记记录不一致")
    if not _is_admin_license(row):
        raise ValueError("仅终端管理员（admin 授权）可同步菜单目录")
    status = _effective_status(row)
    if status == "revoked":
        raise ValueError("授权已停用")
    if status == "expired":
        raise ValueError("授权已到期")
    bound = (row.activated_machine_id or "").strip()
    if bound and bound != mid:
        raise ValueError("该管理员授权已绑定其它电脑")
    if not bound:
        row.activated_machine_id = mid
        row.activated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    return row
