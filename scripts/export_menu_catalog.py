#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 TOA3 菜单目录 → cloud/config/menu_catalog.yml（运营台 SKU 校验用）。"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import APP_VERSION  # noqa: E402
from services.config_service import load_config  # noqa: E402
from services.menu_registry import (  # noqa: E402
    DOMAIN_TAB_LABELS,
    GROUP_LABELS,
    GROUP_ORDER,
    normalize_menu_group_id,
)

SPECIAL_IDS = frozenset(
    {
        "all",
        "home",
        "system_settings",
        "job_scheduler",
        "notifications",
        "about",
    }
)


def _load_manifest_status() -> dict[str, str]:
    path = ROOT / "config" / "migration_manifest.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mods = data.get("modules") or {}
    out: dict[str, str] = {}
    for mid, block in mods.items():
        if isinstance(block, dict):
            out[str(mid)] = str(block.get("status") or "")
    return out


def build_catalog() -> dict:
    cfg = load_config()
    menu = cfg.get("menu") or {}
    items = menu.get("menu_items") or []
    manifest = _load_manifest_status()
    modules = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        group = normalize_menu_group_id(raw.get("group") or "other")
        modules.append(
            {
                "id": mid,
                "name": str(raw.get("name") or mid),
                "group": group,
                "group_label": GROUP_LABELS.get(group, group),
                "domain_tab": DOMAIN_TAB_LABELS.get(group, group),
                "order": int(raw.get("order") or 0),
                "group_order": int(GROUP_ORDER.index(group)) if group in GROUP_ORDER else 99,
                "show": bool(raw.get("show", True)),
                "requires_license": bool(raw.get("requires_license", False)),
                "feature_id": str(raw.get("feature_id") or mid),
                "migration_status": manifest.get(mid, ""),
            }
        )
    modules.sort(key=lambda x: (int(x.get("group_order") or 99), int(x.get("order") or 0), x["id"]))
    # 出厂 group_labels（不含兼容旧键）
    labels = {gid: GROUP_LABELS[gid] for gid in GROUP_ORDER if gid in GROUP_LABELS}
    return {
        "product": "TOA3",
        "app_version": APP_VERSION,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "special_ids": sorted(SPECIAL_IDS),
        "group_labels": labels,
        "group_order": list(GROUP_ORDER),
        "modules": modules,
    }


def main() -> int:
    catalog = build_catalog()
    out_path = ROOT / "cloud" / "config" / "menu_catalog.yml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# TOA3 菜单目录（由 scripts/export_menu_catalog.py 生成，勿手改）\n"
        "# 同步：cloud/scripts/sync_toa3_product_catalog.ps1\n"
    )
    out_path.write_text(header + yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"exported {len(catalog['modules'])} modules -> {out_path}")
    print(f"app_version={catalog['app_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
