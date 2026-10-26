#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登记 TOA3 3.1.4 发布记录（默认不设为当前版，等人审后再 set-current）。

日常发版：运营台「版本发布」审核 → 上传安装包 → 设为当前版。
本脚本用于 CI/SSH 建草稿。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from services import release_service as svc  # noqa: E402

DOWNLOAD_URL = "https://www.yczh.tech/downloads/TOA3-Setup-v3.1.4.exe"
NOTES = """TOA3 3.1.4 · 生成交付报告与 Word 导出修复

· 业务侧新增「生成交付报告」：班级交付目录 → Word 封面大纲贴图 + Excel 层级图片统计（迁自 TOA2）
· 修复 Word 封面后多出一页空白（分页符接到封面页脚）
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--set-current",
        action="store_true",
        help="同时设为 stable 当前版（默认仅建记录，不切换 manifest）",
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
                ToaRelease.version == "3.1.4",
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
            return 0

        row = svc.publish_release(
            db,
            {
                "product": "TOA3",
                "channel": "stable",
                "version": "3.1.4",
                "download_url": DOWNLOAD_URL,
                "download_page": "https://www.yczh.tech/downloads/",
                "release_notes": NOTES.strip(),
                "min_version": "3.0.0",
                "is_current": bool(args.set_current),
            },
        )
        print(f"已登记: id={row.id} v{row.version} is_current={row.is_current}")
        print(f"download_url: {row.download_url}")
        if not args.set_current:
            print("状态: 待审核（未切换 manifest）。运营台确认后执行 set-current 或加 --set-current")
        else:
            manifest = svc.manifest_for_client(db, product="TOA3", channel="stable")
            print("manifest:", manifest)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
