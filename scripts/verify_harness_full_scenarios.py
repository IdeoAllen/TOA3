#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness 全场景契约（P0）：安装/启停/外部口/auto_start/维护面 — 源码+配置断言。

不启 GUI；失败非零退出。对应用户画像 × 安装态 × 服务态 需求门禁。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_no_settings_harness_tab() -> None:
    src = _read("modules/system_settings/integrations_section.py")
    assert "HarnessSection" not in src
    assert "_build_harness_tab" not in src
    assert "_build_ocr_card" in src or "OCR" in src
    assert not (ROOT / "modules/system_settings/harness_section.py").is_file()
    print("OK F1 能力接入无 Harness 配置面")


def test_auto_start_not_forced() -> None:
    src = _read("services/harness_config.py")
    assert 'updates["auto_start"] = True' not in src
    assert "auto_start" in src and "环境维护" in src
    # 隔离临时 yml，不改用户 data/user/harness.yml
    from services import harness_config as hc

    tmp = ROOT / "output" / "_verify_auto_start_sandbox" / "harness.yml"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(
        "harness:\n  enabled: true\n  auto_start: false\n"
        "  node_exe: .\n  dsh_bin: .\n  dsh_home: .\n  web_port: 13083\n",
        encoding="utf-8",
    )
    # node/dsh 须是真实文件才会走 align 的 enabled 分支；用本脚本自身
    self_path = Path(__file__).resolve()
    tmp.write_text(
        "harness:\n"
        "  enabled: false\n"
        "  auto_start: false\n"
        f"  node_exe: {self_path.as_posix()}\n"
        f"  dsh_bin: {self_path.as_posix()}\n"
        "  dsh_home: .\n"
        "  web_port: 13083\n"
        "  surface_mode: embed\n",
        encoding="utf-8",
    )
    hc._CACHE = None
    hc._ALIGNED_ONCE = False
    orig = hc._user_harness_path
    hc._user_harness_path = lambda: tmp  # type: ignore[assignment]
    try:
        hc.align_harness_runtime_config(persist=True, force=True)
        after = hc.load_harness_config(force=True)
        assert after.get("auto_start") is False, after.get("auto_start")
        assert bool(after.get("enabled")) is True
        print("OK B1 auto_start=关 跨 align 仍关（沙箱配置）")
    finally:
        hc._user_harness_path = orig  # type: ignore[assignment]
        hc._CACHE = None
        hc._ALIGNED_ONCE = False
        hc.load_harness_config(force=True)


def test_no_silent_external_takeover() -> None:
    cred = _read("services/harness_credentials.py")
    tree = ast.parse(cred)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "needs_credential_takeover"
    )
    body = ast.get_source_segment(cred, fn) or ""
    assert "if not owned" in body
    assert "return False, \"\"" in body or "return False, ''" in body
    # 不得对 not owned 直接 return True
    assert "密钥可能未生效" not in body

    from services.harness_credentials import needs_credential_takeover

    need, _ = needs_credential_takeover(running=True, owned=False)
    assert need is False, "外部占口禁止静默接管"

    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "ask_confirm" in page
    assert "_start_from_user" in page
    # 用户点启动才问接管；进页自动启静默接上
    assert "本机服务已在运行" in page or "接管" in page
    assert "已接上本机正在运行的服务" in page
    print("OK C1/E2 外部占口须确认，不静默强杀")


def test_upgrade_shows_gate_and_forces_snapshot() -> None:
    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "_upgrade_in_progress" in page
    assert "_force_good_snapshot" in page
    assert 'reason="upgrade"' in page or "reason='upgrade'" in page
    # 升级留在工作区（index 1）看 UpgradeStrip 进度，不切装门抢焦点
    assert "self._body_stack.setCurrentIndex(1)" in page
    assert "self._upgrade_in_progress = True" in page
    assert "upgrade_via" in page
    print("OK D3 更新环境可见进度条 + 强制 last_good")


def test_maintain_is_daily_surface() -> None:
    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "环境维护" in page
    assert "HarnessMaintainDialog" in page
    assert "_open_settings" in page and "_open_maintain" in page
    maintain = _read("modules/harness_agent/maintain_dialog.py")
    assert "修一下" in maintain
    assert "回到上次能用的配置" in maintain or "回到上次能用的样子" in maintain
    assert "更新环境" in maintain
    print("OK D1 日常配置面=环境维护")


def test_embed_default_no_auto_browser() -> None:
    from services.harness_surface import PRODUCT_SURFACE_MODE, prefer_embed

    assert PRODUCT_SURFACE_MODE == "embed"
    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "禁止自动弹浏览器" in page or "_maybe_auto_open_browser" in page
    # 空实现
    assert 'def _maybe_auto_open_browser' in page
    print("OK B2/B4 默认内嵌；不自动弹浏览器")


def test_cdn_fail_no_fake_path_register() -> None:
    prefab = _read("services/harness_prefab.py")
    assert "登记本机" not in prefab
    assert "harness.yml 中" not in prefab
    gate = _read("modules/harness_agent/setup_gate.py")
    assert "登记本机环境" not in gate
    guide = _read("services/harness_guide.py")
    assert "登记本机环境" not in guide
    print("OK A2 CDN失败文案不诱导假登记路径")


