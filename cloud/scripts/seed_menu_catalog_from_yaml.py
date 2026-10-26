#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 config/menu_catalog.yml 发布到运营台 DB（发版后同步 module 池）。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from services import product_catalog_service as cat  # noqa: E402


def main() -> int:
    path = ROOT / "config" / "menu_catalog.yml"
    if not path.is_file():
        print(f"missing {path}")
        return 1
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    modules = data.get("modules") or []
    if not modules:
        print("menu_catalog.yml has no modules")
        return 1
    init_db()
    db = SessionLocal()
    try:
        result = cat.publish_menu_modules(
            db,
            modules,
            app_version=str(data.get("app_version") or ""),
            published_by="seed:menu_catalog.yml",
        )
        print(f"published {result.get('count', len(modules))} modules app_version={data.get('app_version')}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
