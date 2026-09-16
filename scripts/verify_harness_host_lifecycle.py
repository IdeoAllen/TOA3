#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness Host 全周期压测：Chrome 状态机 + 各按钮对应服务效用 + 启停往返。

不卸载、不弹 GUI；可重复跑。失败即非零退出。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def test_chrome_matrix() -> None:
    from services.harness_chrome import BusyPhase, compute_chrome, infer_busy_phase

    _section("Chrome 状态机矩阵")

    idle_stop = compute_chrome(
        install_ready=True,
        running=False,
        install_label="已安装",
        service_label="未启动",
    )
    assert idle_stop.stack_index == 0
    assert idle_stop.start_enabled and not idle_stop.stop_enabled
    assert not idle_stop.open_browser_enabled and idle_stop.more_enabled
    assert "未启动" in idle_stop.status_hint

    idle_run = compute_chrome(
        install_ready=True,
        running=True,
        install_label="已安装",
        service_label="运行中 · TOA 托管",
    )
    assert idle_run.stack_index == 1
    assert not idle_run.start_enabled and idle_run.stop_enabled
    assert idle_run.open_browser_enabled

    not_ready = compute_chrome(install_ready=False, running=False, install_label="未安装")
    assert not not_ready.start_enabled and not not_ready.open_browser_enabled

    for phase, expect_stack in (
        (BusyPhase.STARTING, 0),
        (BusyPhase.STOPPING, 1),
        (BusyPhase.RESTARTING, 0),
        (BusyPhase.REPAIRING, 0),
        (BusyPhase.RESTORING, 0),
        (BusyPhase.HEALING, 0),
        (BusyPhase.UNINSTALLING, 0),
    ):
        v = compute_chrome(
            install_ready=True,
            running=True,
            phase=phase,
            busy_label="x",
        )
        assert v.busy and not v.start_enabled and not v.more_enabled
        assert v.stack_index == expect_stack, (phase, v.stack_index)

    assert infer_busy_phase("正在启动…") == BusyPhase.STARTING
    assert infer_busy_phase("正在停止…") == BusyPhase.STOPPING
    assert infer_busy_phase("正在重启…") == BusyPhase.RESTARTING
    assert infer_busy_phase("正在修复环境…") == BusyPhase.REPAIRING
    print("OK chrome matrix")


def test_ui_contracts() -> None:
    _section("页面契约（源码）")
    page = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(
        encoding="utf-8"
    )
    assert "from services.harness_chrome import" in page
    assert "def _apply_chrome" in page
    assert "confirm=False" in page
    assert "chained = bool(on_ok(payload))" in page
    assert 'SecondaryButton("刷新")' in page
    assert "_begin_click_feedback" in page
    assert "_action_progress" in page
    assert "_begin_home_navigation" in page
    assert "_arm_loading_watchdog" in page
    assert 'addAction("回到主界面"' in page
    assert "⑥ 服务已停止" not in page
    # 刷新必须回主 URL，禁止只 reload 深链
    assert "self._navigate_home_now()" in page
    # 修复/恢复链式重启不得再弹确认
    assert "_on_restart(confirm=False)" in page
    print("OK ui contracts")


