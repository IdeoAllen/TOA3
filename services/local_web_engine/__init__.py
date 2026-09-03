# -*- coding: utf-8 -*-
"""本地 Web 引擎：探测 / 启停 / 健康检查（Harness 同构范式的可复用层）。"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import yaml

from services.config_service import project_root, resolve_path

logger = logging.getLogger("TOA3.local_web_engine")


def _expand(p: str) -> Path:
    s = str(p or "").strip().replace("\\", "/")
    if s.startswith("~/"):
        s = str(Path.home() / s[2:])
    return Path(s).expanduser()


@dataclass
class EngineSpec:
    engine_id: str
    title: str
    description: str = ""
    default_roots: list[str] = field(default_factory=list)
    marker_files: list[str] = field(default_factory=lambda: ["package.json"])
    port: int = 0
    health_path: str = "/"
    start_cmds: list[list[str]] = field(default_factory=list)
    stop_on_leave: bool = False
    prefer_embed: bool = True
    menu_show: bool = True
    auto_start: bool = True
    install_git: str = ""
    install_hint: str = ""
    post_install: list[list[str]] = field(default_factory=list)

    def web_url(self) -> str:
        path = self.health_path if self.health_path.startswith("/") else f"/{self.health_path}"
        return f"http://127.0.0.1:{int(self.port)}{path if path != '/' else '/'}"


@dataclass
class EngineStatus:
    installed: bool
    root: Path | None
    running: bool
    healthy: bool
    url: str
    detail: str = ""


_SPECS: dict[str, EngineSpec] | None = None
_PROCS: dict[str, subprocess.Popen] = {}
_USER_ROOTS: dict[str, str] = {}
_REACHABLE_HOST: dict[str, str] = {}
_PORT_TIMEOUT = 0.05  # 秒；未监听时多 host 合计也要很快
_LAST_MISS_AT: dict[str, float] = {}
_MISS_COOLDOWN_S = 1.5  # 刚探测失败则短时跳过，避免轮询卡 UI


def _catalog_path() -> Path:
    return project_root() / "config" / "local_web_engines.yml"


def _user_cfg_path() -> Path:
    return resolve_path("data_dir") / "user" / "local_web_engines.yml"


def load_specs(*, force: bool = False) -> dict[str, EngineSpec]:
    global _SPECS
    if _SPECS is not None and not force:
        return _SPECS
    out: dict[str, EngineSpec] = {}
    raw: dict[str, Any] = {}
    path = _catalog_path()
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw = dict(data.get("engines") or {})
        except Exception as exc:
            logger.warning("读取 local_web_engines.yml 失败: %s", exc)
    user_p = _user_cfg_path()
    if user_p.is_file():
        try:
            ud = yaml.safe_load(user_p.read_text(encoding="utf-8")) or {}
            uengines = ud.get("engines") or {}
            if isinstance(uengines, dict):
                for k, v in uengines.items():
                    if isinstance(v, dict):
                        base = dict(raw.get(k) or {})
                        base.update(v)
                        raw[k] = base
            roots = ud.get("roots") or {}
            if isinstance(roots, dict):
                for k, v in roots.items():
                    if v:
                        _USER_ROOTS[str(k)] = str(v)
        except Exception as exc:
            logger.warning("读取用户 local_web_engines 失败: %s", exc)

    for eid, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        starts = cfg.get("start") or []
        cmds: list[list[str]] = []
        for row in starts:
            if isinstance(row, (list, tuple)) and row:
                cmds.append([str(x) for x in row])
        inst = cfg.get("install") if isinstance(cfg.get("install"), dict) else {}
        post_raw = inst.get("post") or cfg.get("post_install") or []
        post_cmds: list[list[str]] = []
        for row in post_raw:
            if isinstance(row, (list, tuple)) and row:
                post_cmds.append([str(x) for x in row])
        out[str(eid)] = EngineSpec(
            engine_id=str(eid),
            title=str(cfg.get("title") or eid),
            description=str(cfg.get("description") or ""),
            default_roots=[str(x) for x in (cfg.get("default_roots") or [])],
            marker_files=[str(x) for x in (cfg.get("marker_files") or ["package.json"])],
            port=int(cfg.get("port") or 0),
            health_path=str(cfg.get("health_path") or "/"),
            start_cmds=cmds,
            stop_on_leave=bool(cfg.get("stop_on_leave", False)),
            prefer_embed=bool(cfg.get("prefer_embed", True)),
            menu_show=bool(cfg.get("menu_show", True)),
            auto_start=bool(cfg.get("auto_start", True)),
            install_git=str(inst.get("git") or cfg.get("install_git") or "").strip(),
            install_hint=str(inst.get("hint") or cfg.get("install_hint") or "").strip(),
            post_install=post_cmds,
        )

    # 引擎扩展包覆盖/追加（用户包优先于样例；不覆盖已有官方 id 的核心字段时可合并 roots）
    try:
        from services.local_web_engine.packs import load_pack_engine_configs

        for eid, cfg in load_pack_engine_configs().items():
            if eid in out and not bool(cfg.get("_from_pack")):
                continue
            if eid in out and eid in ("open_pencil", "drawio_web", "comfyui_web"):
                continue
            raw[eid] = cfg
            starts = cfg.get("start") or []
            cmds = [[str(x) for x in row] for row in starts if isinstance(row, (list, tuple)) and row]
            inst = cfg.get("install") if isinstance(cfg.get("install"), dict) else {}
            post_raw = inst.get("post") or []
            post_cmds = [
                [str(x) for x in row] for row in post_raw if isinstance(row, (list, tuple)) and row
            ]
            out[str(eid)] = EngineSpec(
                engine_id=str(eid),
                title=str(cfg.get("title") or eid),
                description=str(cfg.get("description") or ""),
                default_roots=[str(x) for x in (cfg.get("default_roots") or [])],
                marker_files=[str(x) for x in (cfg.get("marker_files") or ["index.html"])],
                port=int(cfg.get("port") or 0),
                health_path=str(cfg.get("health_path") or "/"),
                start_cmds=cmds,
                stop_on_leave=bool(cfg.get("stop_on_leave", False)),
                prefer_embed=bool(cfg.get("prefer_embed", True)),
                menu_show=bool(cfg.get("menu_show", True)),
                auto_start=bool(cfg.get("auto_start", True)),
                install_git=str(inst.get("git") or "").strip(),
                install_hint=str(inst.get("hint") or "").strip(),
                post_install=post_cmds,
            )
    except Exception as exc:
        logger.warning("加载引擎扩展包失败: %s", exc)

    _SPECS = out
    return out


def get_spec(engine_id: str) -> EngineSpec | None:
    return load_specs().get(str(engine_id or "").strip())


def prefer_embed(engine_id: str) -> bool:
    """是否在套件内嵌 WebEngine；Comfy 等重 Guest 默认 False（浏览器表面）。"""
    spec = get_spec(engine_id)
    if spec is None:
        return True
    return bool(spec.prefer_embed)


def set_prefer_embed(engine_id: str, embed: bool) -> None:
    """写入 data/user/local_web_engines.yml，覆盖官方 prefer_embed。"""
    eid = str(engine_id or "").strip()
    if not eid:
        return
    path = _user_cfg_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    engines = dict(data.get("engines") or {})
    row = dict(engines.get(eid) or {})
    row["prefer_embed"] = bool(embed)
    engines[eid] = row
    data["engines"] = engines
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    load_specs(force=True)


def save_user_root(engine_id: str, root: str | Path) -> None:
    eid = str(engine_id or "").strip()
    if not eid:
        return
    _USER_ROOTS[eid] = str(root)
    path = _user_cfg_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    roots = dict(data.get("roots") or {})
    roots[eid] = str(root)
    data["roots"] = roots
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _looks_like_root(path: Path, markers: list[str]) -> bool:
    if not path.is_dir():
        return False
    for m in markers:
        if (path / m).exists():
            return True
    return False


def _normalize_install_root(path: Path, markers: list[str]) -> Path | None:
    """安装根或 Comfy Desktop 外层目录 → 含 main.py 的工作目录。"""
    try:
        p = path.resolve()
    except OSError:
        return None
    if _looks_like_root(p, markers):
        return p
    nested = p / "ComfyUI"
    if _looks_like_root(nested, markers):
        return nested.resolve()
    return None


def discover_root(engine_id: str) -> Path | None:
    spec = get_spec(engine_id)
    if spec is None:
        return None
    user = _USER_ROOTS.get(engine_id) or ""
    cands: list[Path] = []
    if user:
        cands.append(_expand(user))
    for r in spec.default_roots:
        cands.append(_expand(r))
    for p in cands:
        found = _normalize_install_root(p, spec.marker_files)
        if found is not None:
            return found
    return None


def _resolve_start_exe(token: str, root: Path) -> str | None:
    """支持 PATH 命令、绝对路径、相对 root 的解释器（如 ../standalone-env/python.exe）。"""
    raw = str(token or "").strip()
    if not raw:
        return None
    p = Path(raw)
    try:
        if p.is_file():
            return str(p.resolve())
    except OSError:
        pass
    try:
        rel = (root / raw).resolve()
        if rel.is_file():
            return str(rel)
    except OSError:
        pass
    return _which(raw)


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    """快速探测本机端口；优先缓存 host，失败再扫 IPv4/IPv6。"""
    return probe_port_host(port, preferred=host) is not None


def probe_port_host(
    port: int,
    *,
    preferred: str | None = None,
    engine_id: str | None = "",
    force: bool = False,
) -> str | None:
    """返回可达 host；都失败返回 None。单次探测超时极短，避免卡导航。"""
    port = int(port)
    eid = str(engine_id or "")
    if eid and not force:
        miss_at = _LAST_MISS_AT.get(eid)
        if miss_at is not None and (time.monotonic() - miss_at) < _MISS_COOLDOWN_S:
            # 冷却期内：若有缓存 host 再快试一次；否则直接判未开
            cached = _REACHABLE_HOST.get(eid)
            if not cached:
                return None
            try:
                with socket.create_connection((cached, port), timeout=_PORT_TIMEOUT):
                    return cached
            except OSError:
                _REACHABLE_HOST.pop(eid, None)
                return None

    hosts: list[str] = []
    cached = _REACHABLE_HOST.get(eid) if eid else None
    # 不扫 localhost：Windows 上解析/回环更慢；IPv4+IPv6 足够
    for h in (preferred, cached, "127.0.0.1", "::1"):
        if h and h not in hosts:
            hosts.append(h)
    for h in hosts:
        try:
            with socket.create_connection((h, port), timeout=_PORT_TIMEOUT):
                if eid:
                    _REACHABLE_HOST[eid] = h
                    _LAST_MISS_AT.pop(eid, None)
                return h
        except OSError:
            continue
    if eid:
        _REACHABLE_HOST.pop(eid, None)
        _LAST_MISS_AT[eid] = time.monotonic()
    return None


def http_healthy(url: str, *, timeout: float = 0.6) -> bool:
    try:
        with urlopen(url, timeout=timeout) as resp:  # noqa: S310 — localhost only
            code = getattr(resp, "status", None) or resp.getcode()
            return 200 <= int(code) < 500
    except (URLError, TimeoutError, OSError, ValueError):
        return False


def resolve_web_url(engine_id: str) -> str:
    """选一个本机可达的 URL（与端口探测共用缓存，不再重复慢扫）。"""
    spec = get_spec(engine_id)
    if spec is None:
        return ""
    port = int(spec.port)
    path = spec.health_path if str(spec.health_path).startswith("/") else f"/{spec.health_path}"
    if not path.startswith("/"):
        path = "/" + path
    host = probe_port_host(port, engine_id=engine_id) or "127.0.0.1"
    if host == "::1":
        return f"http://[::1]:{port}{path}"
    return f"http://{host}:{port}{path}"


def owned_process(engine_id: str) -> subprocess.Popen | None:
    proc = _PROCS.get(engine_id)
    if proc is None:
        return None
    if proc.poll() is not None:
        _PROCS.pop(engine_id, None)
        return None
    return proc


def read_status(engine_id: str, *, probe_http: bool = False) -> EngineStatus:
    """默认只做端口探测（主线程安全、短超时）。"""
    spec = get_spec(engine_id)
    if spec is None:
        return EngineStatus(False, None, False, False, "", "未知引擎")
    root = discover_root(engine_id)
    host = probe_port_host(int(spec.port), engine_id=engine_id)
    proc = owned_process(engine_id)
    port_up = host is not None
    starting = proc is not None and not port_up
    running = port_up
    path = spec.health_path if str(spec.health_path).startswith("/") else f"/{spec.health_path}"
    if host == "::1":
        url = f"http://[::1]:{int(spec.port)}{path}"
    elif host:
        url = f"http://{host}:{int(spec.port)}{path}"
    else:
        url = spec.web_url()
    healthy = bool(running)
    if probe_http and running:
        healthy = http_healthy(url)
    detail = ""
    if root is None:
        detail = "未找到安装目录（可在设置中指定根路径）"
    elif starting:
        detail = "启动中 · 等待端口打开"
    elif not running:
        detail = "已安装 · 服务未启动"
    else:
        detail = "服务已监听"
    return EngineStatus(
        installed=root is not None,
        root=root,
        running=running,
        healthy=healthy,
        url=url,
        detail=detail,
    )


def _which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def start_engine(engine_id: str) -> tuple[bool, str]:
    spec = get_spec(engine_id)
    if spec is None:
        return False, "未知引擎"
    st = read_status(engine_id)
    if st.running:
        return True, "已在运行"
    root = st.root
    if root is None:
        return False, st.detail or "未安装"
    if owned_process(engine_id) is not None:
        return True, "启动中"

    from services.storage_paths import module_data_dir

    log_dir = module_data_dir("local_web_engine", create=True) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{engine_id}.log"

    last_err = "无可用启动命令"
    for argv in spec.start_cmds:
        if not argv:
            continue
        exe = _resolve_start_exe(argv[0], root)
        if exe is None:
            last_err = f"未找到命令：{argv[0]}"
            continue
        cmd = [exe, *argv[1:]]
        try:
            creationflags = 0
            use_shell = False
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                if exe.lower().endswith((".cmd", ".bat")):
                    use_shell = True
                    creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
                else:
                    creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
            try:
                proc = subprocess.Popen(
                    cmd if not use_shell else subprocess.list2cmdline(cmd),
                    cwd=str(root),
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    shell=use_shell,
                    creationflags=creationflags,
                )
            except Exception:
                log_f.close()
                raise
            setattr(proc, "_toa_log_f", log_f)
            _PROCS[engine_id] = proc
            # 仅短探是否秒退；长等放到页内轮询，避免卡死 UI 主线程
            time.sleep(0.35)
            if proc.poll() is not None:
                _PROCS.pop(engine_id, None)
                try:
                    log_f.close()
                except Exception:
                    pass
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-600:]
                except OSError:
                    pass
                last_err = f"进程立即退出（code {proc.returncode}）"
                if tail:
                    last_err += f"\n{tail}"
                continue
            logger.info("启动本地引擎 %s: %s cwd=%s pid=%s log=%s", engine_id, cmd, root, proc.pid, log_path)
            return True, f"已启动（pid {proc.pid}）"
        except OSError as exc:
            last_err = str(exc)
            continue
    return False, last_err


def wait_engine_ready(
    engine_id: str,
    *,
    timeout_sec: float = 45.0,
    poll_sec: float = 0.4,
) -> tuple[bool, str]:
    """阻塞等待端口就绪（供后台线程 / 校验脚本；勿在 UI 主线程长时间调用）。"""
    spec = get_spec(engine_id)
    if spec is None:
        return False, "未知引擎"
    deadline = time.monotonic() + max(3.0, float(timeout_sec))
    url = ""
    while time.monotonic() < deadline:
        st = read_status(engine_id, probe_http=False)
        url = st.url
        if st.running:
            if http_healthy(st.url, timeout=0.8):
                return True, st.url
            # 端口已开但 HTTP 未好（如 Vite 编译）——继续等
            return True, st.url  # 端口即视为可嵌；页内可再重试
        proc = owned_process(engine_id)
        if proc is None and time.monotonic() > deadline - timeout_sec + 2.0:
            # 曾启动但已死
            pass
        time.sleep(max(0.15, float(poll_sec)))
    proc = owned_process(engine_id)
    if proc is not None and proc.poll() is not None:
        return False, f"启动失败：进程已退出。详见 logs/{engine_id}.log"
    return False, f"等待就绪超时（{timeout_sec:.0f}s）· {url or spec.web_url()}"


def stop_engine(engine_id: str) -> tuple[bool, str]:
    """停止本引擎。优先杀 TOA 子进程；否则尝试结束占用端口的本机进程。"""
    proc = owned_process(engine_id)
    if proc is not None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            _PROCS.pop(engine_id, None)
            return True, "已停止"
        except OSError as exc:
            return False, str(exc)

    spec = get_spec(engine_id)
    if spec is None:
        return True, "无运行中的服务"
    if not port_open(spec.port):
        return True, "服务未在运行"
    # 外部已启动：按端口回收（不弹恐吓文案）
    killed = _kill_listeners_on_port(int(spec.port))
    if killed:
        return True, f"已结束端口 {spec.port} 上的进程"
    return True, "未由 TOA 拉起；请在终端自行结束，或关闭占用该端口的窗口"


def _kill_listeners_on_port(port: int) -> bool:
    """Windows：结束监听该端口的进程；其它平台尽力而为。"""
    if sys.platform != "win32":
        return False
    try:
        import re
        import subprocess as sp

        out = sp.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(sp, "CREATE_NO_WINDOW", 0),
        )
        pids: set[int] = set()
        # TCP  127.0.0.1:1420  ... LISTENING  1234  /  [::1]:1420
        pat = re.compile(
            rf":{port}\s+\S+\s+LISTENING\s+(\d+)\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in pat.finditer(out):
            pid = int(m.group(1))
            if pid > 0:
                pids.add(pid)
        ok_any = False
        for pid in pids:
            try:
                sp.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    stdout=sp.DEVNULL,
                    stderr=sp.DEVNULL,
                    creationflags=getattr(sp, "CREATE_NO_WINDOW", 0),
                )
                ok_any = True
            except OSError:
                continue
        return ok_any
    except Exception:
        logger.debug("按端口停止失败", exc_info=True)
        return False


def wait_healthy(engine_id: str, *, timeout_s: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if read_status(engine_id).healthy:
            return True
        time.sleep(0.5)
    return False
