#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness CDN 双包配置对齐（对标 sync_release_version.py · 与 Setup 分离）。

真相源：
  - 构包产物：`packaging/dist/harness/harness-bundles-<ver>.json` + zip/.sha256
  - 客户端钉扎：`config/harness.yml` + `packaging/shipped_config/harness.yml`（须一致）
  - CDN：`https://toa-service.yczh.tech/download/harness-{official,prefab}-<ver>.zip`

两段式（SOP-04 §5）：
  ① 上传：`cloud/deploy/upload_harness.ps1 -BundleVersion <ver>`
  ② 主理人确认「切配置」后：本脚本 `--apply --verify-cdn`

用法::

  # 预览将写入的字段（默认）
  python scripts/sync_harness_bundles.py --from-dist --version 0.1.5-rc.1

  # 切配置 + CDN 门禁
  python scripts/sync_harness_bundles.py --from-dist --version 0.1.5-rc.1 --apply --verify-cdn

  # 切配置后提交（仅 harness yml + OPS 可选）
  python scripts/sync_harness_bundles.py --from-dist --version 0.1.5-rc.1 --apply --verify-cdn --commit
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CDN_BASE = "https://toa-service.yczh.tech/download"
DIST_DIR = ROOT / "packaging" / "dist" / "harness"
PRODUCT_YML = ROOT / "config" / "harness.yml"
SHIPPED_YML = ROOT / "packaging" / "shipped_config" / "harness.yml"

BUNDLE_KEYS = (
    "official_bundle_url",
    "official_sha256",
    "official_bundle_version",
    "official_size_hint_mb",
    "prefab_bundle_url",
    "prefab_sha256",
    "prefab_bundle_version",
    "prefab_size_hint_mb",
)

COMMIT_PATHS: tuple[str, ...] = (
    "config/harness.yml",
    "packaging/shipped_config/harness.yml",
    "docs/handoff/OPS-01-交接与进度.md",
    "scripts/sync_harness_bundles.py",
)


def _load_meta(version: str, dist_dir: Path) -> dict:
    meta_path = dist_dir / f"harness-bundles-{version}.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"缺少构包元数据: {meta_path}")
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("meta 非对象")
    return data


def _sha_from_sidecar(zip_path: Path) -> str:
    side = Path(str(zip_path) + ".sha256")
    if side.is_file():
        raw = side.read_text(encoding="utf-8").strip().split()[0].lower()
        if len(raw) == 64:
            return raw
    # 回落：读整文件（慢，仅缺 sidecar 时）
    import hashlib

    h = hashlib.sha256()
    with zip_path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _artifact_map(meta: dict, version: str, dist_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    arts = meta.get("artifacts") or []
    if not isinstance(arts, list):
        raise RuntimeError("meta.artifacts 无效")
    for item in arts:
        if not isinstance(item, dict):
            continue
        flavor = str(item.get("flavor") or "").strip()
        file_name = str(item.get("file") or "").strip()
        sha = str(item.get("sha256") or "").strip().lower()
        if not flavor or not file_name:
            continue
        path = dist_dir / file_name
        if not path.is_file():
            raise FileNotFoundError(f"缺少 zip: {path}")
        if not sha:
            sha = _sha_from_sidecar(path)
        size = path.stat().st_size
        out[flavor] = {
            "file": file_name,
            "path": path,
            "sha256": sha,
            "size": size,
            "size_hint_mb": max(1, int(round(size / (1024 * 1024)))),
            "url": f"{CDN_BASE}/{file_name}",
            "version": version,
        }
    if "official" not in out or "prefab" not in out:
        raise RuntimeError("meta 须同时含 official 与 prefab 产物")
    return out


def planned_fields(version: str, dist_dir: Path | None = None) -> dict[str, str | int]:
    dist = dist_dir or DIST_DIR
    meta = _load_meta(version, dist)
    arts = _artifact_map(meta, version, dist)
    return {
        "official_bundle_url": arts["official"]["url"],
        "official_sha256": arts["official"]["sha256"],
        "official_bundle_version": version,
        "official_size_hint_mb": int(arts["official"]["size_hint_mb"]),
        "prefab_bundle_url": arts["prefab"]["url"],
        "prefab_sha256": arts["prefab"]["sha256"],
        "prefab_bundle_version": version,
        "prefab_size_hint_mb": int(arts["prefab"]["size_hint_mb"]),
    }


def _format_value(key: str, value: str | int) -> str:
    if key.endswith("_mb") or isinstance(value, int):
        return str(int(value))
    if key.endswith("_version"):
        return f'"{value}"'
    return str(value)


def _patch_yml(path: Path, fields: dict[str, str | int]) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for key, value in fields.items():
        rendered = _format_value(key, value)
        pattern = re.compile(rf"^([ \t]*{re.escape(key)}\s*:\s*).*$", re.MULTILINE)
        if not pattern.search(text):
            raise RuntimeError(f"{path.name} 缺少键 {key}")
        text = pattern.sub(rf"\g<1>{rendered}", text, count=1)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def apply_config(fields: dict[str, str | int]) -> list[str]:
    changed: list[str] = []
    for path in (PRODUCT_YML, SHIPPED_YML):
        if _patch_yml(path, fields):
            changed.append(str(path.relative_to(ROOT)))
        else:
            print(f"unchanged: {path.relative_to(ROOT)}")
    return changed


def _head(url: str) -> tuple[int, int]:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=40) as resp:
        length = int(resp.headers.get("Content-Length") or 0)
        return int(resp.status), length


