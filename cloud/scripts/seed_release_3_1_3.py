#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册 TOA3 3.1.3 为 stable 当前版（运维脚本 · 已弃用日常发版）。

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

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.1.3.exe"
NOTES = """TOA3 3.1.3 · 首页与发版瘦身

· 首页：精选办公/套件入口，不再整表跟菜单渲染；顶栏 ⌂ 打开「检索工作」
· 模型管理：进页秒开，本机服务探测改后台异步
· Harness / 媒体工坊：整窗抖动与进页卡顿优化
· 菜单：二级可升为顶栏子模块；单功能子模块侧栏自动收起
· 正式安装包：不含预置模型 catalog / 本机生图下载清单；高级算力用户自行绑定或向导安装
· 购买面板：离线先显本机方案；授权验收样例与若干 UI 修复
"""


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = svc.get_current_release(db, product="TOA3", channel="stable")
        if existing and existing.version == "3.1.3" and (existing.download_url or "").strip():
            print(f"已是当前版: {existing.version} -> {existing.download_url}")
            return 0
        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.1.3",
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