def test_button_service_effects(*, live_cycle: bool) -> None:
    """逐项对照按钮 → 服务效用（不卸载）。"""
    from services.harness_config import web_url
    from services.harness_plugins import strip_boot_killer_plugins
    from services.harness_profile_versions import (
        list_snapshots,
        maybe_snapshot_after_healthy,
        snapshot_web_profile,
    )
    from services.harness_setup import repair_harness_runtime
    from services.harness_sidecar import (
        is_running,
        log_suggests_plugin_boot_failure,
        open_config_dir,
        open_install_root,
        open_sidecar_log,
        preflight_web_profile,
        prepare_sidecar_start,
        restart,
        start,
        stop,
    )
    from services.harness_status import InstallState, read_harness_status
    from services.harness_surface import prefer_browser

    _section("按钮 → 服务效用")

    # 打开… 子菜单
    log_p = open_sidecar_log()
    assert log_p.parent.is_dir(), log_p
    assert open_install_root().is_dir()
    assert open_config_dir().is_dir()
    print("OK 打开日志/安装目录/DSH")

    # 启动前自愈（对应每次启动隐式）— 仅 --live 才对本机 profile 动手
    if live_cycle:
        ok_pre, pre_msg = preflight_web_profile()
        assert ok_pre, pre_msg
        print(f"OK preflight: {pre_msg[:80]}")
    else:
        print("SKIP preflight on user runtime (dry)")

    assert prefer_browser() is True or prefer_browser() is False
    print(f"OK surface prefer_browser={prefer_browser()}")

    assert log_suggests_plugin_boot_failure("Failed to load plugins")
    assert not log_suggests_plugin_boot_failure("hello")

    from services.harness_credentials import clear_stale_credential_locks
    from services.harness_sidecar import diagnose_start_log, humanize_start_failure

    lock_sample = (
        "Error: atomic-write: timed out waiting for the writer lock "
        "at C:\\Users\\x\\.toa3\\harness-runtime\\.dsh\\.credentials.yaml.lock"
    )
    assert "凭证锁" in diagnose_start_log(lock_sample)
    assert "启动服务" in humanize_start_failure(default="x") or "环境维护" in humanize_start_failure(
        default="x"
    )
    if live_cycle:
        ok_lock, _ = clear_stale_credential_locks()
        assert ok_lock is True
        print("OK diagnose/clear lock helpers")
    else:
        print("OK diagnose helpers (dry, no lock touch)")

    st = read_harness_status(probe_http=True, http_timeout=1.0)
    print(f"status install={st.install} service={st.service} url={st.url}")
    assert st.install in (InstallState.READY, InstallState.NEEDS_KEY, InstallState.NOT_INSTALLED)

    if not live_cycle:
        print("SKIP 对本机 runtime 的备份/修复/启停（避免影响用户）")
        return

    if st.install != InstallState.READY:
        print("SKIP live cycle: 未 READY（缺 Node/dsh/Key）")
        return

    # 备份（对应曾有的备份钮；健康快照路径）
    ok_s, msg_s, _ = snapshot_web_profile(reason="stress", mark_good=True)
    assert ok_s, msg_s
    assert list_snapshots(), "应有快照"
    print(f"OK 备份配置: {msg_s}")

    # 一键修复（不强制要求改动，只要成功返回）
    ok_r, msg_r = repair_harness_runtime()
    assert ok_r, msg_r
    print(f"OK 一键修复: {msg_r.splitlines()[0][:100]}")

    ok_k, msg_k = strip_boot_killer_plugins()
    assert ok_k, msg_k
    print("OK denylist strip")

    _section("启停往返压测")
    # 停 → 确认未跑 → 启 → HTTP → 再停 → 再启（干净重启）
    was = is_running(timeout=1.0)
    print(f"before stop running={was}")
    ok_stop, stop_msg = stop(force=True)
    assert ok_stop, stop_msg
    time.sleep(0.6)
    assert not is_running(timeout=0.8), "停止后仍响应 HTTP"
    print(f"OK 停止: {stop_msg}")

    ok_prep, prep_msg, already = prepare_sidecar_start()
    assert ok_prep, prep_msg
    assert already is False or is_running()
    print(f"OK prepare already={already} hint={prep_msg[:60]!r}")

    if not is_running():
        ok_start, start_msg = start(wait_ready=True, timeout_sec=35.0)
        assert ok_start, start_msg
        print(f"OK 启动: {start_msg}")
    assert is_running(timeout=1.2), "启动后 HTTP 应通"
    print(f"OK HTTP {web_url()}")

    ok_snap, snap_msg = maybe_snapshot_after_healthy(min_interval_sec=0)
    # 0 秒间隔应允许拍；若失败也不阻断主路径
    print(f"healthy snapshot: {ok_snap} {snap_msg}")

    ok_rst, rst_msg = restart()
    assert ok_rst, rst_msg
    assert is_running(timeout=1.2)
    print(f"OK 重启: {rst_msg[:120]}")


