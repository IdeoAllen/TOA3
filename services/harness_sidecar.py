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
_LAST_START_LOG: Path | None = None


def _sidecar_log_path() -> Path:
    from services.storage_paths import module_output_dir

    p = module_output_dir("harness_agent") / "sidecar_last.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_log_tail(path: Path, limit: int = 600) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return text[-limit:] if len(text) > limit else text


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
        hint = "Harness 已在运行"
        st = health_status()
        if st.get("owned"):
            hint += "（TOA 托管）"
        else:
            hint += "（外部实例，停止服务可结束或「接管并重启」）"
        if setup_hint:
            hint = f"{hint}\n{setup_hint}"
        return True, hint

    node = node_exe_path()
    dsh = dsh_bin_path()
    if not node.is_file():
        return False, f"未找到 Node：{node}"
    if not dsh.is_file():
        return False, f"未找到 dsh：{dsh}"

    from services.harness_plugins import ensure_web_profile_bundles

    home = dsh_home_path()
    ok_prof, prof_msg = ensure_web_profile_bundles(node, dsh, home)
    if not ok_prof:
        return False, f"Web 组件未就绪：{prof_msg}\n请点「更多 → 修复运行环境」。"

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
    log_path = _sidecar_log_path()
    global _LAST_START_LOG
    _LAST_START_LOG = log_path
    try:
        log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    except OSError:
        log_f = subprocess.DEVNULL
    try:
        _PROCESS = subprocess.Popen(
            args,
            env=env,
            cwd=str(dsh.parent),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        _OWNED = True
    except OSError as exc:
        logger.exception("启动 Harness 失败")
        return False, str(exc)
    finally:
        if log_f is not subprocess.DEVNULL:
            try:
                log_f.close()
            except OSError:
                pass

    if wait_ready:
        import time

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if _PROCESS.poll() is not None:
                tail = _read_log_tail(log_path)
                hint = f"\n\n日志：{log_path}"
                if tail:
                    hint = f"\n\n{tail}"
                return False, (
                    "Harness 进程已退出。常见原因：API Key 未配置、"
                    "Node/dsh 路径错误或 Web 组件未装全。"
                    "请点「更多 → 修复运行环境」后重试。"
                    f"{hint}"
                )
            if is_running():
                return True, f"Harness 已启动：{web_url()}"
            time.sleep(0.35)
        tail = _read_log_tail(log_path)
        extra = f"\n{tail}" if tail else ""
        return False, f"Harness 启动超时（{timeout_sec}s），请检查端口 {port}{extra}"

    return True, "Harness 进程已拉起"


def _find_listener_pids(port: int) -> list[int]:
    """查找监听 127.0.0.1:port 的进程（Windows netstat）。"""
    if os.name != "nt":
        return []
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            errors="replace",
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    pids: list[int] = []
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid > 0 and pid not in pids:
            pids.append(pid)
    return pids


def _kill_pids(pids: list[int]) -> list[int]:
    killed: list[int] = []
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=12,
            )
            killed.append(pid)
        except (subprocess.TimeoutExpired, OSError):
            continue
    return killed


def stop(*, force: bool = False) -> tuple[bool, str]:
    """停止 Sidecar；force=True 时结束占用 Web 端口的外部进程。"""
    global _PROCESS, _OWNED
    if _PROCESS is not None and _PROCESS.poll() is None:
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
        if is_running():
            if force:
                port = int(_cfg().get("web_port") or 3081)
                killed = _kill_pids(_find_listener_pids(port))
                if is_running():
                    return False, "进程已结束但端口仍被占用，请改 Web 端口或手动结束占用进程。"
                return True, f"已停止 Harness（并结束端口进程 {len(killed)} 个）"
            return False, "TOA 进程已结束，但端口上仍有 Harness 在运行。"
        return True, "已停止 Harness 服务"

    _PROCESS = None
    _OWNED = False
    if not is_running():
        return True, "Harness 未运行"

    if not force:
        return (
            False,
            "当前为外部实例（如 WorkBuddy 或其它 TOA 会话拉起）。"
            "点「停止服务」并在确认框中同意即可结束。",
        )

    port = int(_cfg().get("web_port") or 3081)
    killed = _kill_pids(_find_listener_pids(port))
    if is_running():
        return False, "未能结束占用端口的进程，请在任务管理器中结束 node.exe 或改 Web 端口。"
    detail = f"（已结束 {len(killed)} 个进程）" if killed else ""
    return True, f"已停止本机 Harness 服务{detail}"


def restart_owned() -> tuple[bool, str]:
    """强制结束端口占用后由 TOA 重新拉起（获得托管）。"""
    ok, msg = stop(force=True)
    if not ok and is_running():
        return False, msg
    return start()


def restart() -> tuple[bool, str]:
    st = health_status()
    if st.get("running") and not st.get("owned"):
        return restart_owned()
    stop(force=False)
    return start()


def stop_on_app_exit_if_configured() -> None:
    if not bool(_cfg().get("stop_on_app_exit", False)):
        return
    stop(force=True)


def open_config_dir() -> Path:
    p = dsh_home_path()
    p.mkdir(parents=True, exist_ok=True)
    return Path(p)
