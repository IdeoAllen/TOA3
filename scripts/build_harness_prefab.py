#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从本机已验证可用的 harness-runtime 打官方/预制两套 zip。

用法（在已知可用机上）::

  python scripts/build_harness_prefab.py --source ~/.toa3/harness-runtime --out packaging/dist/harness

产出::
  harness-official-<ver>.zip + .sha256
  harness-prefab-<ver>.zip + .sha256
  各含 MANIFEST.json（无 .credentials.yaml / 会话）

注意：本脚本只构包。上传与切配置走 SOP-04 §5：
  powershell -File cloud/deploy/upload_harness.ps1 -BundleVersion <ver>
  # 主理人确认「切配置」后：
  python scripts/sync_harness_bundles.py --from-dist --version <ver> --apply --verify-cdn
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.harness_prefab import (  # noqa: E402
    CORE_BUNDLES,
    FLAVOR_OFFICIAL,
    FLAVOR_PREFAB,
    dsh_bin_under,
    essential_plugins,
    portable_node_exe,
    verify_install_tree,
    write_manifest,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _copy_tree_filtered(src: Path, dst: Path) -> None:
    """复制运行时，剔除密钥、会话，以及会拖垮 copytree 的 profile node_modules 联接。"""
    skip_names = {
        ".credentials.yaml",
        ".credentials.yml",
        ".env",
    }
    skip_dir_names = {
        "sessions",
        "logs",
        "cache",
        "tmp",
        "__pycache__",
        ".dsh",  # 构包后写空骨架，避免拷坏联接/会话
    }

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        base = Path(dirpath)
        for name in names:
            if name in skip_names or name in skip_dir_names:
                ignored.add(name)
                continue
            if name.endswith(".log") and (base / name).is_file():
                ignored.add(name)
        return ignored

    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=_ignore, symlinks=False)


