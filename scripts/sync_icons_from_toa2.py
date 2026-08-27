# -*- coding: utf-8 -*-
"""从 TOA2 同步高清 SVG 图标到 resources/icons/svg。"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "TOA" / "resources" / "images"
SRC2 = ROOT.parent / "TOA" / "images"
DEST = ROOT / "resources" / "icons" / "svg"


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    n = 0
    for base in (SRC, SRC2):
        if not base.is_dir():
            continue
        for src in base.glob("*_svg.svg"):
            dst = DEST / src.name
            shutil.copy2(src, dst)
            n += 1
        for src in base.glob("*.svg"):
            if src.name.endswith("_svg.svg"):
                continue
            dst = DEST / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                n += 1
    # 顶栏专用
    for name in ("settings_svg.svg", "exit_svg.svg"):
        for base in (SRC, SRC2, ROOT.parent / "TOA" / "resources" / "images"):
            p = base / name
            if p.is_file():
                shutil.copy2(p, DEST / name)
                n += 1
                break
    print(f"synced {n} svg -> {DEST}")


if __name__ == "__main__":
    main()
