#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 DMS SQLite 迁移 toa_licenses 到 TOA Cloud 库。

用法:
  python scripts/migrate_from_dms.py --dms-db /path/to/data.db [--cloud-db ./data/toa_cloud.db]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal, init_db  # noqa: E402
from models import ToaLicense  # noqa: E402


def _row_dict(cur, row) -> dict:
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate DMS toa_licenses -> TOA Cloud")
    ap.add_argument("--dms-db", required=True, help="DMS data.db path")
    ap.add_argument("--cloud-db", default="", help="Optional cloud sqlite path (sets TOA_CLOUD_DB)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dms_path = Path(args.dms_db)
    if not dms_path.is_file():
        print(f"DMS db not found: {dms_path}", file=sys.stderr)
        return 1

    if args.cloud_db:
        import os

        os.environ["TOA_CLOUD_DB"] = str(Path(args.cloud_db).resolve())

    init_db()
    db = SessionLocal()
    src = sqlite3.connect(str(dms_path))
    src.row_factory = sqlite3.Row
    cur = src.cursor()
    try:
        cur.execute("SELECT * FROM toa_licenses")
    except sqlite3.OperationalError as e:
        print(f"toa_licenses table missing in DMS: {e}", file=sys.stderr)
        return 1

    rows = cur.fetchall()
    inserted = updated = skipped = 0
    for r in rows:
        d = dict(r)
        cid = str(d.get("code_id") or "").strip()
        if not cid:
            skipped += 1
            continue
        existing = db.query(ToaLicense).filter(ToaLicense.code_id == cid).first()
        if args.dry_run:
            print(f"would upsert code_id={cid} name={d.get('name')}")
            continue
        if existing:
            for field in (
                "name",
                "phone",
                "role",
                "expire_date",
                "status",
                "license_key",
                "code_fingerprint",
                "bind_machine",
                "activated_machine_id",
                "remark",
            ):
                if field in d and d[field] is not None:
                    setattr(existing, field, d[field])
            if d.get("menus_json"):
                existing.menus_json = d["menus_json"]
            updated += 1
        else:
            rec = ToaLicense(
                code_id=cid,
                name=str(d.get("name") or ""),
                phone=str(d.get("phone") or ""),
                role=str(d.get("role") or "user"),
                expire_date=str(d.get("expire_date") or ""),
                status=str(d.get("status") or "active"),
                license_key=str(d.get("license_key") or ""),
                code_fingerprint=str(d.get("code_fingerprint") or ""),
                bind_machine=bool(d.get("bind_machine", True)),
                activated_machine_id=str(d.get("activated_machine_id") or ""),
                menus_json=str(d.get("menus_json") or json.dumps(["all"])),
                remark=str(d.get("remark") or ""),
            )
            db.add(rec)
            inserted += 1
    if not args.dry_run:
        db.commit()
    db.close()
    src.close()
    print(f"done: inserted={inserted} updated={updated} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
