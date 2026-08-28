#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 feature_packs 引用的 module_id 均存在于 app.yml 菜单。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.feature_packs import expand_features  # noqa: E402
from services.menu_registry import all_menu_items  # noqa: E402

SPECIAL = frozenset({"all", "home", "system_settings", "job_scheduler", "notifications", "about"})


def main() -> int:
    menu_ids = {str(i.get("id") or "").strip() for i in all_menu_items() if i.get("id")}
    menu_ids |= SPECIAL
    packs_raw = yaml.safe_load((ROOT / "config" / "feature_packs.yml").read_text(encoding="utf-8")) or {}
    pack_blocks = packs_raw.get("packs") or {}
    pack_ids = set(str(k) for k in pack_blocks.keys())

    errors: list[str] = []
    for pid, block in pack_blocks.items():
        if not isinstance(block, dict):
            continue
        raw_feats = list(block.get("features") or [])
        expanded = expand_features(raw_feats or [str(pid)])
        if expanded == ["all"]:
            continue
        for token in expanded:
            if token in menu_ids or token in pack_ids:
                continue
            errors.append(f"pack {pid}: unknown module/token '{token}'")

    if errors:
        print("feature_packs menu validation FAILED:")
        for e in errors:
            print(" ", e)
        return 1
    print(f"feature_packs menu validation OK ({len(pack_blocks)} packs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
