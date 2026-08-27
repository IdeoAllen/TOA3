# -*- coding: utf-8 -*-
"""用招聘简历包回测姓名/手机提取（以 Boss 文件名为姓名金标准）。

用法:
  python scripts/eval_resume_extractor.py "C:/阿维塔/2026年/招聘简历/赵成-阿维塔兼职助教"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.resume_extractor.resume_extractor_service import extract_resume
from modules.resume_extractor.toa2_engine import ResumeExtractor

_BOSS = re.compile(
    r"】\s*(.+?)\s+(?:\d+年以上|\d+年以内|\d+年应届生|\d+年|应届生|应届)\b"
)


def gold_name(path: Path) -> str | None:
    stem = re.sub(r"\s*\(\d+\)\s*$", "", path.stem).strip()
    m = _BOSS.search(stem)
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path)
    args = ap.parse_args()
    root: Path = args.directory
    if not root.is_dir():
        print(f"不是目录: {root}")
        return 2

    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg"}
    )
    eng = ResumeExtractor()
    name_ok = phone_ok = 0
    name_bad: list[str] = []
    phone_miss: list[str] = []

    for i, f in enumerate(files, 1):
        gold = gold_name(f)
        row = extract_resume(f)
        fields = row.get("fields") or {}
        got_name = str(fields.get("姓名") or "").strip()
        got_phone = str(fields.get("手机号") or "").strip()
        if gold:
            if got_name == gold or (
                eng.looks_like_display_name(got_name) and got_name in gold
            ):
                name_ok += 1
            else:
                name_bad.append(f"{f.name} | gold={gold!r} got={got_name!r}")
        if got_phone:
            phone_ok += 1
        else:
            phone_miss.append(f.name)
        print(f"[{i}/{len(files)}] {got_name or '-'} | {got_phone or '-'} | {f.name[:48]}")

    n = len(files) or 1
    print("\n=== 回测摘要 ===")
    print(f"文件数: {len(files)}")
    print(f"姓名对齐 Boss 文件名: {name_ok}/{len(files)} = {100 * name_ok / n:.1f}%")
    print(f"检出手机号: {phone_ok}/{len(files)} = {100 * phone_ok / n:.1f}%")
    if name_bad:
        print("\n姓名偏差:")
        for line in name_bad[:20]:
            print(" ", line)
    if phone_miss:
        print(f"\n无手机号 ({len(phone_miss)}):")
        for line in phone_miss[:15]:
            print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
