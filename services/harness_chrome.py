# -*- coding: utf-8 -*-
"""Harness 工具栏 Chrome 状态机（纯函数）。

把「安装/运行/忙碌阶段」切成互斥视图，供页面与压测共用，避免启停钮与文案打架。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BusyPhase(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    STOPPING = "stopping"
    RESTARTING = "restarting"
    REPAIRING = "repairing"
    RESTORING = "restoring"
    UNINSTALLING = "uninstalling"
    HEALING = "healing"  # 剔插件 / 修密钥
    OTHER = "other"


# 人话进度（状态行 / 标题）
_PHASE_LABEL: dict[BusyPhase, str] = {
    BusyPhase.STARTING: "正在启动…",
    BusyPhase.STOPPING: "正在停止…",
    BusyPhase.RESTARTING: "正在重启…",
    BusyPhase.REPAIRING: "正在修复…",
    BusyPhase.RESTORING: "正在恢复配置…",
    BusyPhase.UNINSTALLING: "正在卸载…",
    BusyPhase.HEALING: "正在自愈…",
    BusyPhase.OTHER: "处理中…",
}


@dataclass(frozen=True)
class ChromeView:
    """工具栏一帧应呈现的状态。"""

    stack_index: int  # 0=启动钮 1=停止钮
    start_enabled: bool
    stop_enabled: bool
    open_browser_enabled: bool
    more_enabled: bool
    title: str
    status_hint: str
    tip_start: str
    tip_stop: str
    tip_browser: str
    tip_more: str
    busy: bool
    phase: BusyPhase


def infer_busy_phase(label: str) -> BusyPhase:
    """从忙碌文案推断阶段（兼容旧调用点）。"""
    t = (label or "").strip()
    if not t:
        return BusyPhase.IDLE
    if "卸载" in t:
        return BusyPhase.UNINSTALLING
    if "恢复" in t:
        return BusyPhase.RESTORING
    if "修一下" in t or "修复环境" in t or "修复…" in t or t.startswith("正在修复"):
        return BusyPhase.REPAIRING
    if "剔除" in t or "自愈" in t or "密钥" in t:
        return BusyPhase.HEALING
    if "重启" in t or "释放端口" in t:
        return BusyPhase.RESTARTING
    if "停止" in t:
        return BusyPhase.STOPPING
    if "启动" in t or "Sidecar" in t:
        return BusyPhase.STARTING
    return BusyPhase.OTHER


def compute_chrome(
    *,
    install_ready: bool,
    running: bool,
    phase: BusyPhase = BusyPhase.IDLE,
    busy_label: str = "",
    install_label: str = "",
    service_label: str = "",
    detail_warn: bool = False,
) -> ChromeView:
    """计算启停栈、按钮可用性、一行状态文案。"""
    busy = phase != BusyPhase.IDLE
    label = (busy_label or "").strip() or _PHASE_LABEL.get(phase, "处理中…")

    if busy:
        # 启停外观与阶段对齐：启动中见「启动」；停止中见「停止」；重启/修复见「启动」侧（往运行去）
        if phase == BusyPhase.STOPPING:
            stack = 1
        elif phase in (
            BusyPhase.STARTING,
            BusyPhase.RESTARTING,
            BusyPhase.REPAIRING,
            BusyPhase.RESTORING,
            BusyPhase.HEALING,
            BusyPhase.UNINSTALLING,
        ):
            stack = 0
        else:
            stack = 1 if running else 0
        tip = f"正在执行：{label}（完成后可操作）"
        return ChromeView(
            stack_index=stack,
            start_enabled=False,
            stop_enabled=False,
            open_browser_enabled=False,
            more_enabled=False,
            title=label,
            status_hint=f"状态：{label}",
            tip_start=tip,
            tip_stop=tip,
            tip_browser=tip,
            tip_more=tip,
            busy=True,
            phase=phase,
        )

    # —— 空闲 ——
    stack = 1 if running else 0
    start_ok = (not running) and install_ready
    stop_ok = running
    browser_ok = install_ready and running

    parts: list[str] = []
    if install_label:
        parts.append(f"安装 {install_label}")
    svc = service_label or ("运行中" if running else "未启动")
    if detail_warn:
        svc = f"{svc} · 需检查 API Key"
    parts.append(f"服务 {svc}")
    hint = " · ".join(parts)

    return ChromeView(
        stack_index=stack,
        start_enabled=start_ok,
        stop_enabled=stop_ok,
        open_browser_enabled=browser_ok,
        more_enabled=True,
        title="DeepSeek Harness",
        status_hint=hint,
        tip_start="启动 DeepSeek Harness 服务" if start_ok else (
            "请先完成安装与 API Key" if not install_ready else "服务已在运行"
        ),
        tip_stop="停止 Harness 服务",
        tip_browser=(
            "另开系统浏览器（同一服务）。侧栏预览等能力浏览器打开效果更佳"
            if browser_ok
            else "请先启动服务"
        ),
        tip_more="环境维护 · 重新启动 · 打开目录 · 卸载",
        busy=False,
        phase=BusyPhase.IDLE,
    )