def _ensure_skeleton_dsh(home: Path, *, flavor: str, plugins: list[str]) -> None:
    profiles = home / "profiles" / "web"
    profiles.mkdir(parents=True, exist_ok=True)
    bundles = list(CORE_BUNDLES)
    if flavor == FLAVOR_PREFAB:
        for p in plugins:
            if p not in bundles:
                bundles.append(p)
    pkg = {
        "name": "dsh-profile-web",
        "private": True,
        "dependencies": {},
        "dsh": {"profile": {"bundles": bundles}},
    }
    (profiles / "package.json").write_text(
        json.dumps(pkg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 确保无 credentials
    for name in (".credentials.yaml", ".credentials.yml", ".env"):
        p = home / name
        if p.is_file():
            p.unlink()


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src_dir.rglob("*"):
            if path.is_file():
                arc = path.relative_to(src_dir).as_posix()
                zf.write(path, arcname=arc)


def build_one(
    *,
    source: Path,
    out_dir: Path,
    flavor: str,
    version: str,
    plugins: list[str],
) -> tuple[Path, str]:
    ok, msg = verify_install_tree(source)
    if not ok:
        # 允许源用系统 node：若无 node/ 则尝试从 PATH 提示
        node = portable_node_exe(source)
        dsh = dsh_bin_under(source)
        if not dsh.is_file():
            raise SystemExit(f"源目录无效：{msg}")
        if not node.is_file():
            raise SystemExit(
                f"源目录缺少便携 Node（{node}）。"
                "请先把 Node win-x64 解压到 source/node/ 再构建。"
            )

    with tempfile.TemporaryDirectory(prefix=f"toa3-build-{flavor}-") as tmp:
        stage = Path(tmp) / f"harness-runtime-{flavor}"
        _copy_tree_filtered(source, stage)
        home = stage / ".dsh"
        _ensure_skeleton_dsh(home, flavor=flavor, plugins=plugins)
        write_manifest(
            stage,
            flavor=flavor,
            version=version,
            plugins=plugins if flavor == FLAVOR_PREFAB else [],
            extra={
                "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "builder": "scripts/build_harness_prefab.py",
            },
        )
        # 再扫一遍禁带密钥
        for hit in home.rglob("*"):
            if hit.name in (".credentials.yaml", ".credentials.yml", ".env") and hit.is_file():
                hit.unlink()

        zip_name = f"harness-{flavor}-{version}.zip"
        zip_path = out_dir / zip_name
        _zip_dir(stage, zip_path)

    digest = _sha256(zip_path)
    (out_dir / f"{zip_name}.sha256").write_text(f"{digest}  {zip_name}\n", encoding="utf-8")
    return zip_path, digest


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 DSH 官方/预制双路线 zip")
    ap.add_argument(
        "--source",
        type=Path,
        default=Path.home() / ".toa3" / "harness-runtime",
        help="已可用的 harness-runtime 根目录",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "packaging" / "dist" / "harness",
        help="输出目录",
    )
    ap.add_argument("--version", default="", help="版本号（默认 UTC 日期）")
    ap.add_argument(
        "--official-only",
        action="store_true",
        help="只打官方精简包",
    )
    ap.add_argument(
        "--prefab-only",
        action="store_true",
        help="只打预制必备包",
    )
    args = ap.parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_dir():
        print(f"源目录不存在：{source}", file=sys.stderr)
        return 2
    version = (args.version or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    plugins = essential_plugins()

    do_official = not args.prefab_only
    do_prefab = not args.official_only
    results: list[tuple[str, Path, str]] = []

    if do_official:
        z, d = build_one(
            source=source,
            out_dir=out_dir,
            flavor=FLAVOR_OFFICIAL,
            version=version,
            plugins=[],
        )
        results.append((FLAVOR_OFFICIAL, z, d))
        print(f"official: {z}")
        print(f"  sha256: {d}")

    if do_prefab:
        z, d = build_one(
            source=source,
            out_dir=out_dir,
            flavor=FLAVOR_PREFAB,
            version=version,
            plugins=plugins,
        )
        results.append((FLAVOR_PREFAB, z, d))
        print(f"prefab:   {z}")
        print(f"  sha256: {d}")
        if not plugins:
            print("  警告：prefab_essential_plugins 为空，预制包与官方包插件集相同。")

    cdn_base = "https://toa-service.yczh.tech/download"
    arts_payload = []
    for f, z, d in results:
        size_mb = max(1, int(round(z.stat().st_size / (1024 * 1024))))
        arts_payload.append(
            {
                "flavor": f,
                "file": z.name,
                "sha256": d,
                "size_bytes": z.stat().st_size,
                "size_hint_mb": size_mb,
                "url": f"{cdn_base}/{z.name}",
            }
        )
    off = next((a for a in arts_payload if a["flavor"] == FLAVOR_OFFICIAL), None)
    pre = next((a for a in arts_payload if a["flavor"] == FLAVOR_PREFAB), None)
    meta = {
        "version": version,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifacts": arts_payload,
        "harness_yml_snippet": {
            "official_bundle_url": (off or {}).get("url", ""),
            "official_sha256": (off or {}).get("sha256", ""),
            "official_bundle_version": version,
            "official_size_hint_mb": (off or {}).get("size_hint_mb", 0),
            "prefab_bundle_url": (pre or {}).get("url", ""),
            "prefab_sha256": (pre or {}).get("sha256", ""),
            "prefab_bundle_version": version,
            "prefab_size_hint_mb": (pre or {}).get("size_hint_mb", 0),
            "prefab_essential_plugins": plugins,
        },
    }
    meta_path = out_dir / f"harness-bundles-{version}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"meta: {meta_path}")
    print("下一步（SOP-04 §5）：")
    print(f"  powershell -File cloud/deploy/upload_harness.ps1 -BundleVersion {version}")
    print(f"  # 主理人确认切配置后：")
    print(
        f"  python scripts/sync_harness_bundles.py --from-dist --version {version} "
        "--apply --verify-cdn"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