def verify_cdn(fields: dict[str, str | int]) -> None:
    for flavor, url_key, sha_key, hint_key in (
        ("official", "official_bundle_url", "official_sha256", "official_size_hint_mb"),
        ("prefab", "prefab_bundle_url", "prefab_sha256", "prefab_size_hint_mb"),
    ):
        url = str(fields[url_key]).strip()
        sha = str(fields[sha_key]).strip().lower()
        assert len(sha) == 64, f"{sha_key} 非法"
        try:
            status, length = _head(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"CDN {flavor} 不可达: {exc}") from exc
        assert status in (200, 206), (flavor, status)
        assert length > 50_000_000, (flavor, length)
        hint = int(fields.get(hint_key) or 0)
        if hint > 0:
            expect = hint * 1024 * 1024
            ratio = length / expect if expect else 0
            assert 0.85 <= ratio <= 1.25, (flavor, length, hint, ratio)
        print(f"OK CDN {flavor}: HTTP {status} size={length} sha={sha[:12]}…")


def git_commit(version: str) -> int:
    existing = [p for p in COMMIT_PATHS if (ROOT / p).exists()]
    subprocess.run(["git", "add", "--", *existing], cwd=ROOT, check=False)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if not (staged.stdout or "").strip():
        print("工作区无 Harness 配置变更可提交")
        return 0
    msg = f"release: harness bundles {version} — sync CDN url/sha256"
    env = dict(os.environ)
    who = subprocess.run(
        ["git", "log", "-1", "--format=%an%n%ae"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln.strip() for ln in (who.stdout or "").splitlines() if ln.strip()]
    if len(lines) >= 2:
        env.setdefault("GIT_AUTHOR_NAME", lines[0])
        env.setdefault("GIT_AUTHOR_EMAIL", lines[1])
        env.setdefault("GIT_COMMITTER_NAME", lines[0])
        env.setdefault("GIT_COMMITTER_EMAIL", lines[1])
    return int(subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, env=env).returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description="对齐 Harness CDN 双包配置（与 Setup 分离）")
    ap.add_argument("--from-dist", action="store_true", help="从 packaging/dist/harness 元数据读")
    ap.add_argument("--version", required=True, help="包版本号，如 0.1.5-rc.1")
    ap.add_argument(
        "--dist",
        type=Path,
        default=DIST_DIR,
        help="构包目录（默认 packaging/dist/harness）",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="写入 config/harness.yml + packaging/shipped_config/harness.yml",
    )
    ap.add_argument(
        "--verify-cdn",
        action="store_true",
        help="HEAD 校验 CDN 直链与 size_hint",
    )
    ap.add_argument("--commit", action="store_true", help="切配置后 git commit")
    args = ap.parse_args()

    if not args.from_dist:
        print("请指定 --from-dist（当前仅支持构包目录真相源）", file=sys.stderr)
        return 2

    version = args.version.strip()
    dist = args.dist.expanduser().resolve()
    fields = planned_fields(version, dist)

    print(f"version: {version}")
    for k in BUNDLE_KEYS:
        print(f"  {k}: {fields[k]}")

    if args.verify_cdn and not args.apply:
        # 允许仅校验「即将写入」的 URL（须已上传）
        verify_cdn(fields)

    if not args.apply:
        print("dry-run：未写 yml。确认切配置后加 --apply [--verify-cdn] [--commit]")
        return 0

    if args.verify_cdn:
        verify_cdn(fields)

    changed = apply_config(fields)
    if changed:
        print("applied:", ", ".join(changed))
    else:
        print("applied: (已是目标值)")

    # 二次对齐：跑现有门禁脚本
    verify_script = ROOT / "scripts" / "verify_harness_cdn.py"
    if verify_script.is_file():
        r = subprocess.run([sys.executable, str(verify_script)], cwd=ROOT)
        if r.returncode != 0:
            return int(r.returncode)

    if args.commit:
        return git_commit(version)
    print("未提交：需要时再加 --commit")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, FileNotFoundError, RuntimeError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
