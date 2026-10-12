# -*- coding: utf-8 -*-
"""SOP-04 §1.1 商用冒烟：自动化可检项 + 人工项清单打印。

可自动：release_config_guard、audit_migration、授权护栏、版本对齐（本地）。
须人工勾选：干净机安装、升级不丢数据、热键手感、edition 隔离实测。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run_py(path: Path, *args: str) -> int:
    print(f"\n--- RUN {path.name} {' '.join(args)}---")
    r = subprocess.run([sys.executable, "-u", str(path), *args], cwd=str(ROOT))
    return int(r.returncode)


def _show_modules() -> list[str]:
    data = yaml.safe_load((ROOT / "config" / "app.yml").read_text(encoding="utf-8")) or {}
    items = ((data.get("menu") or {}).get("menu_items")) or []
    out: list[str] = []
    for it in items:
        if not isinstance(it, dict) or not it.get("show"):
            continue
        mid = str(it.get("id") or "").strip()
        if mid:
            out.append(mid)
    return out


def main() -> int:
    print("SOP-04 §1.1 商用冒烟（Agent 可自动部分）")
    failed: list[str] = []

    if _run_py(ROOT / "packaging" / "release_config_guard.py") != 0:
        failed.append("release_config_guard")

    if _run_py(ROOT / "scripts" / "verify_license_gate.py") != 0:
        failed.append("verify_license_gate")

    if _run_py(ROOT / "scripts" / "verify_version_align.py", "--skip-cdn") != 0:
        failed.append("verify_version_align")

    if _run_py(ROOT / "scripts" / "audit_migration.py") != 0:
        failed.append("audit_migration")

    show_ids = _show_modules()
    print(f"\nshow:true count={len(show_ids)}")

    print("\n========== 须主理人/统筹人工勾选 ==========")
    for line in (
        "1 干净机装 Setup → 首启 → 三级导航 → 退出再开不崩",
        "2 旧数据目录升级 → Wave★ 核心可进、数据不丢",
        "3 每一 show:true 进页手测不崩；有落盘则保存/再开",
        "4 热键/召唤不触发同步长联网卡死",
        "5 edition/授权隔离诚实（未授权模块提示正确）",
        "6 release_config_guard / 无 secrets 入包（上项已自动）",
    ):
        print(f"[ ] {line}")
    print("\n当前 show:true：")
    for mid in show_ids:
        print(f"  - {mid}")

    if failed:
        print("\nCOMMERCIAL SMOKE AUTO FAILED:", ", ".join(failed))
        return 1
    print("\nCOMMERCIAL SMOKE AUTO OK（人工项仍须勾选）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
