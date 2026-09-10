#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版 Harness 模板与开发默认对齐；WorkBuddy home 自愈。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _harness_block(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = data.get("harness") or data
    assert isinstance(block, dict), path
    return block


def _assert_shipped_matches_product() -> None:
    product = _harness_block(ROOT / "config" / "harness.yml")
    shipped = _harness_block(ROOT / "packaging" / "shipped_config" / "harness.yml")
    for key in ("enabled", "auto_start", "surface_mode", "web_port", "dshm_script"):
        assert shipped.get(key) == product.get(key), (key, shipped.get(key), product.get(key))
    assert shipped.get("dsh_home") in ("", None)
    assert shipped.get("dsh_bin") in ("", None)
    assert shipped.get("node_exe") in ("", None)
    assert shipped.get("surface_mode") == "embed"
    assert int(shipped.get("web_port") or 0) == 3082
    assert bool(shipped.get("enabled")) is True
    assert bool(shipped.get("auto_start")) is True


def _assert_align_migrates_workbuddy(tmp: Path) -> None:
    from services import harness_config as hc

    user = tmp / "harness.yml"
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(
        yaml.safe_dump(
            {
                "harness": {
                    "enabled": False,
                    "auto_start": False,
                    "surface_mode": "embed",
                    "web_port": 3081,
                    "dsh_home": str(Path.home() / "WorkBuddy" / "sess" / ".dsh"),
                    "node_exe": sys.executable,  # 任意存在文件，触发恢复启用
                    "dsh_bin": str(Path(__file__).resolve()),
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    hc._CACHE = None
    hc._ALIGNED_ONCE = False
    orig_user = hc._user_harness_path
    hc._user_harness_path = lambda: user  # type: ignore[assignment]
    try:
        notes = hc.align_harness_runtime_config(persist=True, force=True)
        assert notes, "expected alignment notes"
        cfg = hc.load_harness_config(force=True)
        assert not hc.is_workbuddy_home(str(cfg.get("dsh_home") or ""))
        assert bool(cfg.get("enabled")) is True
        assert bool(cfg.get("auto_start")) is True
        assert int(cfg.get("web_port") or 0) == hc.PRODUCT_WEB_PORT
        assert str(cfg.get("surface_mode")) == hc.PRODUCT_SURFACE_MODE
        home = hc.dsh_home_path()
        assert not hc.is_workbuddy_home(home)
    finally:
        hc._user_harness_path = orig_user  # type: ignore[assignment]
        hc._CACHE = None
        hc._ALIGNED_ONCE = False


def _assert_discover_never_returns_workbuddy_home() -> None:
    from services.harness_setup import discover_runtime
    from services.harness_config import is_workbuddy_home

    found = discover_runtime()
    home = str(found.get("dsh_home") or "")
    assert home, "discover must prefer TOA dsh_home"
    assert not is_workbuddy_home(home), home


def main() -> int:
    _assert_shipped_matches_product()
    tmp = ROOT / "output" / "_verify_harness_release_align"
    _assert_align_migrates_workbuddy(tmp)
    _assert_discover_never_returns_workbuddy_home()
    print("VERIFY harness_release_align OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
