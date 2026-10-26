# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from config import DEFAULT_DOWNLOAD_PAGE, DOWNLOAD_BASE_URL, installer_url
from database import get_db
from deps import require_perm
from models import AdminUser
from services import release_service as svc
from services.manifest_view import render_manifest_html

router = APIRouter(prefix="/api/toa/releases", tags=["toa-releases"])


def _wants_html_view(request: Request, *, format: str = "") -> bool:
    fmt = (format or "").strip().lower()
    if fmt == "json":
        return False
    if fmt == "html":
        return True
    accept = (request.headers.get("accept") or "").lower()
    if accept.startswith("text/html"):
        return True
    if "application/json" in accept and "text/html" not in accept:
        return False
    return False


@router.get("/manifest")
def public_manifest(
    request: Request,
    product: str = Query("TOA3"),
    channel: str = Query("stable"),
    format: str = Query("", description="html=可读页；json=强制 JSON"),
    db: Session = Depends(get_db),
):
    """TOA3 桌面「检查更新」读取此 JSON（与 update_check.py 字段兼容）。

    浏览器直达默认返回格式化 HTML；客户端带 Accept: application/json 仍得 JSON。
    """
    data = svc.manifest_for_client(db, product=product, channel=channel)
    if _wants_html_view(request, format=format):
        json_url = str(request.url.include_query_params(format="json"))
        html = render_manifest_html(
            data,
            product=product,
            channel=channel,
            json_url=json_url,
        )
        return HTMLResponse(content=html)
    return data


@router.get("/download-config")
def download_config():
    """下载页 / 安装包目录（运营台与脚本共用，勿在前端写死）。"""
    return {
        "download_page": DEFAULT_DOWNLOAD_PAGE,
        "installer_base": DOWNLOAD_BASE_URL,
        "installer_pattern": installer_url("{version}"),
    }


@router.post("/verify-download")
def verify_download(
    data: dict,
    _user: AdminUser = Depends(require_perm("toa_release:write")),
):
    """运营台「试链」：服务端 HEAD 校验安装包直链（规避浏览器 CORS）。"""
    return svc.verify_download_url(str((data or {}).get("download_url") or ""))


@router.get("")
def list_releases(
    product: str = Query("TOA3"),
    channel: str = Query(""),
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_release:read", "toa_release:write")),
):
    rows = svc.list_releases(db, product=product, channel=channel)
    return [svc.release_to_dict(r) for r in rows]


@router.post("")
def publish_release(
    data: dict,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_perm("toa_release:write")),
):
    try:
        row = svc.publish_release(db, data or {}, publisher=user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.release_to_dict(row)


@router.patch("/{release_id}")
def patch_release(
    release_id: int,
    data: dict,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_release:write")),
):
    try:
        row = svc.update_release(db, release_id, data or {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.release_to_dict(row)


@router.post("/{release_id}/set-current")
def mark_current(
    release_id: int,
    db: Session = Depends(get_db),
    _user: AdminUser = Depends(require_perm("toa_release:write")),
):
    try:
        row = svc.set_current(db, release_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return svc.release_to_dict(row)
