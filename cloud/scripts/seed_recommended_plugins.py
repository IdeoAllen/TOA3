# -*- coding: utf-8 -*-
"""将 seed/plugins 下官方示例插件写入库：已上架 + 推荐。

用法（在 toa-cloud 根或 backend 下）:
  python scripts/seed_recommended_plugins.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
SEED_DIR = ROOT / "seed" / "plugins"
sys.path.insert(0, str(BACKEND))

import tomllib  # noqa: E402
from database import SessionLocal, init_db  # noqa: E402
from models import ToaSoftAsset  # noqa: E402
from services.soft_asset_service import STORAGE_ROOT, ensure_storage  # noqa: E402

OFFICIAL = [
    "tool_phone_mask",
    "tool_meet_bullets",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _pack_zip(plugin_root: Path) -> tuple[bytes, dict]:
    meta_name = "pack.meta.json"
    raw_toml = tomllib.loads((plugin_root / "plugin.toml").read_text(encoding="utf-8"))
    plug = raw_toml.get("plugin") or {}
    safety = raw_toml.get("safety") or {}

    body_parts: list[tuple[str, bytes]] = []
    for fp in sorted(plugin_root.rglob("*")):
        if not fp.is_file():
            continue
        if "__pycache__" in fp.parts or fp.suffix == ".pyc":
            continue
        if fp.name == meta_name:
            continue
        body_parts.append((fp.relative_to(plugin_root).as_posix(), fp.read_bytes()))

    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, data in body_parts:
            zf.writestr(arc, data)
    digest = _sha256_bytes(buf.getvalue())

    meta = {
        "schema_version": 1,
        "asset_kind": "extension.pack",
        "plugin_id": str(plug.get("id") or plugin_root.name),
        "name": str(plug.get("name") or plugin_root.name),
        "version": str(plug.get("version") or "1.0.0"),
        "group": str(plug.get("group") or "business"),
        "description": str(plug.get("description") or ""),
        "author": str(plug.get("author") or "TOA 官方"),
        "capabilities": ["l1"],
        "integrations": list(safety.get("integrations") or []),
        "content_sha256": digest,
        "audit_ok": True,
        "audit_summary": "official seed",
        "review_status": "approved",
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, data in body_parts:
            zf.writestr(arc, data)
        zf.writestr(meta_name, json.dumps(meta, ensure_ascii=False, indent=2))
    return out.getvalue(), meta


def upsert_plugin(db, plugin_id: str) -> ToaSoftAsset:
    root = SEED_DIR / plugin_id
    if not (root / "plugin.toml").is_file():
        raise FileNotFoundError(root)
    zip_bytes, meta = _pack_zip(root)
    ensure_storage()

    row = (
        db.query(ToaSoftAsset)
        .filter(
            ToaSoftAsset.plugin_id == plugin_id,
            ToaSoftAsset.asset_kind == "extension.pack",
        )
        .order_by(ToaSoftAsset.id.desc())
        .first()
    )
    if row is None:
        row = ToaSoftAsset(plugin_id=plugin_id, asset_kind="extension.pack")
        db.add(row)
        db.flush()

    row.name = meta["name"]
    row.description = meta["description"]
    row.version = meta["version"]
    row.group_id = meta["group"]
    row.author = meta["author"]
    row.capabilities_json = json.dumps(meta["capabilities"], ensure_ascii=False)
    row.integrations_json = json.dumps(meta["integrations"], ensure_ascii=False)
    row.content_sha256 = meta["content_sha256"]
    row.audit_ok = True
    row.audit_summary = meta["audit_summary"]
    row.review_status = "approved"
    row.reject_reason = ""
    row.listed = True
    row.enabled = True
    row.recommended = True
    row.customer_id = None
    row.submitted_at = row.submitted_at or _now()
    row.reviewed_at = _now()
    row.updated_at = _now()

    dest = STORAGE_ROOT / f"{row.id}_{plugin_id}.toa-ext.zip"
    dest.write_bytes(zip_bytes)
    row.storage_path = str(dest)
    db.commit()
    db.refresh(row)
    return row


def main() -> int:
    if not SEED_DIR.is_dir():
        print(f"missing seed dir: {SEED_DIR}", file=sys.stderr)
        return 1
    init_db()
    db = SessionLocal()
    try:
        for pid in OFFICIAL:
            row = upsert_plugin(db, pid)
            print(
                f"ok id={row.id} plugin_id={row.plugin_id} "
                f"recommended={row.recommended} listed={row.listed}"
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
