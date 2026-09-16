#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本一致性门禁：TOA 三源 + Harness 双包钉扎对齐。

TOA：APP_VERSION = update_manifest =（可选 --require-live）线上 stable
Harness：config/harness.yml = packaging/shipped_config/harness.yml；CDN HEAD 200；
         内核钉扎 DSH_PINNED_VERSION 可与 bundle_version 不同（包号可带重建后缀）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_sync_mod():
    path = ROOT / "scripts" / "sync_release_version.py"
    spec = importlib.util.spec_from_file_location("toa3_sync_release_version", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _harness_block(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = data.get("harness") or data
    assert isinstance(block, dict), path
    return block


def main() -> int:
    from app.version import APP_VERSION
    from services.harness_setup import DSH_PINNED_VERSION

    errs: list[str] = []
    sync = _load_sync_mod()

    local = yaml.safe_load((ROOT / "config" / "update_manifest.yml").read_text(encoding="utf-8")) or {}
    local_v = str(local.get("version") or "").strip()
    if local_v != APP_VERSION:
        errs.append(f"update_manifest={local_v!r} ≠ APP_VERSION={APP_VERSION!r}")
    require_live = "--require-live" in sys.argv
    for e in sync.verify_aligned(require_live=require_live):
        errs.append(e)
    print(f"TOA APP={APP_VERSION} local_manifest={local_v} require_live={require_live}")

    product = _harness_block(ROOT / "config" / "harness.yml")
    shipped = _harness_block(ROOT / "packaging" / "shipped_config" / "harness.yml")
    keys = (
        "official_bundle_url",
        "official_sha256",
        "official_bundle_version",
        "prefab_bundle_url",
        "prefab_sha256",
        "prefab_bundle_version",
    )
    for key in keys:
        if product.get(key) != shipped.get(key):
            errs.append(f"harness {key}: config≠shipped ({product.get(key)!r} vs {shipped.get(key)!r})")
    print(
        "Harness bundle official/prefab=",
        product.get("official_bundle_version"),
        "/",
        product.get("prefab_bundle_version"),
        "dsh_core_pin=",
        DSH_PINNED_VERSION,
    )

    if "--skip-cdn" not in sys.argv:
        for flavor, url_key in (
            ("official", "official_bundle_url"),
            ("prefab", "prefab_bundle_url"),
        ):
            url = str(product.get(url_key) or "").strip()
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    status = int(resp.status)
                if status not in (200, 206):
                    errs.append(f"CDN {flavor} HTTP {status}")
                else:
                    print(f"CDN {flavor} OK {status}")
            except Exception as exc:
                errs.append(f"CDN {flavor}: {exc}")

    mf = Path.home() / ".toa3" / "harness-runtime" / "MANIFEST.json"
    if mf.is_file():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errs.append(f"MANIFEST 损坏: {exc}")
            data = {}
        flavor = str(data.get("flavor") or "prefab")
        installed = str(data.get("version") or "").strip()
        expect_key = "prefab_bundle_version" if flavor == "prefab" else "official_bundle_version"
        expect = str(product.get(expect_key) or "").strip()
        print(f"local MANIFEST flavor={flavor} version={installed} expect={expect}")
        if installed and expect and installed != expect:
            if "--fix-manifest" in sys.argv:
                errs.append(f"MANIFEST {installed!r} ≠ pin {expect!r}")
            else:
                print(f"WARN MANIFEST drift {installed} → pin {expect}")

    if errs:
        print("FAIL version_align:")
        for e in errs:
            print(" -", e)
        return 1
    print("VERIFY version_align OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
