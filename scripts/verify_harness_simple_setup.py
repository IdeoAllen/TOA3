#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码智能体小白三步：文案/缺 Node 前缀/引导控件契约。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.harness_guide import GUIDE_INTRO, NODE_DOWNLOAD_URL, STEP_HINTS
    from services.harness_setup import NEED_NODE_PREFIX

    assert "三步" in GUIDE_INTRO or "①" in GUIDE_INTRO
    assert "nodejs.org" in NODE_DOWNLOAD_URL
    for key in ("runtime", "runtime_need_node", "credentials", "start"):
        assert key in STEP_HINTS and STEP_HINTS[key].strip()
    # 小白主路径不再推销第三方 Harness 宿主
    assert "WorkBuddy" not in STEP_HINTS["runtime"]
    assert "WorkBuddy" not in STEP_HINTS["runtime_need_node"]

    msg = (
        f"{NEED_NODE_PREFIX}"
        "本机未找到 Node.js。请先安装官方 LTS（18+），装完后点「装好后点这里重试」。"
    )
    assert msg.startswith(NEED_NODE_PREFIX)

    gate_src = (ROOT / "modules" / "harness_agent" / "setup_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(gate_src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for need in ("show_state", "set_installing", "mark_need_node", "_open_node_download", "_save_key"):
        assert need in names, need
    assert "安装环境" in gate_src
    assert "填写密钥" in gate_src
    assert "启动使用" in gate_src
    assert "去安装 Node.js" in gate_src
    assert "保存并启动" in gate_src

    page_src = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(
        encoding="utf-8"
    )
    assert "mark_need_node" in page_src
    assert "_auto_start_tried = False" in page_src

    print("VERIFY harness_simple_setup OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
