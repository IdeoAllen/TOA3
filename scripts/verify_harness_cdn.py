#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness CDN 双包可达性 + 配置/发版模板对齐（无感就绪门禁）。

默认只做 HEAD（不拉 400MB+ zip）。加 --sample 时抽样读 zip 头校验格式。
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _block(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = data.get("harness") or data
    assert isinstance(block, dict), path
    return block


def _head(url: str) -> tuple[int, int]:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=25) as resp:
        length = int(resp.headers.get("Content-Length") or 0)
        return int(resp.status), length


def _sample_zip_ok(url: str) -> None:
    req = urllib.request.Request(url, headers={"Range": "bytes=0-3"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        head = resp.read(4)
    assert head[:2] == b"PK", f"not a zip: {url}"


def main() -> int:
    product = _block(ROOT / "config" / "harness.yml")
    shipped = _block(ROOT / "packaging" / "shipped_config" / "harness.yml")
    sample = "--sample" in sys.argv

    for key in (
        "official_bundle_url",
        "official_sha256",
        "official_bundle_version",
        "prefab_bundle_url",
        "prefab_sha256",
        "prefab_bundle_version",
    ):
        assert product.get(key), f"config missing {key}"
        assert shipped.get(key) == product.get(key), (key, shipped.get(key), product.get(key))

    for flavor, url_key, sha_key, hint_key in (
        ("official", "official_bundle_url", "official_sha256", "official_size_hint_mb"),
        ("prefab", "prefab_bundle_url", "prefab_sha256", "prefab_size_hint_mb"),
    ):
        url = str(product[url_key]).strip()
        sha = str(product[sha_key]).strip().lower()
        assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha), sha_key
        try:
            status, length = _head(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"FAIL CDN {flavor}: {exc}", file=sys.stderr)
            return 1
        assert status in (200, 206), (flavor, status)
        assert length > 50_000_000, (flavor, length)
        hint_mb = float(product.get(hint_key) or 0)
        if hint_mb > 0:
            expect = hint_mb * 1024 * 1024
            ratio = length / expect if expect else 0
            assert 0.85 <= ratio <= 1.25, (flavor, length, hint_mb, ratio)
        if sample:
            _sample_zip_ok(url)
        print(f"OK CDN {flavor}: HTTP {status} size={length} sha256={sha[:12]}…")

    # 诊断包服务存在且可导出
    from services.harness_diagnose import export_diagnostic_pack

    ok, msg, path = export_diagnostic_pack()
    assert ok and path is not None and path.is_file(), msg
    # 脱敏：包内不得出现 sk- 长密钥形态（粗检）
    import zipfile

    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        assert "status.json" in names and "README.txt" in names
        blob = b"".join(zf.read(n) for n in zf.namelist())
        assert b".credentials.yaml" not in blob
    print(f"OK diagnostic pack: {path.name}")

    print("VERIFY harness_cdn OK" + (" (sample)" if sample else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
