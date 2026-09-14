# -*- coding: utf-8 -*-
"""热键清单自检：配置解析 + RegisterHotKey 抽样 + 归属策略。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from services.config_service import get_hotkeys_config
    from services.edition_isolation import (
        peer_hotkey_holder_hint,
        release_toa_running,
        should_register_global_hotkeys,
    )
    from services.hotkey_service import HotkeyService, _parse_hotkey
    from services.module_hotkeys import global_module_bindings
    from services.runtime_paths import is_frozen

    hk = get_hotkeys_config()
    expected = []
    if hk.get("enable_screenshot", True):
        expected.append(("screenshot", str(hk.get("screenshot") or "")))
        expected.append(("screenshot_full", str(hk.get("screenshot_region") or "")))
    for seq, mid in global_module_bindings().items():
        expected.append((f"module:{mid}", seq))

    bad_parse = []
    for name, seq in expected:
        if not seq or seq.lower() == "none":
            continue
        if _parse_hotkey(seq) is None:
            bad_parse.append((name, seq))
    if bad_parse:
        print("FAIL parse:", bad_parse)
        return 1

    ok, reason = should_register_global_hotkeys()
    print("frozen=", is_frozen(), "owner_ok=", ok, reason)
    print("release_running=", release_toa_running(), "hint=", peer_hotkey_holder_hint() or "-")

    # 抽样注册（随后清掉，避免污染本机）
    svc = HotkeyService()
    sample = {
        str(hk.get("screenshot") or "Alt+A"): lambda: None,
        str(hk.get("open_notepad") or "Alt+N"): lambda: None,
    }
    errs = svc.apply(sample)
    print("sample_register:", "OK" if not errs else errs)
    print("active:", svc.active_specs())
    svc.clear()

    print("configured keys:")
    for name, seq in expected:
        print(f"  {name}: {seq or '(空)'}")
    print("VERIFY hotkeys inventory OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
