#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册 TOA3 3.1.2 为 stable 当前版（运维脚本 · 已弃用日常发版）。

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

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.1.2.exe"
NOTES = """TOA3 3.1.2 · 体验与办公套件

· 系统侧栏：系统设置 / 定时任务 / 通知 / 控件库顺序调整
· 快速记事：源码 / 设计 / 预览三页签，所见即所得与 Markdown 互通
· 班级日程提醒：主工作区加高，五场景表格更易浏览
· Harness / 网页工作台稳定性与内嵌体验优化
· 菜单同步、授权与若干 UI 细节修复
"""


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = svc.get_current_release(db, product="TOA3", channel="stable")
        if existing and existing.version == "3.1.2" and (existing.download_url or "").strip():
            print(f"已是当前版: {existing.version} -> {existing.download_url}")
            return 0
        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.1.2",
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
