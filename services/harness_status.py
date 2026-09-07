# -*- coding: utf-8 -*-
"""DeepSeek Harness 安装与服务状态 — 页面/设置唯一真相源。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from services.harness_config import dsh_bin_path, dsh_home_path, load_harness_config, node_exe_path, web_url
from services.harness_credentials import has_api_key
from services.harness_sidecar import _port_open, sidecar_local_snapshot


class InstallState(StrEnum):
    NOT_INSTALLED = "not_installed"
    NEEDS_KEY = "needs_key"
    READY = "ready"


class ServiceState(StrEnum):
    STOPPED = "stopped"
    RUNNING_OWNED = "running_owned"
    RUNNING_EXTERNAL = "running_external"
    PORT_CONFLICT = "port_conflict"


@dataclass(frozen=True)
class HarnessStatus:
    install: InstallState
    service: ServiceState
    summary: str
    detail: str
    url: str
    port: int
    node_ok: bool
    dsh_ok: bool
    home_ok: bool
    has_key: bool
    owned: bool
    http_ok: bool
    port_busy: bool

    @property
    def running(self) -> bool:
        return self.service in (
            ServiceState.RUNNING_OWNED,
            ServiceState.RUNNING_EXTERNAL,
        )

    @property
    def install_label(self) -> str:
        if self.install == InstallState.NOT_INSTALLED:
            return "未安装"
        if self.install == InstallState.NEEDS_KEY:
            return "待配置 API Key"
        return "已安装"

    @property
    def service_label(self) -> str:
        labels = {
            ServiceState.STOPPED: "未启动",
            ServiceState.RUNNING_OWNED: "运行中 · TOA 托管",
            ServiceState.RUNNING_EXTERNAL: "运行中 · 外部实例",
            ServiceState.PORT_CONFLICT: "端口占用但未响应",
        }
        return labels.get(self.service, "未知")


def _read_install() -> tuple[InstallState, bool, bool, bool, bool]:
    node = node_exe_path()
    dsh = dsh_bin_path()
    try:
        node_ok = node.is_file()
    except OSError:
        node_ok = False
    try:
        dsh_ok = dsh.is_file()
    except OSError:
        dsh_ok = False
    try:
        home_ok = dsh_home_path().is_dir()
    except OSError:
        home_ok = False
    if not node_ok or not dsh_ok or not home_ok:
        return InstallState.NOT_INSTALLED, node_ok, dsh_ok, home_ok, False
    if not has_api_key():
        return InstallState.NEEDS_KEY, node_ok, dsh_ok, home_ok, False
    return InstallState.READY, node_ok, dsh_ok, home_ok, True


def _probe_http(*, timeout: float) -> bool:
    from services.harness_sidecar import is_running

    return is_running(timeout=timeout)


def read_harness_status(*, probe_http: bool = True, http_timeout: float = 0.8) -> HarnessStatus:
    """读取安装 + 启停状态。

    probe_http=False：仅本机路径/端口探测，不发起 HTTP（进页首帧，不卡 UI）。
    probe_http=True：再请求 Sidecar URL，得到准确运行态。
    """
    install, node_ok, dsh_ok, home_ok, key_ok = _read_install()
    cfg = load_harness_config()
    from services.harness_config import PRODUCT_WEB_PORT

    port = int(cfg.get("web_port") or PRODUCT_WEB_PORT)
    url = web_url()
    port_busy = _port_open(port)
    http_ok = _probe_http(timeout=http_timeout) if probe_http else False
    snap = sidecar_local_snapshot(http_ok=http_ok if probe_http else None)
    owned = bool(snap.get("owned"))

    if install != InstallState.READY:
        if install == InstallState.NOT_INSTALLED:
            summary = "未安装"
            if not node_ok:
                detail = "还差运行环境：点页内「① 一键安装」。若提示缺 Node，先装官方 LTS 再重试。"
            else:
                detail = "点页内「① 一键安装」完成环境准备（独立目录，无需手填路径）。"
        else:
            summary = "待 API Key"
            detail = "环境已就绪：粘贴 DeepSeek API Key 后点「保存并启动」。"
        return HarnessStatus(
            install=install,
            service=ServiceState.STOPPED,
            summary=f"{summary} · 服务未启动",
            detail=detail,
            url=url,
            port=port,
            node_ok=node_ok,
            dsh_ok=dsh_ok,
            home_ok=home_ok,
            has_key=key_ok,
            owned=False,
            http_ok=False,
            port_busy=port_busy,
        )

    if not probe_http:
        if port_busy:
            summary = "已安装 · 端口已占用"
            detail = f"端口 {port} 已占用，正在确认 Sidecar 是否响应…"
        else:
            summary = "已安装 · 服务未启动"
            detail = "点「启动服务」由 TOA 拉起 Sidecar，或「在浏览器打开」使用已有实例。"
        return HarnessStatus(
            install=install,
            service=ServiceState.STOPPED,
            summary=summary,
            detail=detail,
            url=url,
            port=port,
            node_ok=node_ok,
            dsh_ok=dsh_ok,
            home_ok=home_ok,
            has_key=key_ok,
            owned=owned,
            http_ok=False,
            port_busy=port_busy,
        )

    if http_ok and owned:
        service = ServiceState.RUNNING_OWNED
        summary = "已安装 · TOA 托管运行中"
        detail = f"Sidecar 正常响应：{url}"
    elif http_ok and not owned:
        service = ServiceState.RUNNING_EXTERNAL
        summary = "已安装 · 外部实例运行中"
        detail = (
            "端口上已有其它 Harness 实例。"
            "要用本页密钥稳定干活，请点「更多 → 重启服务」（由 TOA 托管并注入密钥）。"
        )
    elif port_busy and not http_ok:
        service = ServiceState.PORT_CONFLICT
        summary = "已安装 · 端口占用"
        detail = f"端口 {port} 被占用但 Harness 未响应 HTTP，请改端口或结束占用进程。"
    else:
        service = ServiceState.STOPPED
        summary = "已安装 · 服务未启动"
        detail = "点「启动服务」由 TOA 拉起 Sidecar，或「在浏览器打开」使用已有实例。"

    try:
        from services.harness_credentials import diagnose_llm_access

        # 外部实例：文案已提示接管，勿再叠「Key 冲突」（父进程脏 env 易误报）
        if service == ServiceState.RUNNING_EXTERNAL:
            pass
        elif service == ServiceState.STOPPED:
            key_ok, key_msg = diagnose_llm_access(sidecar_owned=True)
            if not key_ok:
                detail = f"{detail}\n⚠ {key_msg}"
        else:
            key_ok, key_msg = diagnose_llm_access(sidecar_owned=bool(http_ok and owned))
            if not key_ok:
                detail = f"{detail}\n⚠ {key_msg}"
    except Exception:
        pass

    return HarnessStatus(
        install=install,
        service=service,
        summary=summary,
        detail=detail,
        url=url,
        port=port,
        node_ok=node_ok,
        dsh_ok=dsh_ok,
        home_ok=home_ok,
        has_key=key_ok,
        owned=owned if service == ServiceState.RUNNING_OWNED else bool(snap.get("owned")),
        http_ok=http_ok,
        port_busy=port_busy,
    )
