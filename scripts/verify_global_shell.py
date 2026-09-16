# -*- coding: utf-8 -*-
"""全局壳能力档案验证：配置点可解析 + 归属策略 + 双击 Ctrl hook 冒烟。"""
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
    from services.global_shell_features import GLOBAL_FEATURES, catalog_rows
    from services.hotkey_service import HotkeyService, _parse_hotkey
    from services.module_hotkeys import global_module_bindings
    from services.runtime_paths import is_frozen

    hk = get_hotkeys_config()
    errors: list[str] = []

    # —— 档案完整性 ——
    if len(GLOBAL_FEATURES) < 8:
        errors.append("GLOBAL_FEATURES 条目过少")
    print("catalog:")
    for row in catalog_rows():
        print(f"  [{row['layer']}] {row['id']}: {row['title']} keys={row['keys']}")

    # —— 配置点默认值 ——
    drop_on = bool(hk.get("enable_drop_open_desktop", True))
    immersive_on = bool(hk.get("enable_immersive_hotkey", True))
    print("drop_open_desktop=", drop_on, "immersive_hotkey=", immersive_on)

    # —— 键位可解析 ——
    must_parse = [
        ("screenshot", str(hk.get("screenshot") or "Alt+A")),
        ("screenshot_region", str(hk.get("screenshot_region") or "Alt+Shift+A")),
        ("exit_app", str(hk.get("exit_app") or "Ctrl+Q")),
        ("restart_app", str(hk.get("restart_app") or "Ctrl+Shift+R")),
        ("toggle_fullscreen", str(hk.get("toggle_fullscreen") or "F11")),
        ("open_settings", str(hk.get("open_settings") or "Alt+S")),
    ]
    for seq, mid in global_module_bindings().items():
        must_parse.append((f"module:{mid}", seq))
    for name, seq in must_parse:
        if not seq or seq.lower() == "none":
            continue
        if name.startswith("screenshot") and not hk.get("enable_screenshot", True):
            continue
        if _parse_hotkey(seq) is None and not str(seq).lower().startswith("double"):
            errors.append(f"无法解析 {name}={seq!r}")

    # —— 退出键须带修饰（防误触）——
    exit_seq = str(hk.get("exit_app") or "Ctrl+Q")
    parsed_exit = _parse_hotkey(exit_seq)
    if parsed_exit is not None and parsed_exit[0] == 0:
        errors.append(f"exit_app 须带修饰键: {exit_seq}")

    # —— 归属 ——
    ok, reason = should_register_global_hotkeys()
    print("frozen=", is_frozen(), "owner_ok=", ok, reason)
    print("release_running=", release_toa_running(), "hint=", peer_hotkey_holder_hint() or "-")

    # —— 双击 Ctrl hook（装上再卸，不长期占钩子）——
    if hk.get("enable_global_toggle", True) and ok:
        from services.double_ctrl_summon import DoubleCtrlSummonService

        hook = DoubleCtrlSummonService()
        err = hook.apply(lambda: None)
        if err:
            errors.append(f"Double+Ctrl hook: {err}")
        else:
            # 冒烟：CallNextHookEx 不得因 LPARAM 溢出抛错（否则吞键）
            try:
                import ctypes
                from ctypes import wintypes

                if hook._call_next and hook._hook_id:
                    hook._call_next(hook._hook_id, 0, 0, wintypes.LPARAM(0))
                print("double_ctrl hook OK (CallNextHookEx smoke)")
            except Exception as exc:
                errors.append(f"Double+Ctrl CallNextHookEx: {exc}")
        hook.stop()
    else:
        print("double_ctrl hook skipped (disabled or not owner)")

    # —— RegisterHotKey 抽样（随后清空）——
    if ok and hk.get("enable_screenshot", True):
        svc = HotkeyService()
        sample_key = str(hk.get("screenshot") or "Alt+A")
        errs = svc.register_many({sample_key: lambda: None})
        if errs:
            print("sample_register warn:", errs)
        else:
            print("sample_register OK:", svc.active_specs())
        svc.clear()

    # —— 拖入入口存在 ——
    from app.shell import MainShell

    if not hasattr(MainShell, "open_drop_paths"):
        errors.append("MainShell.open_drop_paths 缺失")

    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1
    print("VERIFY global_shell OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
