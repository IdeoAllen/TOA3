#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版前扫描：确认 dist 发布目录无 API Key、data/user、个人 Harness 路径。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = ROOT / "packaging"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACKAGING_DIR))

from release_config_guard import (  # noqa: E402
    scan_project_config_before_release,
    scan_release_tree,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="TOA3 发版密钥与本地配置扫描")
    parser.add_argument(
        "path",
        nargs="?",
        default="",
        help="发布目录，例如 packaging/dist/TOA3-v3.0.0-win64",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="仅检查 packaging/shipped_config 模板是否齐全",
    )
    args = parser.parse_args()

    if args.preflight:
        errs = scan_project_config_before_release(ROOT, PACKAGING_DIR)
        if errs:
            for e in errs:
                print(f"ERROR: {e}")
            return 1
        print("preflight OK: shipped_config 模板就绪")
        return 0

    if not args.path:
        print("请指定发布目录，或加 --preflight")
        return 2

    root = Path(args.path)
    errs = scan_release_tree(root)
    if errs:
        for e in errs:
            print(f"ERROR: {e}")
        return 1
    print(f"OK: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
