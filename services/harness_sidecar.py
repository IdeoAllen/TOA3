# -*- coding: utf-8 -*-
"""DeepSeek Harness (dsh) 本地 Sidecar 进程管理。"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any

from services.harness_config import (
    dsh_bin_path,
    dsh_home_path,
    load_harness_config,
    node_exe_path,
    web_url,
)

logger = logging.getLogger(__name__)

_PROCESS: subprocess.Popen | None = None
_OWNED: bool = False


def _cfg() -> dict[str, Any]:
    return load_harness_config()


def is_running() -> bool:
    url = web_url()
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            return resp.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def health_status() -> dict[str, Any]:
    running = is_running()
    cfg = _cfg()
    port = int(cfg.get("web_port") or 3081)
    port_busy = _port_open(port)
    external = running and not (_OWNED and _PROCESS is not None and _PROCESS.poll() is None)
    conflict = port_busy and not running
    return {
        "running": running,
        "owned": _OWNED and _PROCESS is not None and _PROCESS.poll() is None,
        "external": external,
        "port_busy": port_busy,
        "port_conflict": conflict,
        "url": web_url(),
        "port": port,
        "dsh_home": str(dsh_home_path()),
        "node_ok": node_exe_path().is_file(),
        "dsh_ok": dsh_bin_path().is_file(),
    }


def _port_open(port: int) -> bool:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def validate_setup() -> tuple[bool, str]:
    """进页前检查 Node/dsh/端口，返回 (可尝试启动, 提示)。"""
    node = node_exe_path()
    dsh = dsh_bin_path()
    if not node.is_file():
        return False, f"未找到 Node：{node}\n请在设置 → 能力接入 → Harness 配置路径。"
    if not dsh.is_file():
        return False, f"未找到 dsh：{dsh}\n请确认 @deepseek-ai/dsh 已安装。"
    port = int(_cfg().get("web_port") or 3081)
    if _port_open(port) and not is_running():
        return True, (
            f"端口 {port} 已被占用但 Harness 未响应。"
            "可能是 WorkBuddy 或其它进程；可改端口或直接嵌入已有实例。"
        )
    return True, ""


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    home = dsh_home_path()
    home.mkdir(parents=True, exist_ok=True)
    env["DSH_HOME"] = str(home)
    env["DSH_WEB_URL"] = web_url()
    if bool(_cfg().get("clear_env_api_key", True)):
        env.pop("DEEPSEEK_API_KEY", None)
    return env


def start(*, wait_ready: bool = True, timeout_sec: float = 25.0) -> tuple[bool, str]:
    """启动 dsh web；若端口已有实例则直接复用。"""
    global _PROCESS, _OWNED
    ok_setup, setup_hint = validate_setup()
    if not ok_setup:
        return False, setup_hint
    if is_running():
        hint = "Harness 已在运行（复用现有实例）"
        if setup_hint:
            hint = f"{hint}\n{setup_hint}"
        return True, hint

    node = node_exe_path()
    dsh = dsh_bin_path()
    if not node.is_file():
        return False, f"未找到 Node：{node}"
    if not dsh.is_file():
        return False, f"未找到 dsh：{dsh}"

    port = int(_cfg().get("web_port") or 3081)
    env = _build_env()
    args = [
        str(node),
        str(dsh),
        "--profile",
        "web",
        "--port",
        str(port),
    ]
    try:
        _PROCESS = subprocess.Popen(
            args,
            env=env,
            cwd=str(dsh.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        _OWNED = True
    except OSError as exc:
        logger.exception("启动 Harness 失败")
        return False, str(exc)

    if wait_ready:
        import time

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if _PROCESS.poll() is not None:
                return False, "Harness 进程已退出，请检查 Node/dsh 路径与 DSH_HOME"
            if is_running():
                return True, f"Harness 已启动：{web_url()}"
            time.sleep(0.35)
        return False, f"Harness 启动超时（{timeout_sec}s），请检查端口 {port}"

    return True, "Harness 进程已拉起"


def stop() -> tuple[bool, str]:
    """停止本模块拉起的 Sidecar；不杀外部已运行实例。"""
    global _PROCESS, _OWNED
    if _PROCESS is None or _PROCESS.poll() is not None:
        _PROCESS = None
        _OWNED = False
        if is_running():
            return True, "Harness 由外部进程托管，未停止"
        return True, "Harness 未运行"
    try:
        _PROCESS.terminate()
        _PROCESS.wait(timeout=8)
    except subprocess.TimeoutExpired:
        _PROCESS.kill()
    except OSError as exc:
        return False, str(exc)
    finally:
        _PROCESS = None
        _OWNED = False
    return True, "已停止 TOA3 拉起的 Harness"


def restart() -> tuple[bool, str]:
    stop()
    return start()


def stop_on_app_exit_if_configured() -> None:
    if not bool(_cfg().get("stop_on_app_exit", False)):
        return
    stop()


def open_config_dir() -> Path:
    p = dsh_home_path()
    p.mkdir(parents=True, exist_ok=True)
    return Path(p)
