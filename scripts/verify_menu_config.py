# -*- coding: utf-8 -*-
"""菜单配置合并 / 保存 / 可见性冒烟测试（无 GUI）。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.config_service import (  # noqa: E402
    _default_menu_items_from_app,
    _merged_to_overrides_map,
    _read_user_menu_doc,
    _write_menu_user_file,
    get_all_menu_items,
    get_group_labels,
    get_menu_items,
    reset_user_menu,
    save_menu_items,
    user_menu_path,
)
from services.menu_registry import GROUP_ORDER, grouped_menu_items, show_in_sidebar


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def main() -> int:
    errors: list[str] = []

    base = _default_menu_items_from_app()
    if not base:
        errors.append("app.yml menu empty")

    merged = get_all_menu_items()
    if len(merged) < len(base):
        errors.append("merged menu shorter than app base")

    hidden_ids = {str(i.get("id")) for i in merged if not i.get("show", True)}
    visible_ids = {str(i.get("id")) for i in get_menu_items()}
    leaked = hidden_ids & visible_ids
    if leaked:
        errors.append(f"hidden items in visible menu: {sorted(leaked)}")

    labels = get_group_labels()
    for gid in GROUP_ORDER:
        if gid not in labels:
            errors.append(f"missing group label: {gid}")

    # save round-trip
    with tempfile.TemporaryDirectory() as tmp:
        import services.config_service as cs

        fake = Path(tmp) / "menu.yml"
        orig_path_fn = cs.user_menu_path
        cs.user_menu_path = lambda: fake  # type: ignore[assignment]

        try:
            items = deepcopy_items(merged)
            items_by_id = {str(i.get("id")): i for i in items}
            if "quick_notepad" in items_by_id:
                items_by_id["quick_notepad"]["order"] = 99
            if "ocr_tool" in items_by_id:
                items_by_id["ocr_tool"]["show"] = False
            gl = dict(get_group_labels())
            gl["ai"] = "测试智能体"
            custom_order = ["home", "system", "office", "ai", "image", "directory", "file", "business"]
            save_menu_items(items, group_labels=gl, group_order=custom_order)

            doc = _read_user_menu_doc()
            if not doc.get("overrides") and not doc.get("group_labels") and not doc.get("group_order"):
                errors.append("save wrote empty doc")

            cs._CONFIG_CACHE = None
            reloaded = get_all_menu_items()
            ocr = next((i for i in reloaded if i.get("id") == "ocr_tool"), None)
            if ocr and ocr.get("show", True):
                errors.append("ocr_tool show override not applied")

            gl2 = get_group_labels()
            if gl2.get("ai") != "测试智能体":
                errors.append(f"group label ai expected 测试智能体 got {gl2.get('ai')}")

            from services.config_service import get_group_order as cfg_group_order

            go = cfg_group_order()
            if go[:2] != ["home", "system"]:
                errors.append(f"group_order not applied: {go[:3]}")

            reset_user_menu()
            if fake.is_file():
                errors.append("reset_user_menu did not delete file")
        finally:
            cs.user_menu_path = orig_path_fn  # type: ignore[assignment]
            cs._CONFIG_CACHE = None

    # order within group
    for gid, _glab, items in grouped_menu_items():
        orders = [int(i.get("order") or 0) for i in items]
        if orders != sorted(orders):
            errors.append(f"group {gid} items not sorted by order")

    # sidebar filter
    for gid, _glab, items in grouped_menu_items():
        for it in items:
            if not show_in_sidebar(it) and it.get("show", True):
                errors.append(f"{it.get('id')} show but sidebar false")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    print("OK: menu config merge, save, group_labels, visibility, order")
    return 0


def deepcopy_items(items: list[dict]) -> list[dict]:
    from copy import deepcopy

    return deepcopy(items)


if __name__ == "__main__":
    raise SystemExit(main())
