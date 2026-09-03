# -*- coding: utf-8 -*-
"""DeepSeek Harness (dsh) 本地 Sidecar 进程管理。"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
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
_LOCK = threading.Lock()


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


def is_running(*, timeout: float = 1.5) -> bool:
    url = web_url()
    try:
        with urllib.request.urlopen(url, timeout=max(0.3, float(timeout))) as resp:
            return resp.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def sidecar_local_snapshot(*, http_ok: bool | None = None) -> dict[str, Any]:
    """本进程 Sidecar 快照。http_ok 由调用方传入时可计算 external。"""
    cfg = _cfg()
    port = int(cfg.get("web_port") or 3081)
    with _LOCK:
        owned = _OWNED and _PROCESS is not None and _PROCESS.poll() is None
    external = bool(http_ok) and not owned
    return {
        "owned": owned,
        "external": external,
        "url": web_url(),
        "port": port,
    }


def health_status() -> dict[str, Any]:
    running = is_running()
    cfg = _cfg()
    port = int(cfg.get("web_port") or 3081)
    port_busy = _port_open(port)
    with _LOCK:
        owned = _OWNED and _PROCESS is not None and _PROCESS.poll() is None
    external = running and not owned
    conflict = port_busy and not running
    return {
        "running": running,
        "owned": owned,
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
    # dsh 凭证优先级：进程 env > .credentials.yaml。脏 env（WorkBuddy/系统）会盖住设置页密钥。
    if bool(_cfg().get("clear_env_api_key", True)):
        from services.harness_credentials import apply_credentials_to_env, strip_llm_env

        strip_llm_env(env)
        apply_credentials_to_env(env)
    return env


def prepare_sidecar_start() -> tuple[bool, str, bool]:
    """校验环境与 Web 组件；返回 (可继续, 提示, 是否已在运行)。"""
    ok_setup, setup_hint = validate_setup()
    if not ok_setup:
        return False, setup_hint, False
    if is_running():
        hint = "Harness 已在运行"
        st = health_status()
        if st.get("owned"):
            hint += "（TOA 托管）"
        else:
            hint += "（外部实例，停止服务可结束或「接管并重启」）"
        if setup_hint:
            hint = f"{hint}\n{setup_hint}"
        return True, hint, True

    node = node_exe_path()
    dsh = dsh_bin_path()
    if not node.is_file():
        return False, f"未找到 Node：{node}", False
    if not dsh.is_file():
        return False, f"未找到 dsh：{dsh}", False

    from services.harness_plugins import ensure_web_profile_bundles

    home = dsh_home_path()
    ok_prof, prof_msg = ensure_web_profile_bundles(node, dsh, home)
    if not ok_prof:
        return (
            False,
            f"Web 组件未就绪：{prof_msg}\n请点「更多 → 修复运行环境」。",
            False,
        )
    return True, "", False


def spawn_sidecar_process() -> tuple[bool, str]:
    """拉起 dsh web 子进程。Windows + Qt 须在主线程调用。"""
    global _PROCESS, _OWNED, _LAST_START_LOG
    port = int(_cfg().get("web_port") or 3081)
    if is_running():
        return True, "Harness 已在运行"
    if _port_open(port):
        return (
            False,
            f"端口 {port} 已被占用且 Harness 未响应 HTTP。"
            "请先结束占用进程、改 Web 端口，或复用已有实例。",
        )

    node = node_exe_path()
    dsh = dsh_bin_path()
    env = _build_env()
    args = [
        str(node),
        str(dsh),
        "--profile",
        "web",
        "--port",
        str(port),
        "--no-open",  # 禁止 dsh 自开系统浏览器；界面由套件内嵌
    ]
    log_path = _sidecar_log_path()
    try:
        # 子进程存活期间保持句柄打开，避免 Windows 上日志丢失
        log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    except OSError:
        log_f = subprocess.DEVNULL
    try:
        with _LOCK:
            proc = subprocess.Popen(
                args,
                env=env,
                cwd=str(dsh.parent),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            _PROCESS = proc
            _OWNED = True
            _LAST_START_LOG = log_path
            if log_f is not subprocess.DEVNULL:
                setattr(proc, "_toa_log_f", log_f)
    except OSError as exc:
        logger.exception("启动 Harness 失败")
        if log_f is not subprocess.DEVNULL:
            try:
                log_f.close()
            except OSError:
                pass
        return False, str(exc)
    return True, "Harness 进程已拉起"


def wait_sidecar_ready(*, timeout_sec: float = 25.0) -> tuple[bool, str]:
    """轮询 Sidecar HTTP 就绪（可放后台线程）。"""
    port = int(_cfg().get("web_port") or 3081)
    log_path = _LAST_START_LOG or _sidecar_log_path()
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        with _LOCK:
            proc = _PROCESS
        if proc is not None and proc.poll() is not None:
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


def sidecar_start_progress() -> tuple[str, str]:
    """单次检查 Sidecar 启动进度。phase: pending | ready | failed。"""
    log_path = _LAST_START_LOG or _sidecar_log_path()
    with _LOCK:
        proc = _PROCESS
    if proc is not None and proc.poll() is not None:
        tail = _read_log_tail(log_path)
        msg = "Harness 进程已退出。"
        if tail:
            msg = f"{msg}\n{tail[-400:]}"
        return "failed", msg
    if is_running(timeout=0.8):
        return "ready", f"Harness 已启动：{web_url()}"
    return "pending", ""


def start(*, wait_ready: bool = True, timeout_sec: float = 25.0) -> tuple[bool, str]:
    """启动 dsh web；若端口已有实例则直接复用。"""
    ok, msg, already = prepare_sidecar_start()
    if not ok:
        return False, msg
    if already:
        return True, msg
    ok_spawn, spawn_msg = spawn_sidecar_process()
    if not ok_spawn:
        return False, spawn_msg
    if wait_ready:
        return wait_sidecar_ready(timeout_sec=timeout_sec)
    return True, spawn_msg


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
        log_f = getattr(_PROCESS, "_toa_log_f", None)
        try:
            _PROCESS.terminate()
            _PROCESS.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _PROCESS.kill()
        except OSError as exc:
            return False, str(exc)
        finally:
            if log_f is not None:
                try:
                    log_f.close()
                except OSError:
                    pass
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
    return ensure_owned_with_credentials()


def ensure_owned_with_credentials(*, wait_ready: bool = True, timeout_sec: float = 25.0) -> tuple[bool, str]:
    """结束外部/脏实例，用 .credentials.yaml 注入后由 TOA 托管启动。

    专治：WorkBuddy 等外部进程占用端口、或本机 DEEPSEEK_API_KEY 盖住设置页密钥，
    导致历史会话接不上大模型。
    """
    port = int(_cfg().get("web_port") or 3081)
    stop(force=True)
    # 再扫一轮，避免 taskkill 后端口仍短暂占用
    if _port_open(port) or is_running(timeout=0.4):
        _kill_pids(_find_listener_pids(port))
    if not _wait_port_quiet(port, timeout_sec=12.0):
        return (
            False,
            f"端口 {port} 仍被占用，无法用设置页密钥重启。"
            "请在任务管理器结束 node.exe 后重试「接管并重启」。",
        )
    ok_spawn, spawn_msg = spawn_sidecar_process()
    if not ok_spawn:
        return False, spawn_msg
    with _LOCK:
        owned = _OWNED and _PROCESS is not None and _PROCESS.poll() is None
    if not owned:
        return False, "Sidecar 未进入 TOA 托管状态，密钥可能未注入。"
    key_hint = "凭证已注入"
    try:
        from services.harness_credentials import load_credential_map, mask_api_key

        creds = load_credential_map()
        ds = creds.get("DEEPSEEK_API_KEY", "")
        if ds:
            key_hint = f"已注入 {mask_api_key(ds)}"
    except Exception:
        pass
    if wait_ready:
        ok, msg = wait_sidecar_ready(timeout_sec=timeout_sec)
        if not ok:
            return False, msg
        return True, f"{msg} · {key_hint} · TOA 托管"
    return True, f"{spawn_msg} · {key_hint}"


def _wait_port_quiet(port: int, *, timeout_sec: float = 10.0) -> bool:
    """等到端口空闲且 HTTP 不再响应。"""
    deadline = time.monotonic() + max(1.0, float(timeout_sec))
    while time.monotonic() < deadline:
        busy = _port_open(port)
        alive = is_running(timeout=0.35)
        if not busy and not alive:
            # 再确认一帧，避免杀进程后立刻被其它程序抢回
            time.sleep(0.25)
            if not _port_open(port) and not is_running(timeout=0.35):
                return True
        time.sleep(0.2)
    return (not _port_open(port)) and (not is_running(timeout=0.35))


def restart() -> tuple[bool, str]:
    st = health_status()
    if st.get("running") and not st.get("owned"):
        return ensure_owned_with_credentials()
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
