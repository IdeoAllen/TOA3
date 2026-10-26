# -*- coding: utf-8 -*-
"""功能包 API（运营台维护 SKU + 定价）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from deps import require_perm
from models import AdminUser
from services import pack_service as yaml_packs
from services import product_catalog_service as cat

router = APIRouter(prefix="/api/toa/packs", tags=["toa-packs"])


def _use_db(db: Session) -> bool:
    from models import ToaFeaturePack

    return db.query(ToaFeaturePack).count() > 0


@router.get("")
def list_public_packs(sellable: bool = True, db: Session = Depends(get_db)):
    if _use_db(db):
        rows = cat.list_packs_db(db, sellable_only=sellable, include_free=not sellable)
    else:
        rows = yaml_packs.list_packs(sellable_only=sellable, include_free=not sellable)
    return {"commerce": yaml_packs.commerce_summary(), "packs": rows, "plans": rows}


@router.get("/catalog")
def full_catalog(
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    if _use_db(db):
        rows = cat.list_packs_db(db, sellable_only=False, include_free=True, active_only=False)
        meta = cat.catalog_meta_db(db)
        warnings = [
            {"pack_id": r.get("id"), "unknown": (r.get("menu_validation") or {}).get("unknown") or []}
            for r in rows
            if not (r.get("menu_validation") or {}).get("ok", True)
        ]
    else:
        from services import menu_catalog_service as menu_cat

        rows = yaml_packs.list_packs(sellable_only=False, include_free=True)
        rows = [menu_cat.enrich_pack(r) for r in rows]
        meta = menu_cat.catalog_meta()
        warnings = [
            {"pack_id": r.get("id"), "unknown": (r.get("menu_validation") or {}).get("unknown") or []}
            for r in rows
            if not (r.get("menu_validation") or {}).get("ok", True)
        ]
    return {
        "commerce": yaml_packs.commerce_summary(),
        "menu_catalog": meta,
        "packs": rows,
        "validation_warnings": warnings,
        "source": "database" if _use_db(db) else "yaml",
    }


@router.get("/{pack_id}")
def get_pack(pack_id: str, db: Session = Depends(get_db)):
    row = cat.get_pack_db(db, pack_id) if _use_db(db) else yaml_packs.get_pack(pack_id)
    if not row:
        raise HTTPException(404, "产品方案不存在")
    return row


@router.put("/{pack_id}")
def save_pack(
    pack_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    body = dict(data or {})
    body["id"] = pack_id
    try:
        return cat.save_pack_db(db, pack_id, body, operator=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("")
def create_pack(
    data: dict,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    pack_id = str((data or {}).get("id") or "").strip()
    if not pack_id:
        raise HTTPException(400, "请提供功能包 id")
    try:
        return cat.save_pack_db(db, pack_id, data or {}, operator=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{pack_id}/disable")
def disable_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    if not _use_db(db):
        raise HTTPException(400, "请先同步产品目录至数据库")
    try:
        return cat.disable_pack_db(db, pack_id, operator=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{pack_id}/enable")
def enable_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    if not _use_db(db):
        raise HTTPException(400, "请先同步产品目录至数据库")
    try:
        return cat.enable_pack_db(db, pack_id, operator=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{pack_id}")
def clear_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    if not _use_db(db):
        raise HTTPException(400, "请先同步产品目录至数据库")
    try:
        return cat.clear_pack_db(db, pack_id, operator=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
