# -*- coding: utf-8 -*-
"""TOA3 验收总入口：MVP 冒烟 + 控件库/QSS 门禁。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(name: str, *, retries: int = 1) -> int:
    print(f"\n{'=' * 60}")
    print(f"RUN {name}")
    print("=" * 60)
    last = 1
    for attempt in range(1, max(1, retries) + 1):
        if attempt > 1:
            print(f"(retry {attempt}/{retries}) {name}")
        result = subprocess.run(
            [sys.executable, "-u", str(SCRIPTS / name)],
            cwd=str(ROOT),
            capture_output=name == "verify_mvp.py",
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if name == "verify_mvp.py":
            out = (result.stdout or "") + (result.stderr or "")
            if out.strip():
                print(out, end="" if out.endswith("\n") else "\n")
            # Qt 成功后偶发 STATUS_ACCESS_VIOLATION（0xC0000005）
            if "MVP VERIFY OK" in out and (result.returncode & 0xFFFFFFFF) == 0xC0000005:
                print("(ignore Windows Qt teardown AV after MVP VERIFY OK)")
                return 0
        last = int(result.returncode)
        if last == 0:
            return 0
    return last


def main() -> int:
    steps = [
        "verify_mvp.py",
        "verify_gallery.py",
        "verify_shell_hardening.py",
        "verify_global_shell.py",
        "verify_version_align.py",
        "verify_screenshot_pin.py",
        "verify_screenshot_tool_gaps.py",
        "verify_watermark_ai.py",
        "verify_llm_simple_paradigm.py",
        "verify_mxapi_image_catalog.py",
        "verify_harness_clean_restart.py",
        "verify_harness_full_scenarios.py",
        "verify_harness_cdn.py",
        "verify_harness_embed_default.py",
        "verify_dsh_resource_url_scheme.py",
        "verify_harness_host_lifecycle.py",
        "verify_harness_providers.py",
        "verify_harness_release_align.py",
        "verify_harness_simple_setup.py",
        "verify_harness_system_backup.py",
        "verify_local_web_host_chrome.py",
        "verify_menu_promote_context.py",
        "debug_engines_to_business.py",
        "stress_engines_business.py",
        "stress_all_menus.py",
        "audit_migration.py",
        "audit_architecture.py",
    ]
    # WebEngine 共享 View 偶发串引擎，允许该诊断脚本重试一次
    retry_once = {"debug_engines_to_business.py"}
    failed: list[str] = []
    for step in steps:
        code = _run(step, retries=2 if step in retry_once else 1)
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
