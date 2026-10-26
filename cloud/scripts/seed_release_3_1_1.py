#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册 TOA3 3.1.1 为 stable 当前版（运维脚本 · 已弃用日常发版）。

日常发版请走运营台「版本发布」。本脚本用于 CI/SSH 一键发版或 bootstrap。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from services import release_service as svc  # noqa: E402

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.1.1.exe"
NOTES = """TOA3 3.1.1 · 无感开通与商业链

· 受限模块 / 顶栏 Chip / 用户资料：一键开通，无需粘贴授权码
· 设置「激活与订阅」「选择套餐」与弹窗共用购买链路
· 终端菜单同步 module 池 → 运营台组包 → 订单履约
· 授权管理移除冗余「运营参考」；SKU/定价仅在运营台
· 用户可见文案统一为 TOA 云服务术语
"""


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = svc.get_current_release(db, product="TOA3", channel="stable")
        if existing and existing.version == "3.1.1" and (existing.download_url or "").strip():
            print(f"已是当前版: {existing.version} -> {existing.download_url}")
            return 0
        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.1.1",
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
