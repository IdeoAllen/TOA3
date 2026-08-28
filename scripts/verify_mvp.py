# -*- coding: utf-8 -*-
"""TOA3 MVP 冒烟验收（无 GUI 长时间运行）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from app.module_loader import create_page
from app.theme_loader import apply_theme, ensure_official_qss, list_theme_ids
from services.config_service import load_config, resolve_path
from services.menu_registry import grouped_menu_items
from services.theme_catalog import selectable_themes


def main() -> int:
    errors: list[str] = []

    cfg = load_config()
    if not cfg:
        errors.append("config empty")

    for key in ("data_dir", "log_dir", "license_file"):
        p = resolve_path(key)
        if "TOA\\" in str(p) or "TOA/" in str(p):
            errors.append(f"path {key} still points to TOA2: {p}")

    for key in ("data_dir", "log_dir", "output_dir", "docs_dir", "images_dir"):
        try:
            p = resolve_path(key)
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    try:
        from services.storage_paths import bundled_root, bundled_samples_dir, bundled_templates_dir

        if not bundled_templates_dir().is_dir():
            errors.append("missing assets/templates")
        if not bundled_samples_dir().is_dir():
            errors.append("missing assets/samples")
        if not (ROOT / "config" / "storage.yml").is_file():
            errors.append("missing config/storage.yml")
        if not (ROOT / "config" / "ui_spec.yml").is_file():
            errors.append("missing config/ui_spec.yml")
        if not (ROOT / "config" / "integrations.yml").is_file():
            errors.append("missing config/integrations.yml")
        from core.ui_spec import shell_spec

        if not shell_spec().get("min_width"):
            errors.append("ui_spec shell incomplete")
    except Exception as e:
        errors.append(f"storage_paths: {e}")

    from services.theme_catalog import official_theme_ids, selectable_themes

    themes = selectable_themes()
    expected_official = len(official_theme_ids())
    if len(themes) < expected_official:
        errors.append(f"expected {expected_official} official themes, got {len(themes)}")

    json_ids = list_theme_ids()
    if len(json_ids) < 11:
        errors.append(f"expected 11 theme json files, got {len(json_ids)}")

    ensure_official_qss()

    app = QApplication([])
    for tid, _ in themes[:3]:
        try:
            apply_theme(app, tid)
        except Exception as e:
            errors.append(f"apply_theme {tid}: {e}")

    from services.menu_registry import all_menu_items, grouped_menu_items

    menu_count = len(all_menu_items())
    if menu_count < 10:
        errors.append(f"menu items too few: {menu_count}")
    # 分组在授权过滤后仍应可用（至少首页组）
    if not grouped_menu_items():
        errors.append("grouped_menu_items empty")

    for _gid, _gl, items in grouped_menu_items(licensed_only=False, migrated_only=True):
        for item in items:
            mid = str(item.get("id") or "")
            if not mid:
                continue
            try:
                page = create_page(mid, item)
                if not page.page_id:
                    errors.append(f"page missing id: {mid}")
            except Exception as e:
                errors.append(f"create_page {mid}: {e}")

    from services.menu_registry import MIGRATED_MODULES

    for mid in MIGRATED_MODULES:
        if mid in ("home",):
            continue
        try:
            page = create_page(mid, {"name": mid})
            if page.page_id != mid and mid != "__about__":
                errors.append(f"page_id mismatch {mid} -> {page.page_id}")
        except Exception as e:
            errors.append(f"create_page migrated {mid}: {e}")

    if errors:
        print("MVP VERIFY FAILED")
        for e in errors:
            print(" -", e)
        return 1

    print("MVP VERIFY OK")
    print(f"  themes: {len(themes)}")
    print(f"  menu visible: {menu_count}")
    import os

    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
