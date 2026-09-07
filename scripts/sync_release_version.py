#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一测试/生产版本信息，并可在发版后自动 git commit。

真相源：
  - 代码/安装包：`app/version.py` → APP_VERSION
  - 生产 stable：运营台 manifest（toa-service）
  - 本机/离线回退：`config/update_manifest.yml`（须与 stable 对齐）

用法：
  # 打包成功后：按 APP_VERSION 写本地回退清单
  python scripts/sync_release_version.py --from-app

  # 运营台「设为当前版」之后：拉线上 stable 对齐本地，并提交
  python scripts/sync_release_version.py --from-live --require-match --commit

  # 仅校验三者一致
  python scripts/sync_release_version.py --verify
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UPDATE_MANIFEST = ROOT / "config" / "update_manifest.yml"
VERSION_PY = ROOT / "app" / "version.py"
HANDOFF_TODO = ROOT / "docs" / "待办总览.md"
MANIFEST_URL = (
    "https://toa-service.yczh.tech/api/toa/releases/manifest"
    "?product=TOA3&channel=stable&format=json"
)

# 发版提交默认纳入的路径（相对仓库根；不含日志/产物）
RELEASE_COMMIT_PATHS: tuple[str, ...] = (
    "app/version.py",
    "config/update_manifest.yml",
    "config/harness.yml",
    "config/migration_manifest.yml",
    "packaging/shipped_config/",
    "packaging/release_config_guard.py",
    "packaging/build_windows.py",
    "packaging/INSTALL.md",
    "scripts/sync_release_version.py",
    "scripts/verify_all.py",
    "scripts/verify_harness_release_align.py",
    "scripts/verify_harness_simple_setup.py",
    "modules/harness_agent/",
    "modules/system_settings/harness_section.py",
    "services/harness_config.py",
    "services/harness_guide.py",
    "services/harness_setup.py",
    "services/harness_sidecar.py",
    "services/harness_status.py",
    "docs/architecture/27-Portal发版与商业升级子流程.md",
    "docs/待办总览.md",
)


def _read_app_version() -> str:
    from app.version import APP_VERSION

    return str(APP_VERSION).strip()


