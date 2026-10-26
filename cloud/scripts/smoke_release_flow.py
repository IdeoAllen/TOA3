#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版流程冒烟：登录 → 试链 → 发非当前版 → 设当前 → manifest → 还原 3.1.4 → 删测试版。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from config import ADMIN_PASSWORD, ADMIN_USERNAME  # noqa: E402

BASE = os.environ.get("TOA_CLOUD_PUBLIC_BASE_URL", "https://toa-service.yczh.tech").rstrip("/")
SMOKE_VERSION = "9.9.9"
KEEP_VERSION = "3.1.4"
DOWNLOAD_PAGE = f"{BASE}/download/"
INSTALLER = f"{DOWNLOAD_PAGE}TOA3-Setup-v{KEEP_VERSION}.exe"


def _req(method: str, path: str, *, token: str = "", data: dict | None = None) -> dict | list:
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} → HTTP {e.code}: {detail}") from e


def main() -> int:
    print("BASE", BASE)
    print("admin user", ADMIN_USERNAME)

    # 1) 登录
    login = _req("POST", "/api/auth/login", data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    token = str(login.get("token") or "")
    assert token, f"login failed: {login}"
    print("OK login")

    # 2) 试链（现网安装包）
    verify = _req(
        "POST",
        "/api/toa/releases/verify-download",
        token=token,
        data={"download_url": INSTALLER},
    )
    print("OK verify-download", verify.get("ok"), verify.get("status"), verify.get("size_mb"))
    assert verify.get("ok") is True, verify

    # 3) 发布测试版（先不设当前）
    published = _req(
        "POST",
        "/api/toa/releases",
        token=token,
        data={
            "product": "TOA3",
            "channel": "stable",
            "version": SMOKE_VERSION,
            "download_url": INSTALLER,
            "download_page": DOWNLOAD_PAGE,
            "release_notes": "发版流程冒烟（自动删除）",
            "min_version": "3.0.0",
            "is_current": False,
            "skip_verify": False,
        },
    )
    smoke_id = int(published["id"])
    print("OK publish draft", SMOKE_VERSION, "id=", smoke_id, "current=", published.get("is_current"))
    assert published.get("is_current") is False

    # 4) 设为当前版
    patched = _req("POST", f"/api/toa/releases/{smoke_id}/set-current", token=token)
    print("OK set current", patched.get("version"), patched.get("is_current"))
    assert patched.get("is_current") is True

    # 5) 公开 manifest
    man = _req("GET", "/api/toa/releases/manifest?product=TOA3&channel=stable&format=json")
    print("OK manifest", man.get("version"), man.get("download_url"))
    assert man.get("version") == SMOKE_VERSION
    assert man.get("download_url") == INSTALLER

    # 6) 还原 3.1.4 为当前
    rows = _req("GET", "/api/toa/releases?product=TOA3&channel=stable", token=token)
    keep = next((r for r in rows if r.get("version") == KEEP_VERSION), None)
    assert keep, f"{KEEP_VERSION} missing"
    restored = _req("POST", f"/api/toa/releases/{keep['id']}/set-current", token=token)
    print("OK restore current", restored.get("version"))
    assert restored.get("is_current") is True

    # 7) 删除冒烟版（库内清，运营台暂无 DELETE API）
    from database import SessionLocal
    from models import ToaRelease

    db = SessionLocal()
    try:
        n = db.query(ToaRelease).filter(ToaRelease.version == SMOKE_VERSION).delete()
        db.commit()
        print("OK delete smoke rows", n)
    finally:
        db.close()

    # 8) 最终验收
    man2 = _req("GET", "/api/toa/releases/manifest?product=TOA3&channel=stable&format=json")
    assert man2.get("version") == KEEP_VERSION, man2
    assert man2.get("download_url").endswith(f"TOA3-Setup-v{KEEP_VERSION}.exe"), man2
    print("OK final manifest", man2.get("version"), man2.get("download_url"))

    # 9) 下载页可达
    req = urllib.request.Request(DOWNLOAD_PAGE, headers={"Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")
        assert resp.status == 200
    print("OK download page", len(html), "bytes")

    # HEAD installer
    req2 = urllib.request.Request(INSTALLER, method="HEAD")
    with urllib.request.urlopen(req2, timeout=30) as resp2:
        print("OK installer HEAD", resp2.status, resp2.headers.get("Content-Length"))
        assert int(resp2.status) in (200, 302, 301)

    # 10) 桌面检查更新字段兼容
    for key in ("version", "latest_version", "download_url", "download_page", "release_notes"):
        assert key in man2, f"manifest missing {key}"
    print("OK desktop manifest fields")

    print("\nrelease_flow_smoke: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FAIL:", exc)
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