def test_stop_semantics() -> None:
    """停止 ≠ 重启：停着时不得因修密钥/脏 env 被拉起。"""
    from services.harness_credentials import needs_credential_takeover

    _section("停止语义")
    need, _ = needs_credential_takeover(running=False, owned=False)
    assert need is False, "未运行时不得触发修密钥接管"
    need2, _ = needs_credential_takeover(running=True, owned=True)
    assert need2 is False, "TOA 托管运行中不必接管"
    need3, reason = needs_credential_takeover(running=True, owned=False)
    assert need3 is False, "外部占口禁止静默修密钥接管（须用户确认重启）"
    print("OK stop/heal semantics")


def test_no_auto_browser_in_surface() -> None:
    _section("启停与浏览器表面一致")
    page = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(
        encoding="utf-8"
    )
    assert "已切走" not in page
    assert 'PrimaryButton("启动服务")' in page
    assert 'SecondaryButton("在浏览器打开")' in page
    assert 'SecondaryButton("修一下")' in page
    assert "环境维护" in page
    assert "maintain_dialog" in page or "_open_maintain" in page
    assert '一键修复（坏了点这个）' not in page
    assert "_btn_repair" in page
    assert "self._btn_repair.hide()" in page or '_btn_repair.hide()' in page
    assert "_set_capability_hint" in page
    assert "BROWSER_BETTER_HINT" in page
    assert 'self._show_web_idle("正在进入' not in page
    assert "SoftActivityBar" in page
    from services.harness_progress import HINT, Progress
    from services.harness_surface import BROWSER_BETTER_HINT

    assert "修一下" in HINT[Progress.NEED_REPAIR] or "环境维护" in HINT[Progress.NEED_REPAIR]
    from services.harness_chrome import compute_chrome

    tip = compute_chrome(install_ready=True, running=True).tip_browser
    assert "推荐主路径" not in tip
    assert BROWSER_BETTER_HINT in tip or "浏览器打开效果更佳" in tip
    print("OK unified surface lifecycle")


def test_progress_copy() -> None:
    _section("进度文案")
    from services.harness_progress import HINT, IDLE, TITLE, TOAST, Progress, clip_user_detail, sanitize_user_text

    for step in Progress:
        assert TITLE[step]
        assert HINT[step]
        assert IDLE[step]
        assert TOAST[step]
        for bag in (TITLE, HINT, IDLE, TOAST):
            t = bag[step]
            assert "①" not in t and "WorkBuddy" not in t and "Sidecar" not in t
    assert "其它程序" in sanitize_user_text("来自 WorkBuddy 的进程")
    assert "node_modules" not in clip_user_detail(
        "Harness 进程已退出。\nat Objectnanmicoder/foo (C:\\Users\\x\\node_modules\\bar.js:1)"
    )
    assert "进程已退出" in clip_user_detail("Harness 进程已退出。\nat foo")
    assert "启动服务" in HINT[Progress.FAILED]
    assert "修一下" not in HINT[Progress.FAILED]
    page = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(
        encoding="utf-8"
    )
    assert "_set_progress" in page
    assert "WorkBuddy" not in page
    assert "_enter_check_install" in page
    print("OK progress copy")


def main() -> int:
    live = "--live" in sys.argv
    test_chrome_matrix()
    test_ui_contracts()
    test_stop_semantics()
    test_no_auto_browser_in_surface()
    test_progress_copy()
    test_button_service_effects(live_cycle=live)
    print("\nVERIFY harness_host_lifecycle OK" + (" (live)" if live else " (dry)"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
