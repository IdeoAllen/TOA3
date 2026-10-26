# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from config import DEFAULT_DOWNLOAD_PAGE
from models import AdminUser, ToaRelease


def release_to_dict(row: ToaRelease) -> dict[str, Any]:
    return {
        "id": row.id,
        "product": row.product,
        "channel": row.channel,
        "version": row.version,
        "download_url": row.download_url or "",
        "download_page": row.download_page or DEFAULT_DOWNLOAD_PAGE,
        "release_notes": row.release_notes or "",
        "min_version": row.min_version or "",
        "is_current": bool(row.is_current),
        "published_at": row.published_at.isoformat() if row.published_at else "",
    }


def list_releases(db: Session, *, product: str = "TOA3", channel: str = "") -> list[ToaRelease]:
    q = db.query(ToaRelease).filter(ToaRelease.product == (product or "TOA3"))
    if channel:
        q = q.filter(ToaRelease.channel == channel)
    return q.order_by(ToaRelease.id.desc()).limit(100).all()


def get_current_release(db: Session, *, product: str = "TOA3", channel: str = "stable") -> Optional[ToaRelease]:
    return (
        db.query(ToaRelease)
        .filter(
            ToaRelease.product == (product or "TOA3"),
            ToaRelease.channel == (channel or "stable"),
            ToaRelease.is_current.is_(True),
        )
        .order_by(ToaRelease.id.desc())
        .first()
    )


def manifest_for_client(db: Session, *, product: str = "TOA3", channel: str = "stable") -> dict[str, Any]:
    row = get_current_release(db, product=product, channel=channel)
    if not row:
        return {
            "product": product or "TOA3",
            "channel": channel or "stable",
            "version": "",
            "latest_version": "",
            "download_url": "",
            "download_page": DEFAULT_DOWNLOAD_PAGE,
            "release_notes": "",
            "min_version": "",
        }
    d = release_to_dict(row)
    return {
        "product": d["product"],
        "channel": d["channel"],
        "version": d["version"],
        "latest_version": d["version"],
        "download_url": d["download_url"],
        "download_page": d["download_page"],
        "release_notes": d["release_notes"],
        "min_version": d["min_version"],
        "published_at": d.get("published_at") or "",
        "installer_filename": _installer_filename(d["download_url"]),
    }


def _installer_filename(download_url: str) -> str:
    url = (download_url or "").strip().split("?")[0].rstrip("/")
    if not url:
        return ""
    name = url.rsplit("/", 1)[-1]
    return name if name.lower().endswith(".exe") else ""


