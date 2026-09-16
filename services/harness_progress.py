# -*- coding: utf-8 -*-
"""Harness 用户可见进度文案（无编号、无第三方产品名）。

页面只展示「正在做什么 → 结果」；装/启/修引导用语统一从此处取。
"""
from __future__ import annotations

from enum import StrEnum


class Progress(StrEnum):
    """全周期进度（不对用户显示枚举名）。"""

    ENTER = "enter"
    CHECK_INSTALL = "check_install"
    CHECK_SERVICE = "check_service"
    NEED_INSTALL = "need_install"
    NEED_KEY = "need_key"
    NEED_START = "need_start"
    NEED_REPAIR = "need_repair"
    STOPPING = "stopping"
    STOPPED = "stopped"
    STARTING = "starting"
    STARTED = "started"
    RESTARTING = "restarting"
    LOADING_UI = "loading_ui"
    READY = "ready"
    READY_BROWSER = "ready_browser"
    FAILED = "failed"


# 标题栏短句（SectionTitle）
TITLE: dict[Progress, str] = {
    Progress.ENTER: "正在进入…",
    Progress.CHECK_INSTALL: "正在检查安装…",
    Progress.CHECK_SERVICE: "正在检查服务…",
    Progress.NEED_INSTALL: "DeepSeek Harness",
    Progress.NEED_KEY: "DeepSeek Harness",
    Progress.NEED_START: "DeepSeek Harness",
    Progress.NEED_REPAIR: "DeepSeek Harness",
    Progress.STOPPING: "正在停止…",
    Progress.STOPPED: "服务已停止",
    Progress.STARTING: "正在启动…",
    Progress.STARTED: "服务已启动",
    Progress.RESTARTING: "正在重新启动…",
    Progress.LOADING_UI: "正在装载界面…",
    Progress.READY: "DeepSeek Harness",
    Progress.READY_BROWSER: "DeepSeek Harness",
    Progress.FAILED: "DeepSeek Harness",
}

# 状态行（一眼知道在干什么 / 结果）
HINT: dict[Progress, str] = {
    Progress.ENTER: "状态：正在进入页面…",
    Progress.CHECK_INSTALL: "状态：正在检查安装状态…",
    Progress.CHECK_SERVICE: "状态：正在检查启动状态…",
    Progress.NEED_INSTALL: "状态：未安装 · 请点「一键安装」",
    Progress.NEED_KEY: "状态：待配置 API Key",
    Progress.NEED_START: "状态：服务未启动 · 请点「启动服务」",
    Progress.NEED_REPAIR: "状态：环境异常 · 请点「修一下」或「更多 → 环境维护」",
    Progress.STOPPING: "状态：正在停止服务…",
    Progress.STOPPED: "状态：服务已停止",
    Progress.STARTING: "状态：正在启动服务…",
    Progress.STARTED: "状态：服务已启动",
    Progress.RESTARTING: "状态：正在重新启动…",
    Progress.LOADING_UI: "状态：正在装载 DeepSeek Harness 界面…",
    Progress.READY: "状态：服务已启动",
    Progress.READY_BROWSER: "状态：服务已启动 · 请点「在浏览器打开」",
    Progress.FAILED: "状态：启动未成功 · 请再点「启动服务」",
}

# 主区占位（与状态行同口径，避免 Sidecar/第三方名）
IDLE: dict[Progress, str] = {
    Progress.ENTER: "正在进入…",
    Progress.CHECK_INSTALL: "正在检查安装状态…",
    Progress.CHECK_SERVICE: "正在检查启动状态…",
    Progress.NEED_INSTALL: "尚未安装运行环境\n请点上方「一键安装」",
    Progress.NEED_KEY: "请填写 DeepSeek API Key 后启动",
    Progress.NEED_START: "服务未启动\n请点「启动服务」",
    Progress.NEED_REPAIR: "运行环境异常\n请点「修一下」",
    Progress.STOPPING: "正在停止服务…",
    Progress.STOPPED: "服务已停止\n需要时再点「启动服务」",
    Progress.STARTING: "正在启动服务…",
    Progress.STARTED: "服务已启动",
    Progress.RESTARTING: "正在重新启动…",
    Progress.LOADING_UI: "正在装载 DeepSeek Harness 界面…",
    Progress.READY: "服务已启动",
    Progress.READY_BROWSER: "服务已启动\n请点「在浏览器打开」（浏览器打开效果更佳）",
    Progress.FAILED: "启动未成功\n请再点「启动服务」；有新版本时可先更新",
}

# 底栏/通知短句
TOAST: dict[Progress, str] = {
    Progress.ENTER: "正在进入编码智能体…",
    Progress.CHECK_INSTALL: "正在检查安装状态…",
    Progress.CHECK_SERVICE: "正在检查启动状态…",
    Progress.NEED_INSTALL: "请先一键安装",
    Progress.NEED_KEY: "请先配置 API Key",
    Progress.NEED_START: "请点「启动服务」",
    Progress.NEED_REPAIR: "环境异常，可点「修一下」",
    Progress.STOPPING: "正在停止服务…",
    Progress.STOPPED: "服务已停止",
    Progress.STARTING: "正在启动服务…",
    Progress.STARTED: "服务已启动",
    Progress.RESTARTING: "正在重新启动…",
    Progress.LOADING_UI: "正在装载 DeepSeek Harness 界面…",
    Progress.READY: "服务已启动",
    Progress.READY_BROWSER: "请点「在浏览器打开」",
    Progress.FAILED: "启动未成功，请再点「启动服务」",
}


def sanitize_user_text(text: str) -> str:
    """去掉与用户无关的第三方/内部词，避免干扰。"""
    t = str(text or "")
    repl = (
        ("WorkBuddy", "其它程序"),
        ("workbuddy", "其它程序"),
        ("Sidecar", "服务"),
        ("sidecar", "服务"),
        ("外部实例", "本机其它进程"),
        ("外部 Harness", "本机其它 Harness 进程"),
        ("DSH_HOME", "数据目录"),
    )
    for a, b in repl:
        t = t.replace(a, b)
    return t


def clip_user_detail(text: str, *, max_len: int = 96) -> str:
    """状态行/主区用的短因：去掉堆栈与 node_modules 路径，禁止整段日志刷屏。"""
    t = sanitize_user_text(text).strip()
    if not t:
        return ""
    # 已知短因：凭证顶层脏键
    if "unknown top-level key" in t.lower() or "EVOLINK_API_KEY" in t:
        return "凭证文件格式异常（已可自动整理）"
    if "plugin tree failed" in t.lower() or "failed to load plugins" in t.lower():
        return "插件/凭证加载失败，请点「修一下」后重试"
    kept: list[str] = []
    for raw in t.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if s.startswith("at ") or s.startswith("File "):
            break
        if "node_modules" in low or "\\node_modules\\" in low:
            continue
        if ".js:" in s and ("\\" in s or "/" in s):
            continue
        if "error:" in low and ("c:\\" in low or "/users/" in low):
            if ":" in s:
                s = s.split(":")[-1].strip() or s
        kept.append(s)
        if len(kept) >= 2:
            break
    out = " · ".join(kept) if kept else t.splitlines()[0].strip()
    out = " ".join(out.split())
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out
