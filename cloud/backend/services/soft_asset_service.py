# -*- coding: utf-8 -*-
"""办公插件软资产：投稿、审核、上架、流水（无偿流通）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from config import DATA_DIR
from models import ToaMenuModule, ToaSoftAsset, ToaSoftAssetEvent
from services import customer_service as cust

STORAGE_ROOT = DATA_DIR / "soft_assets"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def _dump_list(items: list | None) -> str:
    return json.dumps(list(items or []), ensure_ascii=False)


def ensure_storage() -> Path:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return STORAGE_ROOT


def asset_to_dict(
    row: ToaSoftAsset,
    *,
    public: bool = False,
    include_download: bool = False,
) -> dict[str, Any]:
    caps = _parse_list(row.capabilities_json)
    ints = _parse_list(row.integrations_json)
    out: dict[str, Any] = {
        "id": row.id,
        "asset_kind": row.asset_kind or "extension.pack",
        "plugin_id": row.plugin_id or "",
        "name": row.name or "",
        "description": row.description or "",
        "version": row.version or "",
        "group": row.group_id or "business",
        "author": row.author or "",
        "capabilities": caps,
        "integrations": ints,
        "content_sha256": row.content_sha256 or "",
        "audit_ok": bool(row.audit_ok),
        "recommended": bool(getattr(row, "recommended", False)),
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else "",
    }
    if not public:
        out.update(
            {
                "audit_summary": row.audit_summary or "",
                "review_status": row.review_status or "",
                "reject_reason": row.reject_reason or "",
                "listed": bool(row.listed),
                "enabled": bool(row.enabled),
                "customer_id": row.customer_id,
                "storage_path": row.storage_path or "",
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else "",
                "reviewed_by_id": row.reviewed_by_id,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
        )
    else:
        out["listed"] = True
        out["enabled"] = True
    if include_download:
        out["download_path"] = f"/api/toa-soft-assets/{row.id}/download"
    return out


def event_to_dict(row: ToaSoftAssetEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_kind": row.event_kind or "",
        "asset_id": row.asset_id,
        "plugin_id": row.plugin_id or "",
        "version": row.version or "",
        "customer_id": row.customer_id,
        "machine_id": row.machine_id or "",
        "result": row.result or "",
        "detail": row.detail or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def record_event(
    db: Session,
    *,
    event_kind: str,
    asset: ToaSoftAsset | None = None,
    plugin_id: str = "",
    version: str = "",
    customer_id: int | None = None,
    machine_id: str = "",
    result: str = "ok",
    detail: str = "",
) -> ToaSoftAssetEvent:
    ev = ToaSoftAssetEvent(
        event_kind=event_kind,
        asset_id=asset.id if asset else None,
        plugin_id=plugin_id or (asset.plugin_id if asset else ""),
        version=version or (asset.version if asset else ""),
        customer_id=customer_id,
        machine_id=machine_id or "",
        result=result,
        detail=(detail or "")[:500],
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _assert_not_official_id(db: Session, plugin_id: str) -> None:
    pid = (plugin_id or "").strip()
    if not pid:
        raise ValueError("缺少 plugin_id")
    hit = db.query(ToaMenuModule).filter(ToaMenuModule.id == pid).first()
    if hit:
        raise ValueError(f"plugin_id 与官方模块冲突：{pid}")


def submit_extension_pack(
    db: Session,
    *,
    license_key: str = "",
    machine_id: str = "",
    meta: dict[str, Any],
    zip_bytes: bytes,
) -> ToaSoftAsset:
    """投稿扩展包。无偿流通：无需授权码；有码则关联社区账号。"""
    customer = None
    key = (license_key or "").strip()
    mid = (machine_id or "").strip()
    if key:
        try:
            customer, _lic = cust.resolve_customer_from_license(
                db, license_key=key, machine_id=mid
            )
        except ValueError:
            # 码无效时仍允许匿名投稿（前期无偿开放）
            customer = None

    kind = str(meta.get("asset_kind") or "extension.pack").strip()
    if kind != "extension.pack":
        raise ValueError("仅支持 extension.pack")
    plugin_id = str(meta.get("plugin_id") or "").strip()
    name = str(meta.get("name") or plugin_id).strip()
    version = str(meta.get("version") or "0.1.0").strip()
    if not plugin_id or not name:
        raise ValueError("meta 缺少 plugin_id / name")
    if not meta.get("audit_ok"):
        raise ValueError("本机审计未通过，拒绝投稿")
    if not zip_bytes:
        raise ValueError("缺少扩展包文件")
    _assert_not_official_id(db, plugin_id)

    author = str(meta.get("author") or "").strip()
    if not author and customer is not None:
        author = str(customer.display_name or "").strip()
    if not author:
        author = "匿名用户"

    sha = str(meta.get("content_sha256") or "").strip()
    ensure_storage()
    asset = ToaSoftAsset(
        asset_kind="extension.pack",
        plugin_id=plugin_id,
        name=name,
        description=str(meta.get("description") or "")[:500],
        version=version,
        group_id=str(meta.get("group") or "business")[:32],
        author=author[:100],
        capabilities_json=_dump_list(meta.get("capabilities") or ["l1"]),
        integrations_json=_dump_list(meta.get("integrations") or []),
        content_sha256=sha,
        audit_ok=True,
        audit_summary=str(meta.get("audit_summary") or "")[:2000],
        review_status="submitted",
        listed=False,
        enabled=True,
        customer_id=customer.id if customer is not None else None,
        submitted_at=_now(),
    )
    db.add(asset)
    db.flush()
    dest = ensure_storage() / f"{asset.id}_{plugin_id}.toa-ext.zip"
    dest.write_bytes(zip_bytes)
    asset.storage_path = str(dest)
    db.commit()
    db.refresh(asset)
    record_event(
        db,
        event_kind="upload",
        asset=asset,
        customer_id=customer.id if customer is not None else None,
        machine_id=mid,
        result="ok",
        detail="submitted" if customer else "submitted_anonymous",
    )
    return asset


def list_assets_admin(
    db: Session,
    *,
    status: str = "",
    q: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = db.query(ToaSoftAsset)
    st = (status or "").strip()
    if st:
        query = query.filter(ToaSoftAsset.review_status == st)
    qq = (q or "").strip()
    if qq:
        like = f"%{qq}%"
        query = query.filter(
            (ToaSoftAsset.name.like(like))
            | (ToaSoftAsset.plugin_id.like(like))
            | (ToaSoftAsset.author.like(like))
        )
    rows = query.order_by(ToaSoftAsset.id.desc()).limit(max(1, min(limit, 500))).all()
    return [asset_to_dict(r) for r in rows]


def list_public_catalog(
    db: Session,
    *,
    q: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """终端公示：已上架 + 启用 + approved。"""
    query = db.query(ToaSoftAsset).filter(
        ToaSoftAsset.asset_kind == "extension.pack",
        ToaSoftAsset.review_status == "approved",
        ToaSoftAsset.listed.is_(True),
        ToaSoftAsset.enabled.is_(True),
    )
    qq = (q or "").strip()
    if qq:
        like = f"%{qq}%"
        query = query.filter(
            (ToaSoftAsset.name.like(like))
            | (ToaSoftAsset.description.like(like))
            | (ToaSoftAsset.author.like(like))
            | (ToaSoftAsset.plugin_id.like(like))
        )
    rows = query.order_by(
        ToaSoftAsset.recommended.desc(),
        ToaSoftAsset.updated_at.desc(),
    ).limit(max(1, min(limit, 200))).all()
    return [asset_to_dict(r, public=True, include_download=True) for r in rows]


def get_asset(db: Session, asset_id: int) -> ToaSoftAsset | None:
    return db.query(ToaSoftAsset).filter(ToaSoftAsset.id == int(asset_id)).first()


def review_asset(
    db: Session,
    asset_id: int,
    *,
    action: str,
    reject_reason: str = "",
    admin_id: int | None = None,
    name: str | None = None,
    description: str | None = None,
) -> ToaSoftAsset:
    """人审：approve / reject / list / unlist / enable / disable / recommend / unrecommend。"""
    row = get_asset(db, asset_id)
    if not row:
        raise ValueError("插件不存在")
    act = (action or "").strip().lower()
    if name is not None:
        row.name = str(name).strip()[:100] or row.name
    if description is not None:
        row.description = str(description).strip()[:500]

    if act == "approve":
        _assert_not_official_id(db, row.plugin_id)
        row.review_status = "approved"
        row.listed = True
        row.enabled = True
        row.reject_reason = ""
        row.reviewed_at = _now()
        row.reviewed_by_id = admin_id
    elif act == "reject":
        row.review_status = "rejected"
        row.listed = False
        row.recommended = False
        row.reject_reason = (reject_reason or "未通过审核")[:500]
        row.reviewed_at = _now()
        row.reviewed_by_id = admin_id
    elif act == "list":
        if row.review_status != "approved":
            raise ValueError("仅已通过审核的插件可上架")
        row.listed = True
        row.review_status = "approved"
    elif act == "unlist":
        row.listed = False
        row.recommended = False
        row.review_status = "delisted"
    elif act == "enable":
        row.enabled = True
    elif act == "disable":
        row.enabled = False
        row.recommended = False
    elif act == "recommend":
        if row.review_status != "approved" or not row.listed or not row.enabled:
            raise ValueError("仅已上架且启用的插件可设为推荐")
        row.recommended = True
    elif act == "unrecommend":
        row.recommended = False
    else:
        raise ValueError(f"未知操作：{action}")
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def resolve_downloadable(
    db: Session,
    asset_id: int,
    *,
    license_key: str = "",
    machine_id: str = "",
    require_identity: bool = False,
) -> tuple[ToaSoftAsset, Path]:
    """取可下载包。默认无门槛（无偿流通）；require_identity 时才校验授权。"""
    customer_id = None
    mid = (machine_id or "").strip()
    key = (license_key or "").strip()
    if require_identity or key:
        customer, _ = cust.resolve_customer_from_license(
            db, license_key=key, machine_id=mid
        )
        customer_id = customer.id
    row = get_asset(db, asset_id)
    if not row:
        raise ValueError("插件不存在")
    if row.review_status != "approved" or not row.listed or not row.enabled:
        raise ValueError("插件未上架或已停用")
    path = Path(row.storage_path or "")
    if not path.is_file():
        raise ValueError("插件包文件缺失")
    record_event(
        db,
        event_kind="download",
        asset=row,
        customer_id=customer_id,
        machine_id=mid,
        result="ok",
        detail="public" if customer_id is None else "identified",
    )
    return row, path


def list_events(
    db: Session,
    *,
    event_kind: str = "",
    customer_id: int | None = None,
    plugin_id: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = db.query(ToaSoftAssetEvent)
    if event_kind:
        query = query.filter(ToaSoftAssetEvent.event_kind == event_kind)
    if customer_id:
        query = query.filter(ToaSoftAssetEvent.customer_id == int(customer_id))
    if plugin_id:
        query = query.filter(ToaSoftAssetEvent.plugin_id == plugin_id.strip())
    rows = query.order_by(ToaSoftAssetEvent.id.desc()).limit(max(1, min(limit, 500))).all()
    return [event_to_dict(r) for r in rows]


def delete_asset_files(row: ToaSoftAsset) -> None:
    try:
        p = Path(row.storage_path or "")
        if p.is_file():
            p.unlink(missing_ok=True)
    except Exception:
        pass
