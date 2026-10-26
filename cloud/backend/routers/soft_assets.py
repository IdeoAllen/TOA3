# -*- coding: utf-8 -*-
"""办公插件软资产 API：终端投稿/目录/下载 + 运营台审核控制。"""
from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from deps import require_perm
from models import AdminUser
from services import soft_asset_service as soft

router = APIRouter(prefix="/api/toa-soft-assets", tags=["toa-soft-assets"])


@router.get("")
def list_public(
    kind: str = Query("extension.pack"),
    status: str = Query("approved"),
    q: str = Query(""),
    db: Session = Depends(get_db),
):
    """终端公示目录（无偿·只读）。仅返回已上架且启用。"""
    _ = kind, status  # 契约兼容；公示固定 approved+listed+enabled
    return {"items": soft.list_public_catalog(db, q=q)}


@router.get("/admin/list")
def admin_list(
    status: str = Query(""),
    q: str = Query(""),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    return {"items": soft.list_assets_admin(db, status=status, q=q)}


@router.get("/admin/events")
def admin_events(
    event_kind: str = Query(""),
    customer_id: int | None = Query(None),
    plugin_id: str = Query(""),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_license:read", "toa_license:write")),
):
    return {
        "items": soft.list_events(
            db, event_kind=event_kind, customer_id=customer_id, plugin_id=plugin_id
        )
    }


@router.post("/submit")
async def submit_pack(
    license_key: str = Form(""),
    machine_id: str = Form(""),
    meta_json: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """终端投稿（无偿开放，无需授权码；有码则关联账号）。"""
    try:
        meta = json.loads(meta_json or "{}")
        if not isinstance(meta, dict):
            raise ValueError("meta_json 须为对象")
        raw = await file.read()
        asset = soft.submit_extension_pack(
            db,
            license_key=license_key,
            machine_id=machine_id,
            meta=meta,
            zip_bytes=raw,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except json.JSONDecodeError as e:
        raise HTTPException(400, "meta_json 无效") from e
    return {"ok": True, "asset": soft.asset_to_dict(asset)}


@router.post("/submit-json")
def submit_pack_json(data: dict, db: Session = Depends(get_db)):
    """JSON 投稿（zip_base64），便于桌面 urllib 客户端。无偿开放。"""
    body = data or {}
    try:
        meta = body.get("meta") or {}
        if not isinstance(meta, dict):
            raise ValueError("meta 须为对象")
        b64 = str(body.get("zip_base64") or "").strip()
        if not b64:
            raise ValueError("缺少 zip_base64")
        raw = base64.b64decode(b64)
        asset = soft.submit_extension_pack(
            db,
            license_key=str(body.get("license_key") or ""),
            machine_id=str(body.get("machine_id") or ""),
            meta=meta,
            zip_bytes=raw,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(400, f"投稿失败：{e}") from e
    return {"ok": True, "asset": soft.asset_to_dict(asset)}


@router.post("/{asset_id}/review")
def review(
    asset_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_license:write")),
):
    """人审：approve/reject/list/unlist/enable/disable。Agent 不得调用自批。"""
    body = data or {}
    try:
        row = soft.review_asset(
            db,
            asset_id,
            action=str(body.get("action") or ""),
            reject_reason=str(body.get("reject_reason") or ""),
            admin_id=user.id,
            name=body.get("name"),
            description=body.get("description"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "asset": soft.asset_to_dict(row)}


@router.post("/{asset_id}/download")
def download_post(asset_id: int, data: dict | None = None, db: Session = Depends(get_db)):
    """终端下载（无门槛；可选附带 machine_id 记流水）。"""
    body = data or {}
    try:
        row, path = soft.resolve_downloadable(
            db,
            asset_id,
            license_key=str(body.get("license_key") or ""),
            machine_id=str(body.get("machine_id") or ""),
            require_identity=False,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{row.plugin_id}-{row.version}.toa-ext.zip",
    )


@router.get("/{asset_id}/download")
def download_get(
    asset_id: int,
    machine_id: str = Query(""),
    db: Session = Depends(get_db),
):
    """公开下载（无授权门槛；仅已上架且启用）。"""
    try:
        row, path = soft.resolve_downloadable(
            db,
            asset_id,
            machine_id=machine_id,
            require_identity=False,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{row.plugin_id}-{row.version}.toa-ext.zip",
    )