def _fetch_live_stable(timeout: float = 12.0) -> dict:
    req = urllib.request.Request(MANIFEST_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise RuntimeError("manifest 非对象")
    return data


def _live_version(data: dict) -> str:
    return str(data.get("latest_version") or data.get("version") or "").strip()


def _write_update_manifest(
    *,
    version: str,
    download_url: str,
    download_page: str,
    release_notes: str,
    min_version: str = "3.0.0",
) -> None:
    notes = (release_notes or "").strip()
    if not notes:
        notes = f"TOA3 {version}"
    payload = {
        "product": "TOA3",
        "version": version,
        "channel": "stable",
        "release_notes": notes,
        "download_page": download_page or "https://www.yczh.tech/downloads/",
        "download_url": download_url
        or f"https://www.yczh.tech/downloads/TOA3-Setup-v{version}.exe",
        "min_version": min_version or "3.0.0",
    }
    text = (
        "# 本地回退清单（远程 manifest 不可达时使用）\n"
        "# 须与运营台当前 stable 对齐；由 scripts/sync_release_version.py 在发版后同步。\n"
        + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    )
    UPDATE_MANIFEST.write_text(text, encoding="utf-8")


def _read_local_manifest() -> dict:
    if not UPDATE_MANIFEST.is_file():
        return {}
    data = yaml.safe_load(UPDATE_MANIFEST.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def sync_from_app(*, release_notes: str = "") -> dict:
    ver = _read_app_version()
    url = f"https://www.yczh.tech/downloads/TOA3-Setup-v{ver}.exe"
    _write_update_manifest(
        version=ver,
        download_url=url,
        download_page="https://www.yczh.tech/downloads/",
        release_notes=release_notes or f"TOA3 {ver}",
    )
    return _read_local_manifest()


def sync_from_live() -> dict:
    live = _fetch_live_stable()
    ver = _live_version(live)
    if not ver:
        raise RuntimeError("线上 stable 无 version")
    _write_update_manifest(
        version=ver,
        download_url=str(live.get("download_url") or "").strip(),
        download_page=str(live.get("download_page") or "").strip()
        or "https://www.yczh.tech/downloads/",
        release_notes=str(live.get("release_notes") or "").strip() or f"TOA3 {ver}",
        min_version=str(live.get("min_version") or "3.0.0"),
    )
    return live


def _patch_todo_overview(version: str) -> None:
    if not HANDOFF_TODO.is_file():
        return
    text = HANDOFF_TODO.read_text(encoding="utf-8")
    text2 = re.sub(
        r"(\| 代码版本 \| \*\*)[0-9.]+(\*\*)",
        rf"\g<1>{version}\2",
        text,
        count=1,
    )
    text2 = re.sub(
        r"(\| 线上稳定版 \| \*\*)[0-9.]+(\*\*)",
        rf"\g<1>{version}\2",
        text2,
        count=1,
    )
    if text2 != text:
        HANDOFF_TODO.write_text(text2, encoding="utf-8")


def verify_aligned(*, require_live: bool = True) -> list[str]:
    errs: list[str] = []
    app_v = _read_app_version()
    local = _read_local_manifest()
    local_v = str(local.get("version") or "").strip()
    if local_v != app_v:
        errs.append(f"update_manifest.yml={local_v!r} ≠ APP_VERSION={app_v!r}")
    if require_live:
        live = _fetch_live_stable()
        live_v = _live_version(live)
        if live_v != app_v:
            errs.append(f"线上 stable={live_v!r} ≠ APP_VERSION={app_v!r}")
        live_url = str(live.get("download_url") or "").strip()
        local_url = str(local.get("download_url") or "").strip()
        if live_url and local_url and live_url != local_url:
            errs.append(f"download_url 本地≠线上\n  local={local_url}\n  live={live_url}")
    return errs


def git_commit_release(version: str, *, extra_paths: list[str] | None = None) -> int:
    paths = list(RELEASE_COMMIT_PATHS)
    if extra_paths:
        paths.extend(extra_paths)
    existing = [p for p in paths if (ROOT / p).exists()]
    if not existing:
        print("无待提交路径", file=sys.stderr)
        return 1
    subprocess.run(["git", "add", "--", *existing], cwd=ROOT, check=False)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if not (staged.stdout or "").strip():
        print("工作区无发版相关变更可提交（可能已提交）")
        return 0
    msg = f"release: TOA3 v{version} — sync update_manifest with stable"
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    # 不改 git config：沿用最近一次提交的作者作为 committer
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
    r = subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, env=env)
    return int(r.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description="对齐 TOA3 测试/生产版本信息")
    ap.add_argument("--from-app", action="store_true", help="按 APP_VERSION 写 update_manifest")
    ap.add_argument("--from-live", action="store_true", help="按线上 stable 写 update_manifest")
    ap.add_argument(
        "--require-match",
        action="store_true",
        help="要求 APP_VERSION 与线上 stable 一致，否则失败",
    )
    ap.add_argument("--verify", action="store_true", help="仅校验对齐")
    ap.add_argument("--commit", action="store_true", help="对齐后 git commit 发版相关路径")
    ap.add_argument("--notes", default="", help="--from-app 时写入的更新说明")
    ap.add_argument(
        "--extra",
        action="append",
        default=[],
        help="额外纳入 commit 的路径（可多次）",
    )
    args = ap.parse_args()

    if not any((args.from_app, args.from_live, args.verify, args.commit)):
        ap.print_help()
        return 2

    app_v = _read_app_version()
    print(f"APP_VERSION={app_v}")

    if args.from_live:
        live = sync_from_live()
        live_v = _live_version(live)
        print(f"已从线上 stable 同步 update_manifest → {live_v}")
        if args.require_match and live_v != app_v:
            print(
                f"错误: 线上 {live_v} ≠ APP_VERSION {app_v}。"
                "请先 bump 版本或等运营台设为当前版。",
                file=sys.stderr,
            )
            return 1
        _patch_todo_overview(live_v if args.require_match else app_v)
    elif args.from_app:
        sync_from_app(release_notes=args.notes)
        print(f"已按 APP_VERSION 同步 update_manifest → {app_v}")
        _patch_todo_overview(app_v)

    if args.verify or args.require_match:
        errs = verify_aligned(require_live=True)
        if errs:
            print("版本未对齐:", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print("VERIFY release_version_align OK（APP_VERSION = 本地回退 = 线上 stable）")

    if args.commit:
        # 提交前再读本地清单版本
        local_v = str(_read_local_manifest().get("version") or app_v).strip()
        return git_commit_release(local_v, extra_paths=list(args.extra or []))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
