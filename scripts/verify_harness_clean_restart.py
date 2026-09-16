#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness 干净重启契约：restart() 必须强杀路径，禁止软复用。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _assert_restart_is_clean() -> None:
    path = ROOT / "services" / "harness_sidecar.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    restart_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "restart":
            restart_fn = node
            break
    assert restart_fn is not None, "restart() missing"
    # 函数体只能调用 ensure_owned_with_credentials（干净重启）
    calls = [
        n
        for n in ast.walk(restart_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    names = {c.func.id for c in calls}
    assert "ensure_owned_with_credentials" in names, names
    assert "start" not in names, "restart must not soft-call start()"
    # 源码级：不得再出现 stop(force=False) 再 start 的旧模式
    body_src = ast.get_source_segment(src, restart_fn) or ""
    assert "stop(force=False)" not in body_src
    assert "return start()" not in body_src.replace(" ", "")


def _assert_page_restart_forces() -> None:
    path = ROOT / "modules" / "harness_agent" / "harness_agent_page.py"
    text = path.read_text(encoding="utf-8")
    assert "_takeover_restart_on_main" in text
    # _on_restart 不得再 stop(force=False)+_run_sidecar_start
    idx = text.find("def _on_restart")
    assert idx > 0
    chunk = text[idx : idx + 900]
    assert "stop(force=False)" not in chunk
    assert "_takeover_restart_on_main" in chunk
    assert "_user_stopped" in text
    assert "open_browser: bool = False" in text


def _assert_app_restart_kills_siblings() -> None:
    path = ROOT / "services" / "app_lifecycle.py"
    text = path.read_text(encoding="utf-8")
    assert "_kill_sibling_app_instances" in text
    idx = text.find("def restart_process")
    assert idx > 0
    chunk = text[idx : idx + 900]
    assert "_kill_sibling_app_instances" in chunk
    assert "startDetached" in chunk


def main() -> int:
    _assert_restart_is_clean()
    _assert_page_restart_forces()
    _assert_app_restart_kills_siblings()
    # 运行时：restart 符号指向干净实现
    from services import harness_sidecar as hs

    assert hs.restart.__doc__ and "强杀" in hs.restart.__doc__
    assert callable(hs.preflight_web_profile)
    src = (ROOT / "services" / "harness_sidecar.py").read_text(encoding="utf-8")
    assert "preflight_web_profile" in src
    assert "strip_boot_killer_plugins" in src
    page = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(encoding="utf-8")
    assert "卸载…" in page
    assert "打开…" in page
    assert "修一下" in page or "环境维护" in page
    assert "_maybe_auto_heal_plugins" in page
    # 主栏保留启停 + 浏览器 + 刷新 + 更多
    assert 'SecondaryButton("刷新")' in page
    assert "_begin_click_feedback" in page
    assert "_action_progress" in page
    assert "再次打开浏览器" not in page
    # launch-token：导航不得把 ?token= 末尾拼成 token…/
    assert "normalize_nav_url" in page
    from services.shared_local_webengine import normalize_nav_url

    bare = "http://127.0.0.1:3082"
    tok = "http://127.0.0.1:3082/?token=abcDEF"
    assert normalize_nav_url(bare) == "http://127.0.0.1:3082/"
    assert normalize_nav_url(tok) == tok
    shared = (ROOT / "services" / "shared_local_webengine.py").read_text(encoding="utf-8")
    assert "normalize_nav_url" in shared
    assert 'url.rstrip("/") + "/"' not in shared
    cfg = (ROOT / "services" / "harness_config.py").read_text(encoding="utf-8")
    assert "_capture_auth_url_from_log" in cfg
    side = (ROOT / "services" / "harness_sidecar.py").read_text(encoding="utf-8")
    assert side.count("_capture_auth_url_from_log()") >= 2
    print("VERIFY harness_clean_restart OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
