#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""侧栏右键置为一级菜单：契约自测。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    shell = (ROOT / "app" / "shell.py").read_text(encoding="utf-8")
    assert "_on_nav_context_menu" in shell
    assert "置为一级菜单" in shell
    assert "_on_domain_context_menu" in shell
    from services.menu_promote import (
        PROMOTE_BLOCK_IDS,
        demote_module_from_top_level,
        is_top_level_module,
        promote_module_to_top_level,
    )

    assert "home" in PROMOTE_BLOCK_IDS
    assert callable(promote_module_to_top_level)
    assert callable(demote_module_from_top_level)
    assert callable(is_top_level_module)
    # 系统入口应被拒绝
    ok, msg = promote_module_to_top_level("system_settings")
    assert not ok and "系统" in msg
    print("VERIFY menu_promote_context OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
