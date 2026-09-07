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
        "verify_shell_hardening.py",
        "verify_screenshot_pin.py",
        "verify_watermark_ai.py",
        "verify_llm_simple_paradigm.py",
        "verify_harness_clean_restart.py",
        "verify_harness_providers.py",
        "verify_harness_release_align.py",
        "verify_harness_simple_setup.py",
        "verify_menu_promote_context.py",
        "debug_engines_to_business.py",
        "stress_engines_business.py",
        "stress_all_menus.py",
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
    print("VERIFY ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
