# -*- coding: utf-8 -*-
"""产品方案 API（与 /api/toa/packs 同源；pack_id 为兼容别名 = plan_id）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from deps import require_perm
from models import AdminUser
from routers.packs import _use_db
from services import pack_service as yaml_packs
from services import product_catalog_service as cat

router = APIRouter(prefix="/api/toa/plans", tags=["toa-product-plans"])


def _plan_response(rows: list[dict], commerce: dict) -> dict:
    return {
        "commerce": commerce,
        "plans": rows,
        "packs": rows,
    }


@router.get("")
def list_public_plans(sellable: bool = True, db: Session = Depends(get_db)):
    if _use_db(db):
        rows = cat.list_packs_db(db, sellable_only=sellable, include_free=not sellable)
    else:
        rows = yaml_packs.list_packs(sellable_only=sellable, include_free=not sellable)
    return _plan_response(rows, yaml_packs.commerce_summary())


@router.get("/catalog")
def full_plan_catalog(
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    if _use_db(db):
        rows = cat.list_packs_db(db, sellable_only=False, include_free=True)
        meta = cat.catalog_meta_db(db)
        warnings = [
            {"plan_id": r.get("id"), "pack_id": r.get("id"), "unknown": (r.get("menu_validation") or {}).get("unknown") or []}
            for r in rows
            if not (r.get("menu_validation") or {}).get("ok", True)
        ]
    else:
        from services import menu_catalog_service as menu_cat

        rows = yaml_packs.list_packs(sellable_only=False, include_free=True)
        rows = [menu_cat.enrich_pack(r) for r in rows]
        meta = menu_cat.catalog_meta()
        warnings = [
            {"plan_id": r.get("id"), "pack_id": r.get("id"), "unknown": (r.get("menu_validation") or {}).get("unknown") or []}
            for r in rows
            if not (r.get("menu_validation") or {}).get("ok", True)
        ]
    return {
        "commerce": yaml_packs.commerce_summary(),
        "menu_catalog": meta,
        "plans": rows,
        "packs": rows,
        "validation_warnings": warnings,
        "source": "database" if _use_db(db) else "yaml",
    }


@router.get("/{plan_id}")
def get_plan(plan_id: str, db: Session = Depends(get_db)):
    row = cat.get_pack_db(db, plan_id) if _use_db(db) else yaml_packs.get_pack(plan_id)
    if not row:
        raise HTTPException(404, "产品方案不存在")
    return row
