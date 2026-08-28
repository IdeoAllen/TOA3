#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOA3 v3.1.0 发布冒烟：导入 + manifest + trial-start 路由存在。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import APP_VERSION  # noqa: E402
from services.update_check import check_for_update  # noqa: E402
from services.tray_menu import tray_module_ids  # noqa: E402


def main() -> int:
    assert APP_VERSION == "3.1.0", APP_VERSION
    mids = tray_module_ids()
    assert "quick_notepad" in mids
    r = check_for_update()
    print("version", APP_VERSION)
    print("tray", mids)
    print("manifest", r.latest_version, r.has_update, r.source)
    cloud = ROOT.parent / "toa-cloud" / "backend" / "services" / "toa_license_service.py"
    assert cloud.is_file()
    text = cloud.read_text(encoding="utf-8")
    assert "def start_trial" in text
    print("trial-start backend ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
