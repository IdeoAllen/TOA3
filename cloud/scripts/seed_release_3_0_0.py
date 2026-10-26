#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册 TOA3 3.0.0 单机版为 stable 当前版（运维一次性脚本）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from services import release_service as svc  # noqa: E402

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.0.0.exe"
NOTES = """TOA3 3.0.0 · 单机版首发

· 首次启动可选「单机体验」：免授权码、可离线
· 含：快速记事、截图、剪贴板、四象限任务、番茄钟
· 完整培训业务：登录窗「授权码登录」联网激活
"""


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = svc.get_current_release(db, product="TOA3", channel="stable")
        if existing and existing.version == "3.0.0" and (existing.download_url or "").strip():
            print(f"已是当前版: {existing.version} -> {existing.download_url}")
            return 0
        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.0.0",
                "download_url": DOWNLOAD_URL,
                "download_page": "https://www.yczh.tech/downloads/",
                "release_notes": NOTES.strip(),
                "min_version": "",
                "is_current": True,
            },
        )
        print(f"已发布: v{row.version} is_current={row.is_current}")
        print(f"download_url: {row.download_url}")
        manifest = svc.manifest_for_client(db, product="TOA3", channel="stable")
        print("manifest:", manifest)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
