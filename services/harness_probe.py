# -*- coding: utf-8 -*-
"""编码智能体页状态探测（进页自动检查）。"""
from __future__ import annotations

from enum import StrEnum

from services.harness_config import dsh_bin_path, dsh_home_path, node_exe_path
from services.harness_status import InstallState, ServiceState, read_harness_status


class HarnessPageState(StrEnum):
    CHECKING = "checking"
    NOT_INSTALLED = "not_installed"
    NEEDS_KEY = "needs_key"
    STOPPED = "stopped"
    RUNNING = "running"


def is_runtime_installed() -> bool:
    return node_exe_path().is_file() and dsh_bin_path().is_file() and dsh_home_path().is_dir()


def probe_page_state(*, check_running: bool = True, running_timeout: float = 0.8) -> tuple[HarnessPageState, str]:
    st = read_harness_status(
        probe_http=check_running,
        http_timeout=running_timeout,
    )
    if st.install == InstallState.NOT_INSTALLED:
        return HarnessPageState.NOT_INSTALLED, st.detail
    if st.install == InstallState.NEEDS_KEY:
        return HarnessPageState.NEEDS_KEY, st.detail
    if st.service in (ServiceState.RUNNING_OWNED, ServiceState.RUNNING_EXTERNAL):
        return HarnessPageState.RUNNING, st.detail
    if st.service == ServiceState.PORT_CONFLICT:
        return HarnessPageState.STOPPED, st.detail
    return HarnessPageState.STOPPED, st.detail
