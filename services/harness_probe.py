# -*- coding: utf-8 -*-
"""编码智能体页状态探测（进页自动检查）。"""
from __future__ import annotations

from enum import StrEnum

from services.harness_config import dsh_bin_path, dsh_home_path, node_exe_path
from services.harness_credentials import has_api_key
from services.harness_sidecar import is_running


class HarnessPageState(StrEnum):
    CHECKING = "checking"
    NOT_INSTALLED = "not_installed"
    NEEDS_KEY = "needs_key"
    STOPPED = "stopped"
    RUNNING = "running"


def is_runtime_installed() -> bool:
    return node_exe_path().is_file() and dsh_bin_path().is_file() and dsh_home_path().is_dir()


def probe_page_state() -> tuple[HarnessPageState, str]:
    if not node_exe_path().is_file() or not dsh_bin_path().is_file():
        return HarnessPageState.NOT_INSTALLED, "未检测到 DeepSeek Harness 运行组件"
    if not dsh_home_path().is_dir():
        return HarnessPageState.NOT_INSTALLED, "Harness 数据目录未初始化"
    if not has_api_key():
        return HarnessPageState.NEEDS_KEY, "请配置 DeepSeek API Key"
    if is_running():
        return HarnessPageState.RUNNING, "Harness 服务运行中"
    return HarnessPageState.STOPPED, "Harness 已安装，服务未启动"
