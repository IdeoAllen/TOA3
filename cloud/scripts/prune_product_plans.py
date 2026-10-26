#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将运营台产品方案收敛为仅 tiyan + local_free（清除其余 SKU）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import yaml  # noqa: E402

from database import SessionLocal, init_db  # noqa: E402
from models import ToaFeaturePack  # noqa: E402
from services import product_catalog_service as cat  # noqa: E402

KEEP = frozenset({"tiyan", "local_free"})


def _load_yaml_packs() -> dict:
    path = ROOT / "config" / "feature_packs.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("packs") or {}


def _load_prices() -> dict:
    path = ROOT / "config" / "commerce.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("pack_prices_yuan") or {}


def main() -> int:
    init_db()
    db = SessionLocal()
    cleared: list[str] = []
    upserted: list[str] = []
    try:
        packs_yaml = _load_yaml_packs()
        prices = _load_prices()
        for pid in KEEP:
            block = packs_yaml.get(pid)
            if not isinstance(block, dict):
                print(f"skip missing yaml pack: {pid}")
                continue
            body = {
                "id": pid,
                "name": block.get("name"),
                "desc": block.get("desc"),
                "sellable": bool(block.get("sellable", pid == "tiyan")),
                "price_yuan": int(prices.get(pid, 0) or 0),
                "validity_days": int(block.get("validity_days") or 365),
                "features": list(block.get("features") or []),
                "includes": list(block.get("includes") or []),
                "is_active": True,
            }
            cat.save_pack_db(db, pid, body, operator=None, skip_validation=True)
            upserted.append(pid)

        for row in db.query(ToaFeaturePack).all():
            if row.id in KEEP:
                continue
            try:
                cat.clear_pack_db(db, row.id, operator=None)
                cleared.append(row.id)
            except ValueError as exc:
                print(f"warn clear {row.id}: {exc}")
        print(f"upserted: {', '.join(upserted) or '—'}")
        print(f"cleared: {', '.join(cleared) or '—'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
