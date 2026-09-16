# -*- coding: utf-8 -*-
"""引擎 Host 进度/装载契约（STD-01 A4.7 / ARCH-05 §2.1）静态验收。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def test_local_web_host_chrome() -> None:
    _section("LocalWebHost SoftActivityBar")
    page = (ROOT / "modules" / "local_web_host" / "local_web_host_page.py").read_text(
        encoding="utf-8"
    )
    assert "SoftActivityBar" in page
    assert "def _set_activity" in page
    assert "setRange(0, 0)" not in page
    assert 'self._progress.show()' in page  # 仅安装
    assert "_set_activity(True, immediate=True)" in page
    assert "正在装载界面" in page
    assert "① 正在检测" not in page
    print("OK local_web_host chrome")


def test_hub_harness_chrome() -> None:
    _section("HubHarness SoftActivityBar")
    page = (ROOT / "modules" / "engine_host_hub" / "hub_harness_host.py").read_text(
        encoding="utf-8"
    )
    assert "SoftActivityBar" in page
    assert "def _set_activity" in page
    assert "setRange(0, 0)" not in page
    print("OK hub_harness chrome")


def test_soft_activity_widget() -> None:
    _section("SoftActivityBar API")
    from widgets import SoftActivityBar

    assert SoftActivityBar is not None
    from widgets.displays import SoftActivityBar as SAB

    assert hasattr(SAB, "set_active")
    assert hasattr(SAB, "_hard_stop")
    assert hasattr(SAB, "_tick_marquee")
    assert getattr(SAB, "_HEIGHT", 0) >= 4
    assert hasattr(SAB, "_PERIOD")
    print("OK SoftActivityBar")


def main() -> int:
    test_soft_activity_widget()
    test_local_web_host_chrome()
    test_hub_harness_chrome()
    print("\nVERIFY local_web_host_chrome OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
