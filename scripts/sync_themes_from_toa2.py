# -*- coding: utf-8 -*-
"""从 TOA2 config/themes 同步 JSON 主题到 TOA3。"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOA2_THEMES = ROOT.parent / "TOA" / "config" / "themes"
DEST = ROOT / "config" / "themes"


def main() -> None:
    if not TOA2_THEMES.is_dir():
        print(f"TOA2 主题目录不存在: {TOA2_THEMES}")
        return
    DEST.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(TOA2_THEMES.glob("*.json")):
        dst = DEST / src.name
        shutil.copy2(src, dst)
        print("synced", src.name)
        n += 1
    print(f"done: {n} files -> {DEST}")


if __name__ == "__main__":
    main()
