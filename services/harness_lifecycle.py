# -*- coding: utf-8 -*-
"""Harness 安装就绪检测（不含 Harness 业务替代）。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.harness_config import dsh_bin_path, dsh_home_path, node_exe_path
from services.harness_credentials import has_api_key
from services.harness_sidecar import is_running
from services.storage_paths import module_data_dir


@dataclass
class SetupStep:
    id: str
    title: str
    done: bool
    hint: str


def _marker_path() -> Path:
    return module_data_dir("harness_agent", create=True) / "setup_complete.json"


def mark_setup_complete() -> None:
    p = _marker_path()
    p.write_text(json.dumps({"complete": True}, ensure_ascii=False), encoding="utf-8")


def is_setup_marked_complete() -> bool:
    p = _marker_path()
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return bool(data.get("complete"))
    except (json.JSONDecodeError, OSError):
        return False


def evaluate_setup() -> dict[str, Any]:
    from services.harness_guide import STEP_HINTS

    node_ok = node_exe_path().is_file()
    dsh_ok = dsh_bin_path().is_file()
    home_ok = dsh_home_path().is_dir()
    key_ok = has_api_key()
    running = is_running()

    steps = [
        SetupStep("runtime", "① Node + dsh 就绪", node_ok and dsh_ok, STEP_HINTS["runtime"]),
        SetupStep("credentials", "② API Key 已配置", key_ok, STEP_HINTS["credentials"]),
        SetupStep("start", "③ Harness 已启动", running, STEP_HINTS["start"]),
    ]
    core_done = node_ok and dsh_ok and key_ok and home_ok
    return {
        "steps": steps,
        "core_ready": core_done,
        "ready_chat": core_done and running,
        "node_ok": node_ok,
        "dsh_ok": dsh_ok,
        "home_ok": home_ok,
        "key_ok": key_ok,
        "running": running,
    }
