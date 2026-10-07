# -*- coding: utf-8 -*-
"""门禁：Harness 系统备份 / 版本信息 / 内核漂移可提示更新。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.harness_prefab import runtime_update_available
    from services.harness_system_backup import (
        KEEP_GENERATIONS,
        list_system_backups,
        open_backup_dir,
        version_info,
    )

    info = version_info()
    assert info.get("install_root"), "version_info 缺 install_root"
    assert "dsh_core" in info and "dsh_pinned" in info
    assert "needs_repin" in info

    root = open_backup_dir()
    assert isinstance(root, Path)
    assert root.is_dir()
    assert KEEP_GENERATIONS >= 2

    snaps = list_system_backups()
    assert isinstance(snaps, list)

    # 漂移机：应给出可更新信息；干净机可为 None
    upd = runtime_update_available()
    if info.get("core_drift") or info.get("bundle_drift"):
        assert upd is not None, "有漂移时 runtime_update_available 应非空"
        assert upd.get("core_drift") or upd.get("version_diff") or upd.get("sha_diff")

    page = (ROOT / "modules/harness_agent/harness_agent_page.py").read_text(encoding="utf-8")
    assert "_on_backup_system" in page
    assert "备份系统" in page
    dlg = (ROOT / "modules/harness_agent/maintain_dialog.py").read_text(encoding="utf-8")
    assert "备份系统" in dlg
    assert "运行环境版本" in dlg
    print("verify_harness_system_backup: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
