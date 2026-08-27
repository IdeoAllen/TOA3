# -*- coding: utf-8 -*-
"""TOA3 验收总入口：MVP 冒烟 + 控件库/QSS 门禁。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(name: str) -> int:
    print(f"\n{'=' * 60}")
    print(f"RUN {name}")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, "-u", str(SCRIPTS / name)],
        cwd=str(ROOT),
    )
    return int(result.returncode)


def main() -> int:
    steps = [
        "verify_mvp.py",
        "verify_gallery.py",
        "audit_migration.py",
        "audit_architecture.py",
    ]
    failed: list[str] = []
    for step in steps:
        code = _run(step)
        if code != 0:
            failed.append(step)

    print(f"\n{'=' * 60}")
    if failed:
        print("VERIFY ALL FAILED:", ", ".join(failed))
        return 1
    print("VERIFY ALL OK — 可进行人工验收（python -m app.main）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
