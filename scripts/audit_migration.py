# -*- coding: utf-8 -*-
"""核对 TOA3 迁移模块：菜单 / MIGRATED_MODULES / 页面可加载 / storage 登记。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.config_service import get_all_menu_items, get_menu_items
from services.menu_registry import MIGRATED_MODULES, is_migrated
from services.migration_manifest import (
    audit_false_done,
    get_module_meta,
    get_module_status,
    load_manifest,
    reload_manifest,
)


def _smoke_create_subprocess(mid: str) -> str | None:
    """单进程实例化易在 Windows 上堆叠原生资源崩溃；改为子进程逐个冒烟。"""
    code = (
        "import sys\n"
        f"sys.path.insert(0, r'{ROOT}')\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from app.module_loader import create_page\n"
        "app = QApplication([])\n"
        f"page = create_page({mid!r}, {{'name': {mid!r}, 'desc': ''}})\n"
        f"assert page.page_id == {mid!r} or {mid!r} == '__about__', page.page_id\n"
        "print('OK')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-u", "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"create_page {mid}: timeout"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return f"create_page {mid}: exit={result.returncode} {err[:400]}"
    if "OK" not in (result.stdout or ""):
        return f"create_page {mid}: no OK ({(result.stdout or '')[:200]})"
    return None


def main() -> int:
    errors: list[str] = []
    reload_manifest()
    menu_items = get_all_menu_items()
    menu_ids = {str(i.get("id") or "") for i in menu_items}
    visible = get_menu_items()
    for item in visible:
        mid = str(item.get("id") or "")
        if not mid:
            continue
        if not is_migrated(mid):
            errors.append(f"menu id {mid} 未登记 MIGRATED_MODULES / migration_manifest")
        if not get_module_meta(mid):
            errors.append(f"menu id {mid} 未登记 migration_manifest.yml")

    manifest_ids = set(load_manifest().keys())
    for mid in manifest_ids:
        if mid in ("__about__", "home"):
            continue
        if get_module_status(mid) == "missing":
            continue
        if mid not in menu_ids and mid != "system_settings":
            errors.append(f"manifest {mid} 不在 app.yml menu_items")

    for mid in audit_false_done():
        errors.append(f"manifest {mid} 标为 done 但仍有 gaps（不得绿灯）")

    # 导入检查（同进程即可）
    from app.module_loader import _import_page_class

    for mid, dotted in MIGRATED_MODULES.items():
        try:
            _import_page_class(dotted)
        except Exception as exc:
            errors.append(f"import {mid}: {exc}")

    created: set[str] = set()
    for mid in MIGRATED_MODULES:
        if mid == "home":
            continue
        err = _smoke_create_subprocess(mid)
        if err:
            errors.append(err)
        else:
            created.add(mid)

    storage_path = ROOT / "config" / "storage.yml"
    if storage_path.is_file():
        text = storage_path.read_text(encoding="utf-8")
        for mid in set(MIGRATED_MODULES.keys()) | manifest_ids:
            if mid in ("__about__", "home", "theme_preview", "system_settings"):
                continue
            if get_module_status(mid) == "missing":
                continue
            if f"{mid}:" not in text and f"  {mid}:" not in text:
                errors.append(f"storage.yml modules 未登记 {mid}")

    for mid in manifest_ids:
        if mid == "home" or mid in created:
            continue
        if get_module_status(mid) == "missing":
            continue
        err = _smoke_create_subprocess(mid)
        if err:
            errors.append(err)

    if errors:
        print("MIGRATION AUDIT FAILED")
        for e in errors:
            print(" -", e)
        return 1
    print("MIGRATION AUDIT OK")
    print(f"  migrated modules: {len(MIGRATED_MODULES)}")
    print(f"  menu items: {len(menu_ids)}")
    done = [m for m in manifest_ids if get_module_status(m) == "done"]
    print(f"  done (green): {sorted(done)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
