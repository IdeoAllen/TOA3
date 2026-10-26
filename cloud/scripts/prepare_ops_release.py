# -*- coding: utf-8 -*-
"""运营台预登记发版（is_current=false）：主理人只点「设为当前」。

用法：
  python scripts/prepare_ops_release.py --version 3.1.22 --notes-file notes.txt
  python scripts/prepare_ops_release.py --version 3.1.22 --notes "……"
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from config import (  # noqa: E402
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    DEFAULT_DOWNLOAD_PAGE as DOWNLOAD_PAGE,
    PUBLIC_BASE_URL as BASE,
    installer_url,
)


def req(method: str, path: str, *, token: str = "", data: dict | None = None):
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} → HTTP {e.code}: {detail}") from e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="x.y.z")
    ap.add_argument("--notes", default="", help="更新说明正文")
    ap.add_argument("--notes-file", default="", help="更新说明文件路径")
    ap.add_argument("--download-url", default="", help="默认按版本拼直链")
    ap.add_argument("--min-version", default="3.0.0")
    ap.add_argument("--set-current", action="store_true", help="直接设为当前（默认否，留给主理人点）")
    args = ap.parse_args()

    ver = str(args.version).strip().lstrip("v")
    notes = (args.notes or "").strip()
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8").strip()
    if not notes:
        print("FAIL: 必须提供 --notes 或 --notes-file")
        return 2
    url = (args.download_url or "").strip() or installer_url(ver)

    login = req(
        "POST",
        "/api/auth/login",
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    token = str(login.get("token") or "")
    if not token:
        print("FAIL login", login)
        return 1

    rows = req("GET", f"/api/toa/releases?product=TOA3", token=token)
    existing = next((r for r in rows if str(r.get("version")) == ver), None)
    payload = {
        "product": "TOA3",
        "channel": "stable",
        "version": ver,
        "download_url": url,
        "download_page": DOWNLOAD_PAGE,
        "min_version": args.min_version,
        "release_notes": notes,
        "is_current": bool(args.set_current),
    }

    if existing:
        rid = int(existing["id"])
        print(f"已存在 id={rid} v{ver} is_current={existing.get('is_current')} → PATCH 说明/直链")
        row = req(
            "PATCH",
            f"/api/toa/releases/{rid}",
            token=token,
            data={
                "download_url": url,
                "min_version": args.min_version,
                "release_notes": notes,
            },
        )
        if args.set_current and not existing.get("is_current"):
            row = req("POST", f"/api/toa/releases/{rid}/set-current", token=token)
    else:
        print(f"新建 v{ver} is_current={bool(args.set_current)}")
        row = req("POST", "/api/toa/releases", token=token, data=payload)

    print(
        "OK",
        f"id={row.get('id')}",
        f"v{row.get('version')}",
        f"current={row.get('is_current')}",
        f"notes_len={len(row.get('release_notes') or '')}",
    )
    print("download_url:", row.get("download_url"))
    if not row.get("is_current"):
        print("下一步：主理人只点「设为当前」→ Agent 再跑 sync_release_version --from-live --require-match --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
