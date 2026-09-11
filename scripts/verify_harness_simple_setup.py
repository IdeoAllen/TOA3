#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码智能体四步开用：文案 / 双路线 / 引导控件契约。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.harness_guide import GUIDE_INTRO, NODE_DOWNLOAD_URL, STEP_HINTS
    from services.harness_prefab import (
        FLAVOR_OFFICIAL,
        FLAVOR_PREFAB,
        FLAVORS,
        bundle_spec,
        normalize_flavor,
    )
    from services.harness_setup import NEED_NODE_PREFIX

    assert "四步" in GUIDE_INTRO or "①" in GUIDE_INTRO
    assert "nodejs.org" in NODE_DOWNLOAD_URL
    for key in ("runtime", "runtime_need_node", "credentials", "start"):
        assert key in STEP_HINTS and STEP_HINTS[key].strip()
    assert "WorkBuddy" not in STEP_HINTS["runtime"]
    assert "WorkBuddy" not in STEP_HINTS["runtime_need_node"]
    assert "官方" in STEP_HINTS["runtime"] or "预制" in STEP_HINTS["runtime"]

    msg = (
        f"{NEED_NODE_PREFIX}"
        "本机未找到运行环境。请选择「安装官方版」或「安装预制版」下载预制包。"
    )
    assert msg.startswith(NEED_NODE_PREFIX)

    assert normalize_flavor("official") == FLAVOR_OFFICIAL
    assert normalize_flavor("prefab") == FLAVOR_PREFAB
    assert set(FLAVORS) == {FLAVOR_OFFICIAL, FLAVOR_PREFAB}
    for f in FLAVORS:
        spec = bundle_spec(f)
        assert "url" in spec and "sha256" in spec

    gate_src = (ROOT / "modules" / "harness_agent" / "setup_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(gate_src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for need in (
        "show_state",
        "set_installing",
        "set_install_progress",
        "show_install_failed",
        "mark_need_node",
        "_open_node_download",
        "_save_key",
    ):
        assert need in names, need
    assert "选择版本" in gate_src
    assert "填写密钥" in gate_src
    assert "安装官方版" in gate_src
    assert "安装预制版" in gate_src
    assert "保存并启动" in gate_src
    assert "install_requested = Signal(str)" in gate_src

    page_src = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(
        encoding="utf-8"
    )
    assert "_HarnessInstallWorker" in page_src
    assert "_on_cancel_install" in page_src
    assert "set_install_progress" in page_src
    assert "_auto_start_tried = False" in page_src

    setup_src = (ROOT / "services" / "harness_setup.py").read_text(encoding="utf-8")
    assert "flavor" in setup_src
    assert "install_prefab_bundle" in setup_src

    cfg = (ROOT / "config" / "harness.yml").read_text(encoding="utf-8")
    for key in (
        "official_bundle_url",
        "prefab_bundle_url",
        "prefab_essential_plugins",
        "official_sha256",
        "prefab_sha256",
    ):
        assert key in cfg, key

    build_script = ROOT / "scripts" / "build_harness_prefab.py"
    assert build_script.is_file()

    print("VERIFY harness_simple_setup OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
