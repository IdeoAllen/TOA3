# -*- coding: utf-8 -*-
"""C-11：Harness 默认浏览器优先。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.harness_config import PRODUCT_SURFACE_MODE, load_harness_config
    from services.harness_guide import GUIDE_INTRO, STEP_HINTS
    from services.harness_surface import SURFACE_BROWSER, prefer_browser, surface_mode

    assert PRODUCT_SURFACE_MODE == SURFACE_BROWSER == "browser"
    product = load_harness_config(force=True)
    # 用户覆盖可能仍是 embed；产品文件须为 browser
    import yaml

    shipped = yaml.safe_load(
        (ROOT / "packaging" / "shipped_config" / "harness.yml").read_text(encoding="utf-8")
    )["harness"]
    cfg = yaml.safe_load((ROOT / "config" / "harness.yml").read_text(encoding="utf-8"))["harness"]
    assert cfg.get("surface_mode") == "browser", cfg.get("surface_mode")
    assert shipped.get("surface_mode") == "browser", shipped.get("surface_mode")
    assert "浏览器" in GUIDE_INTRO
    assert "浏览器" in STEP_HINTS.get("start", "")

    page = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(encoding="utf-8")
    assert 'PrimaryButton("在浏览器打开")' in page
    assert 'SecondaryButton("启动服务")' in page

    print("OK: harness browser-first defaults + CTA")
    print(f"  runtime surface_mode={surface_mode()} prefer_browser={prefer_browser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
