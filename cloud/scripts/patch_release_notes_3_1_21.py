# -*- coding: utf-8 -*-
"""补写运营台 v3.1.21 更新说明（当前误为「11」）。"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from config import ADMIN_PASSWORD, ADMIN_USERNAME  # noqa: E402

BASE = "https://toa-service.yczh.tech"
VERSION = "3.1.21"
NOTES = """【版本】v3.1.21
【本版要点】
1. Harness 内嵌侧栏可预览文件（修复「文件资源服务不可用」）
2. Ctrl+Tab / Ctrl+Shift+Tab 切换顶栏主菜单
3. 编码智能体启动自愈；记事编辑预览与组件库；桌面视频封面
【全局介入/热键】
- 新增 next_domain=Ctrl+Tab、prev_domain=Ctrl+Shift+Tab（仅应用前台）
【已知限制】
- 其余 Qt WebEngine ≠ 完整 Chrome 处仍可「在浏览器打开」
【验收】安装包直链试链通过；检查更新可见本号"""


def req(method: str, path: str, *, token: str = "", data: dict | None = None):
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    login = req(
        "POST",
        "/api/auth/login",
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    token = str(login.get("token") or "")
    if not token:
        print("FAIL login", login)
        return 1
    rows = req("GET", "/api/toa/releases?product=TOA3", token=token)
    row = next((x for x in rows if str(x.get("version")) == VERSION), None)
    if not row:
        print("FAIL: v3.1.21 not found")
        return 1
    print("id", row["id"], "old_notes", repr(row.get("release_notes")))
    patched = req(
        "PATCH",
        f"/api/toa/releases/{row['id']}",
        token=token,
        data={
            "release_notes": NOTES,
            "download_url": f"https://www.yczh.tech/downloads/TOA3-Setup-v{VERSION}.exe",
        },
    )
    print("patched_len", len(patched.get("release_notes") or ""))
    man = req(
        "GET",
        "/api/toa/releases/manifest?product=TOA3&channel=stable&format=json",
    )
    print("manifest", man.get("version"), "notes_ok", (man.get("release_notes") or "").startswith("【版本】"))
    print((man.get("release_notes") or "")[:160].replace("\n", " / "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
