# -*- coding: utf-8 -*-
"""Harness 运行环境检测与一键安装。"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _workbuddy_roots() -> list[Path]:
    home = Path.home()
    roots = [home / ".workbuddy", home / "WorkBuddy"]
    desktop = home / "Desktop"
    if desktop.is_dir():
        roots.append(desktop / "WorkBuddy")
    return [r for r in roots if r.is_dir()]


def discover_runtime() -> dict[str, str]:
    """扫描 WorkBuddy / 常见路径，返回 node_exe、dsh_bin、dsh_home 候选。"""
    found: dict[str, str] = {}
    for root in _workbuddy_roots():
        binaries = root / "binaries" / "node" / "versions"
        if binaries.is_dir():
            versions = sorted(binaries.iterdir(), key=lambda p: p.name, reverse=True)
            for ver in versions:
                node = ver / "node.exe"
                dsh = ver / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
                if node.is_file() and dsh.is_file():
                    found.setdefault("node_exe", str(node))
                    found.setdefault("dsh_bin", str(dsh))
                    break
        for child in root.iterdir():
            if not child.is_dir():
                continue
            dsh_home = child / ".dsh"
            if dsh_home.is_dir():
                found.setdefault("dsh_home", str(dsh_home))
    return found


def find_system_node() -> Path | None:
    """本机 Node（PATH / 常见安装路径）。"""
    import shutil

    which = shutil.which("node")
    if which:
        p = Path(which)
        if p.is_file():
            return p
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "nodejs" / "node.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs" / "node.exe",
    ]
    for p in roots:
        if p.is_file():
            return p
    return None


def default_install_root() -> Path:
    return Path.home() / ".toa3" / "harness-runtime"


def npm_install_dsh(node_exe: Path, install_root: Path, *, timeout: float = 300.0) -> tuple[bool, str]:
    install_root.mkdir(parents=True, exist_ok=True)
    npm = node_exe.parent / "npm.cmd"
    if not npm.is_file():
        npm = node_exe.parent / "npm"
    if not npm.is_file():
        return False, "未找到 npm，请使用完整 Node 安装包。"
    cmd = [str(npm), "install", "@deepseek-ai/dsh", "--prefix", str(install_root), "--no-fund", "--no-audit"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip()[-400:]
            return False, f"安装失败：{tail or 'npm 退出非零'}"
    except subprocess.TimeoutExpired:
        return False, "安装超时，请检查网络后重试。"
    except OSError as exc:
        return False, str(exc)
    dsh = install_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    if not dsh.is_file():
        return False, "安装完成但未找到 dsh，请重试或手动检测路径。"
    return True, str(dsh)


def init_dsh_home(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        profiles = path / "profiles" / "web"
        profiles.mkdir(parents=True, exist_ok=True)
        pkg = profiles / "package.json"
        if not pkg.is_file():
            pkg.write_text(
                '{"name":"dsh-profile-web","private":true,"dependencies":{},'
                '"dsh":{"profile":{"bundles":["@deepseek-ai/dsh-base","@deepseek-ai/dsh-web-app"]}}}',
                encoding="utf-8",
            )
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


def runtime_report(node: Path, dsh: Path, home: Path) -> dict[str, Any]:
    return {
        "node_ok": node.is_file(),
        "dsh_ok": dsh.is_file(),
        "home_ok": home.is_dir(),
        "node_exe": str(node),
        "dsh_bin": str(dsh),
        "dsh_home": str(home),
    }


def install_harness_runtime() -> tuple[bool, str]:
    """
    一键安装 / 检测 Harness 运行环境（Node + @deepseek-ai/dsh + DSH 目录）。
    优先复用 WorkBuddy；否则用本机 Node 装到 ~/.toa3/harness-runtime。
    """
    from services.harness_plugins import ensure_web_profile_bundles
    from services.harness_config import load_harness_config, save_harness_config

    found = discover_runtime()
    node_s = str(found.get("node_exe") or "").strip()
    dsh_s = str(found.get("dsh_bin") or "").strip()

    if not node_s or not Path(node_s).is_file():
        sys_node = find_system_node()
        if sys_node is not None:
            node_s = str(sys_node)

    if node_s and dsh_s and Path(node_s).is_file() and Path(dsh_s).is_file():
        node_p = Path(node_s)
        dsh_p = Path(dsh_s)
        cfg = load_harness_config()
        home_s = str(found.get("dsh_home") or cfg.get("dsh_home") or "").strip()
        home = Path(home_s) if home_s else default_install_root() / ".dsh"
        ok_home, _ = init_dsh_home(home)
        if not ok_home:
            return False, "无法创建 DSH 数据目录"
        ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
        if not ok_prof:
            return False, f"Web 界面组件安装失败：{prof_msg}"
        save_harness_config({"node_exe": str(node_p), "dsh_bin": str(dsh_p), "dsh_home": str(home)})
        load_harness_config(force=True)
        return True, "已登记本机 Harness 环境并完成 Web 组件检查"

    if node_s and Path(node_s).is_file():
        node_p = Path(node_s)
        root = default_install_root()
        ok, msg = npm_install_dsh(node_p, root)
        if not ok:
            return False, msg
        dsh_p = root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        cfg = load_harness_config()
        home_s = str(cfg.get("dsh_home") or "").strip()
        home = Path(home_s) if home_s else root / ".dsh"
        ok_home, _ = init_dsh_home(home)
        if not ok_home:
            return False, "无法创建 DSH 数据目录"
        ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
        if not ok_prof:
            return False, f"Web 界面组件安装失败：{prof_msg}"
        save_harness_config(
            {"node_exe": str(node_p), "dsh_bin": str(dsh_p), "dsh_home": str(home)}
        )
        load_harness_config(force=True)
        return True, "DeepSeek Harness 安装完成，请保存 API Key 后启动服务"

    return (
        False,
        "未找到 Node.js。请先安装 Node 18+（https://nodejs.org），"
        "或安装带 Harness 的 WorkBuddy 后点「一键安装」重试。",
    )


def repair_harness_runtime() -> tuple[bool, str]:
    """修复：重建 DSH 目录并补装 web profile 组件（不重复 npm 装 dsh）。"""
    from services.harness_config import load_harness_config, save_harness_config
    from services.harness_plugins import (
        ensure_web_profile_bundles,
        link_web_profile_node_modules,
        web_profile_ready,
    )

    cfg = load_harness_config(force=True)
    node_s = str(cfg.get("node_exe") or "").strip()
    dsh_s = str(cfg.get("dsh_bin") or "").strip()
    if not node_s or not dsh_s or not Path(node_s).is_file() or not Path(dsh_s).is_file():
        return install_harness_runtime()
    node_p = Path(node_s)
    dsh_p = Path(dsh_s)
    home_s = str(cfg.get("dsh_home") or "").strip()
    home = Path(home_s) if home_s else default_install_root() / ".dsh"
    ok_home, _ = init_dsh_home(home)
    if not ok_home:
        return False, "无法创建 DSH 数据目录"
    if web_profile_ready(home):
        save_harness_config({"node_exe": str(node_p), "dsh_bin": str(dsh_p), "dsh_home": str(home)})
        load_harness_config(force=True)
        return True, "Web 组件已就绪，请点「启动服务」"
    ok_link, link_msg = link_web_profile_node_modules(dsh_p, home)
    if ok_link:
        save_harness_config({"node_exe": str(node_p), "dsh_bin": str(dsh_p), "dsh_home": str(home)})
        load_harness_config(force=True)
        return True, "已修复 Web 组件，请点「启动服务」"
    ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
    if not ok_prof:
        return False, prof_msg
    save_harness_config({"node_exe": str(node_p), "dsh_bin": str(dsh_p), "dsh_home": str(home)})
    load_harness_config(force=True)
    return True, "环境已修复，请保存 API Key 后点「启动服务」"