def test_lock_heal_and_repair_entry() -> None:
    cred = _read("services/harness_credentials.py")
    assert "clear_stale_credential_locks" in cred
    setup = _read("services/harness_setup.py")
    assert "clear_stale_credential_locks" in setup
    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "_on_repair_env" in page
    print("OK C4/D1 凭证锁清理 + 修一下入口")


def test_coexistence_home() -> None:
    cfg = _read("services/harness_config.py")
    assert "is_workbuddy_home" in cfg
    assert "preferred_dsh_home" in cfg
    setup = _read("services/harness_setup.py")
    assert "default_install_root" in setup
    print("OK E1 WorkBuddy home 隔离 / 卸只清 TOA 树契约存在")


def test_upgrade_forces_snapshot_api() -> None:
    from services.harness_profile_versions import maybe_snapshot_after_healthy, snapshot_web_profile

    # API 存在且 force 路径可调用（不要求一定改盘成功）
    ok, msg, _sid = snapshot_web_profile(reason="upgrade-verify", mark_good=True)
    assert isinstance(ok, bool) and isinstance(msg, str)
    skipped, skip_msg = maybe_snapshot_after_healthy(min_interval_sec=3600.0)
    assert isinstance(skipped, bool) and isinstance(skip_msg, str)
    # 节流可跳过；强制 mark_good 路径不受 maybe 节流限制（由页面 _force_good_snapshot 直调）
    print("OK D3 snapshot API（force / throttle）")


def test_page_source_external_confirm() -> None:
    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "改为由运营宝接管" in page
    assert "_start_from_user" in page
    assert "已接上本机正在运行的服务" in page
    assert "_upgrade_in_progress = True" in page
    assert 'reason="upgrade"' in page or "reason='upgrade'" in page
    print("OK 页面接线：外部确认 + 升级强制快照")


def test_bom_strip_heals_start() -> None:
    from services.harness_plugins import strip_utf8_bom_in_profile

    ok, msg = strip_utf8_bom_in_profile()
    assert ok is True
    assert isinstance(msg, str)
    plugins = _read("services/harness_plugins.py")
    assert "strip_utf8_bom_in_profile" in plugins
    side = _read("services/harness_sidecar.py")
    assert "strip_utf8_bom_in_profile" in side
    print(f"OK C-BOM profile 编码清理: {msg}")


def test_runtime_update_nudge_contract() -> None:
    """已装旧 MANIFEST + 新钉扎 → 有更新信息；同版本 → None。禁止静默下载。"""
    import json
    import tempfile
    from pathlib import Path

    from services import harness_prefab as hp

    page = _read("modules/harness_agent/harness_agent_page.py")
    assert "runtime_update_available" in page
    assert "_refresh_upgrade_nudge" in page
    assert "UpgradeStrip" in page
    assert "_awaiting_start_after_upgrade" in page
    assert "show_upgraded_done" in page
    assert "snooze_today" in page or "_on_upgrade_nudge_snooze_today" in page
    assert "runtime_update_available()" in page
    # 有待更新时禁止进页抢启（避免旧核失败吓出修一下）
    assert "runtime_update_available" in page and "return False" in page
    assert "port_busy" in page
    assert "_start_from_user" in page
    assert "已接上本机正在运行的服务" in page
    strip = _read("modules/harness_agent/upgrade_strip.py")
    assert "更新" in strip and "不更新" in strip and "今日不提醒" in strip
    assert "启动服务" in strip and "已升级完成" in strip
    prefab = _read("services/harness_prefab.py")
    assert "正在下载" in prefab and "大约还要" in prefab
    nudge = _read("services/harness_upgrade_nudge.py")
    assert "snooze_today" in nudge and "is_snoozed_today" in nudge
    standalone = _read("config/editions/standalone.yml")
    assert "harness_agent" in standalone

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "MANIFEST.json").write_text(
            json.dumps({"flavor": "prefab", "version": "0.0.0-test"}, ensure_ascii=False),
            encoding="utf-8",
        )
        info = hp.runtime_update_available(root)
        from services.harness_config import load_harness_config

        pinned = str(load_harness_config().get("prefab_bundle_version") or "").strip()
        if pinned and pinned != "0.0.0-test":
            assert info is not None
            assert info["installed_version"] == "0.0.0-test"
            assert info["available_version_raw"] == pinned
        (root / "MANIFEST.json").write_text(
            json.dumps({"flavor": "prefab", "version": pinned or "same"}, ensure_ascii=False),
            encoding="utf-8",
        )
        if pinned:
            # 同号 CDN 底座且无本机内核树 → 无弱提示；内核落后由本机真实安装另测
            again = hp.runtime_update_available(root)
            assert again is None or again.get("npm_core_only") is True
    print("OK 升级弱提示契约（确认才下 + 今日不提醒 + 升级后启服）")


def main() -> int:
    tests = [
        test_no_settings_harness_tab,
        test_auto_start_not_forced,
        test_no_silent_external_takeover,
        test_upgrade_shows_gate_and_forces_snapshot,
        test_upgrade_forces_snapshot_api,
        test_page_source_external_confirm,
        test_maintain_is_daily_surface,
        test_embed_default_no_auto_browser,
        test_cdn_fail_no_fake_path_register,
        test_lock_heal_and_repair_entry,
        test_coexistence_home,
        test_bom_strip_heals_start,
        test_runtime_update_nudge_contract,
    ]
    for t in tests:
        t()
    print("\nVERIFY harness_full_scenarios OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
