#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness 默认套件内嵌；外开须用户自点；能力不及处提示「浏览器打开效果更佳」。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.harness_config import PRODUCT_SURFACE_MODE, load_harness_config
    from services.harness_surface import (
        BROWSER_BETTER_HINT,
        SURFACE_EMBED,
        prefer_embed,
        surface_mode,
    )

    assert PRODUCT_SURFACE_MODE == SURFACE_EMBED == "embed"
    assert BROWSER_BETTER_HINT == "浏览器打开效果更佳"
    load_harness_config(force=True)

    shipped = yaml.safe_load(
        (ROOT / "packaging" / "shipped_config" / "harness.yml").read_text(encoding="utf-8")
    )["harness"]
    cfg = yaml.safe_load((ROOT / "config" / "harness.yml").read_text(encoding="utf-8"))["harness"]
    assert cfg.get("surface_mode") == "embed", cfg.get("surface_mode")
    assert shipped.get("surface_mode") == "embed", shipped.get("surface_mode")

    page = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(encoding="utf-8")
    assert 'SecondaryButton("在浏览器打开")' in page
    assert "_set_capability_hint" in page
    assert "BROWSER_BETTER_HINT" in page
    assert "禁止自动" in page or "auto_open=False" in page or "刻意忽略 auto_open" in page

    print("OK: harness embed-default; browser is opt-in click")
    print(f"  runtime surface_mode={surface_mode()} prefer_embed={prefer_embed()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
