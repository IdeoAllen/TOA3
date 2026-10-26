#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登记 TOA3 3.1.5 发布记录并设为 stable 当前版（主理人 Full Go 2026-09-02）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from services import release_service as svc  # noqa: E402

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.1.5.exe"
NOTES = """TOA3 3.1.5 · 登录/档位/任务栏与 Wave F 收口（Full Go）

· 登录：授权码登录 +「进入软件」；用户档位统一为基础版 / 授权版 / 正式版
· Windows 任务栏：显示「运营宝 TOA3」，不再出现 Python
· 首页 Hero 与精选工具卡；扣分备注得分/扣分同排大字号展示
· Wave F：PDF 工具、文件打包、批量重命名（mvp，待后续点验标 done）
· 应用内 Setup 下载、更新提醒与运营台菜单信息查询（云侧）
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--set-current",
        action="store_true",
        help="同时设为 stable 当前版",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        from models import ToaRelease

        row = (
            db.query(ToaRelease)
            .filter(
                ToaRelease.product == "TOA3",
                ToaRelease.channel == "stable",
                ToaRelease.version == "3.1.5",
            )
            .first()
        )
        if row:
            print(f"已存在记录 id={row.id} v{row.version} is_current={row.is_current}")
            if args.set_current and not row.is_current:
                if not (row.download_url or "").strip():
                    row.download_url = DOWNLOAD_URL
                    db.commit()
                row = svc.set_current(db, row.id)
                print(f"已设为当前版: v{row.version}")
            elif args.set_current and row.is_current:
                print("已是当前版")
            return 0

        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.1.5",
                "download_url": DOWNLOAD_URL,
                "download_page": "https://www.yczh.tech/downloads/",
                "release_notes": NOTES.strip(),
                "min_version": "3.0.0",
                "is_current": bool(args.set_current),
            },
        )
        print(f"已登记: id={row.id} v{row.version} is_current={row.is_current}")
        print(f"download_url: {row.download_url}")
        if args.set_current:
            manifest = svc.manifest_for_client(db, product="TOA3", channel="stable")
            print("manifest:", manifest)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
