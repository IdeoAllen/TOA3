#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness 交付门禁（默认不碰用户本机 3082 / ~/.toa3）。

默认：契约 + CDN + 沙箱干净机（隔离端口 13082）。
显式 --live：才对用户当前 runtime 做启停往返（慎用）。

用法：
  python scripts/verify_harness_delivery.py
  python scripts/verify_harness_delivery.py --skip-sandbox
  python scripts/verify_harness_delivery.py --live
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    "verify_harness_full_scenarios.py",
    "verify_harness_cdn.py",
    "verify_harness_embed_default.py",
    "verify_harness_browser_default.py",
    "verify_harness_clean_restart.py",
    "verify_harness_simple_setup.py",
    "verify_harness_release_align.py",
    "verify_harness_providers.py",
]


def _run(script: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *(extra or [])]
    print(f"\n>>> {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    live = "--live" in sys.argv
    skip_sandbox = "--skip-sandbox" in sys.argv
    failed: list[str] = []
    for step in STEPS:
        if _run(step) != 0:
            failed.append(step)

    # 默认 dry lifecycle（源码/效用契约，不 stop 用户服务）
    if _run("verify_harness_host_lifecycle.py") != 0:
        failed.append("verify_harness_host_lifecycle.py")

    if not skip_sandbox:
        if _run("verify_harness_sandbox_clean.py") != 0:
            failed.append("verify_harness_sandbox_clean.py")

    if live:
        if _run("verify_harness_host_lifecycle.py", ["--live"]) != 0:
            failed.append("verify_harness_host_lifecycle.py --live")

    print(f"\n{'=' * 60}")
    if failed:
        print("HARNESS DELIVERY FAILED:", ", ".join(failed))
        return 1
    mode = "live+sandbox" if live else "sandbox"
    print(f"HARNESS DELIVERY OK ({mode}; user 3082 untouched by default)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