def publish_release(db: Session, data: dict, *, publisher: Optional[AdminUser] = None) -> ToaRelease:
    import re

    product = str(data.get("product") or "TOA3").strip() or "TOA3"
    channel = str(data.get("channel") or "stable").strip() or "stable"
    version = str(data.get("version") or "").strip()
    if not version:
        raise ValueError("版本号不能为空")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("版本号须为 x.y.z 格式")
    download_url = str(data.get("download_url") or "").strip()
    download_page = str(data.get("download_page") or DEFAULT_DOWNLOAD_PAGE).strip()
    notes = str(data.get("release_notes") or data.get("notes") or "").strip()
    min_version = str(data.get("min_version") or "").strip()
    if min_version and not re.fullmatch(r"\d+\.\d+\.\d+", min_version):
        raise ValueError("最低可升级版本须为 x.y.z 格式")
    set_current = data.get("is_current", True)
    if isinstance(set_current, str):
        set_current = set_current.lower() in ("1", "true", "yes", "on")

    if set_current and not download_url:
        raise ValueError("设为当前版时必须填写安装包直链")
    if set_current and not notes:
        raise ValueError("设为当前版时必须填写更新说明（用户「检查更新」可见）")
    if download_url and not download_url.lower().startswith(("http://", "https://")):
        raise ValueError("安装包直链须以 http:// 或 https:// 开头")
    skip_verify = data.get("skip_verify", False)
    if isinstance(skip_verify, str):
        skip_verify = skip_verify.lower() in ("1", "true", "yes", "on")
    if set_current and download_url and not skip_verify:
        _require_reachable_download(download_url)

    dup = (
        db.query(ToaRelease)
        .filter(
            ToaRelease.product == product,
            ToaRelease.channel == channel,
            ToaRelease.version == version,
        )
        .first()
    )
    if dup:
        raise ValueError(f"该渠道已有 v{version}，请改版本号或在列表中「设为当前」")

    if set_current:
        db.query(ToaRelease).filter(
            ToaRelease.product == product,
            ToaRelease.channel == channel,
            ToaRelease.is_current.is_(True),
        ).update({ToaRelease.is_current: False})

    row = ToaRelease(
        product=product,
        channel=channel,
        version=version,
        download_url=download_url,
        download_page=download_page,
        release_notes=notes,
        min_version=min_version,
        is_current=bool(set_current),
        published_by_id=publisher.id if publisher else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_current(db: Session, release_id: int, *, skip_verify: bool = False) -> ToaRelease:
    row = db.query(ToaRelease).filter(ToaRelease.id == release_id).first()
    if not row:
        raise ValueError("发布记录不存在")
    download_url = (row.download_url or "").strip()
    if not download_url:
        raise ValueError("设为当前版前必须填写安装包直链")
    if not download_url.lower().startswith(("http://", "https://")):
        raise ValueError("安装包直链须以 http:// 或 https:// 开头")
    if not skip_verify:
        _require_reachable_download(download_url)
    db.query(ToaRelease).filter(
        ToaRelease.product == row.product,
        ToaRelease.channel == row.channel,
        ToaRelease.is_current.is_(True),
    ).update({ToaRelease.is_current: False})
    row.is_current = True
    db.commit()
    db.refresh(row)
    return row


def update_release(db: Session, release_id: int, data: dict) -> ToaRelease:
    """更新已有记录的说明 / 直链 / 最低版本（不可改版本号）。"""
    import re

    row = db.query(ToaRelease).filter(ToaRelease.id == release_id).first()
    if not row:
        raise ValueError("发布记录不存在")
    if "release_notes" in data or "notes" in data:
        row.release_notes = str(data.get("release_notes") or data.get("notes") or "").strip()
    if "download_url" in data:
        download_url = str(data.get("download_url") or "").strip()
        if download_url and not download_url.lower().startswith(("http://", "https://")):
            raise ValueError("安装包直链须以 http:// 或 https:// 开头")
        if row.is_current and not download_url:
            raise ValueError("当前版不可清空安装包直链")
        if row.is_current and download_url:
            _require_reachable_download(download_url)
        row.download_url = download_url
    if "download_page" in data:
        row.download_page = str(data.get("download_page") or DEFAULT_DOWNLOAD_PAGE).strip()
    if "min_version" in data:
        min_version = str(data.get("min_version") or "").strip()
        if min_version and not re.fullmatch(r"\d+\.\d+\.\d+", min_version):
            raise ValueError("最低可升级版本须为 x.y.z 格式")
        row.min_version = min_version
    db.commit()
    db.refresh(row)
    return row


def _require_reachable_download(download_url: str) -> None:
    check = verify_download_url(download_url)
    if check.get("ok"):
        return
    detail = check.get("reason") or check.get("status") or "unreachable"
    raise ValueError(f"安装包直链不可达（{detail}），请先上传 Setup 并试链通过后再设为当前版")


def verify_download_url(download_url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    """服务端 HEAD 试链；供运营台「试链」按钮，避免浏览器 CORS。"""
    import urllib.error
    import urllib.request

    url = (download_url or "").strip()
    if not url:
        return {"ok": False, "status": None, "reason": "empty_url", "size_mb": None}
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "status": None, "reason": "invalid_scheme", "size_mb": None}
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "TOA-Cloud-Release-Verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            length = resp.headers.get("Content-Length") or resp.headers.get("content-length")
            size_mb = None
            if length and str(length).isdigit():
                size_mb = round(int(length) / (1024 * 1024), 1)
            return {
                "ok": 200 <= status < 400,
                "status": status,
                "reason": "" if 200 <= status < 400 else f"http_{status}",
                "size_mb": size_mb,
            }
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": int(e.code), "reason": f"http_{e.code}", "size_mb": None}
    except Exception as e:
        return {"ok": False, "status": None, "reason": str(e)[:120] or "network", "size_mb": None}
