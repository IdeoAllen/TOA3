#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册 TOA3 3.1.0 为 stable 当前版（运维脚本 · 已弃用日常发版）。

日常发版请走运营台「版本发布」。本脚本仅作历史/bootstrap 参考。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from services import release_service as svc  # noqa: E402

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.1.0.exe"
NOTES = """TOA3 3.1.0 · 平台体验 Target

· 托盘 menu_registry 动态菜单 + 检查更新/授权入口
· 顶栏授权 Chip；关闭窗口可最小化到托盘（设置页可配）
· 登录「开始试用」+ 云服务 trial-start
· 启动后非阻塞检查更新；检查更新 Hub 防卡死
"""


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = svc.get_current_release(db, product="TOA3", channel="stable")
        if existing and existing.version == "3.1.0" and (existing.download_url or "").strip():
            print(f"已是当前版: {existing.version} -> {existing.download_url}")
            return 0
        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.1.0",
                "download_url": DOWNLOAD_URL,
                "download_page": "https://www.yczh.tech/downloads/",
                "release_notes": NOTES.strip(),
                "min_version": "3.0.0",
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
