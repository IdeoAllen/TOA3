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
    chunk = text[idx : idx + 600]
    assert "stop(force=False)" not in chunk
    assert "_takeover_restart_on_main" in chunk


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
    print("VERIFY harness_clean_restart OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
