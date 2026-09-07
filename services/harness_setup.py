# -*- coding: utf-8 -*-
"""Harness 运行环境检测与一键安装。"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SetupGate 识别：缺 Node 时展示「去安装 Node.js」
NEED_NODE_PREFIX = "NEED_NODE:"


def _workbuddy_roots() -> list[Path]:
    home = Path.home()
    roots = [home / ".workbuddy", home / "WorkBuddy"]
    desktop = home / "Desktop"
    if desktop.is_dir():
        roots.append(desktop / "WorkBuddy")
    return [r for r in roots if r.is_dir()]


def discover_runtime() -> dict[str, str]:
    """扫描运行时：优先 TOA 独立目录，其次本机 Node，再次 WorkBuddy（仅借 node/dsh，不绑其 home）。"""
    found: dict[str, str] = {}
    toa_root = default_install_root()
    toa_dsh = toa_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    toa_home = toa_root / ".dsh"
    if toa_dsh.is_file():
        found["dsh_bin"] = str(toa_dsh)
    # 始终优先 TOA home（可尚不存在）；绝不把 WorkBuddy/.dsh 写入发现结果
    found["dsh_home"] = str(toa_home)

    sys_node = find_system_node()
    if sys_node is not None:
        found.setdefault("node_exe", str(sys_node))

    for root in _workbuddy_roots():
        binaries = root / "binaries" / "node" / "versions"
        if binaries.is_dir():
            versions = sorted(binaries.iterdir(), key=lambda p: p.name, reverse=True)
            for ver in versions:
                node = ver / "node.exe"
                dsh = ver / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
                if node.is_file():
                    found.setdefault("node_exe", str(node))
                if dsh.is_file():
                    found.setdefault("dsh_bin", str(dsh))
                if found.get("node_exe") and found.get("dsh_bin"):
                    break
        if found.get("node_exe") and found.get("dsh_bin"):
            break
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
    优先 TOA 独立目录 ~/.toa3/harness-runtime；可回落本机 Node / WorkBuddy。
    """
    try:
        return _install_harness_runtime_inner()
    except OSError as exc:
        from services.harness_plugins import _friendly_os_error

        return False, _friendly_os_error(exc)


def _install_harness_runtime_inner() -> tuple[bool, str]:
    from services.harness_plugins import ensure_web_profile_bundles
    from services.harness_config import (
        align_harness_runtime_config,
        is_workbuddy_home,
        load_harness_config,
        save_harness_config,
    )

    align_harness_runtime_config(persist=True)

    found = discover_runtime()
    node_s = str(found.get("node_exe") or "").strip()
    dsh_s = str(found.get("dsh_bin") or "").strip()

    if not node_s or not Path(node_s).is_file():
        sys_node = find_system_node()
        if sys_node is not None:
            node_s = str(sys_node)

    # 已有 dsh：登记到 TOA 数据目录（勿再绑 WorkBuddy 脏 home）
    if node_s and dsh_s and Path(node_s).is_file() and Path(dsh_s).is_file():
        node_p = Path(node_s)
        dsh_p = Path(dsh_s)
        cfg = load_harness_config()
        home_s = str(cfg.get("dsh_home") or "").strip()
        if (not home_s) or is_workbuddy_home(home_s):
            home = default_install_root() / ".dsh"
        else:
            home = Path(home_s)
        ok_home, _ = init_dsh_home(home)
        if not ok_home:
            return False, "无法创建 DSH 数据目录"
        ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
        if not ok_prof:
            return False, f"Web 界面组件安装失败：{prof_msg}"
        save_harness_config(
            {
                "enabled": True,
                "auto_start": True,
                "surface_mode": "browser",
                "web_port": 3082,
                "node_exe": str(node_p),
                "dsh_bin": str(dsh_p),
                "dsh_home": str(home),
            }
        )
        load_harness_config(force=True)
        try:
            from services.harness_model_defaults import ensure_official_default_model

            ensure_official_default_model()
        except Exception:
            pass
        return True, "已登记本机 Harness 环境并完成 Web 组件检查"

    if node_s and Path(node_s).is_file():
        node_p = Path(node_s)
        root = default_install_root()
        ok, msg = npm_install_dsh(node_p, root)
        if not ok:
            return False, msg
        dsh_p = root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        home = root / ".dsh"
        ok_home, _ = init_dsh_home(home)
        if not ok_home:
            return False, "无法创建 DSH 数据目录"
        ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
        if not ok_prof:
            return False, f"Web 界面组件安装失败：{prof_msg}"
        save_harness_config(
            {
                "enabled": True,
                "auto_start": True,
                "surface_mode": "browser",
                "web_port": 3082,
                "node_exe": str(node_p),
                "dsh_bin": str(dsh_p),
                "dsh_home": str(home),
            }
        )
        load_harness_config(force=True)
        try:
            from services.harness_model_defaults import ensure_official_default_model

            ensure_official_default_model()
        except Exception:
            pass
        return True, "DeepSeek Harness 安装完成，请保存 API Key 后启动服务"

    return (
        False,
        f"{NEED_NODE_PREFIX}"
        "本机未找到 Node.js。请先安装官方 LTS（18+），装完后点「装好后点这里重试」。"
        "不必手填路径，也不必安装其它带 Harness 的软件。",
    )


def repair_harness_runtime() -> tuple[bool, str]:
    """修复：重建 DSH 目录、补装 web profile，并检查 API Key 冲突。"""
    from services.harness_config import (
        align_harness_runtime_config,
        is_workbuddy_home,
        load_harness_config,
        save_harness_config,
    )
    from services.harness_credentials import diagnose_llm_access, has_api_key
    from services.harness_model_defaults import ensure_official_default_model
    from services.harness_plugins import (
        ensure_web_profile_bundles,
        heal_web_profile_junction,
        link_web_profile_node_modules,
        sanitize_web_profile_package,
        web_profile_ready,
    )

    align_notes = align_harness_runtime_config(persist=True, force=True)
    cfg = load_harness_config(force=True)
    node_s = str(cfg.get("node_exe") or "").strip()
    dsh_s = str(cfg.get("dsh_bin") or "").strip()
    if not node_s or not dsh_s or not Path(node_s).is_file() or not Path(dsh_s).is_file():
        return install_harness_runtime()
    node_p = Path(node_s)
    dsh_p = Path(dsh_s)
    home_s = str(cfg.get("dsh_home") or "").strip()
    if (not home_s) or is_workbuddy_home(home_s):
        home = default_install_root() / ".dsh"
    else:
        home = Path(home_s)
    ok_home, _ = init_dsh_home(home)
    if not ok_home:
        return False, "无法创建 DSH 数据目录"

    notes: list[str] = list(align_notes)
    changed_model, model_msg = ensure_official_default_model()
    if changed_model:
        notes.append(model_msg)

    if web_profile_ready(home, dsh=dsh_p):
        notes.append("Web 组件已就绪")
    else:
        ok_link, link_msg = link_web_profile_node_modules(dsh_p, home)
        if ok_link:
            notes.append("已修复 Web 组件")
        else:
            ok_heal, heal_msg = heal_web_profile_junction(dsh_p, home)
            if ok_heal:
                notes.append(heal_msg or "已重建 Web 组件联接")
            else:
                ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
                if not ok_prof:
                    return False, prof_msg or heal_msg or link_msg
                notes.append("已补装 Web 组件")

    ok_san, san_msg = sanitize_web_profile_package(home, dsh=dsh_p)
    if not ok_san:
        return False, f"清理 profile 插件失败：{san_msg}"
    if "移除" in san_msg:
        notes.append(san_msg)

    save_harness_config(
        {
            "enabled": True,
            "auto_start": True,
            "surface_mode": "browser",
            "node_exe": str(node_p),
            "dsh_bin": str(dsh_p),
            "dsh_home": str(home),
        }
    )
    load_harness_config(force=True)

    key_ok, key_msg = diagnose_llm_access()
    if not has_api_key():
        return False, "环境组件已检查，但未配置 API Key。请到系统设置 → 能力接入 → Harness 保存密钥后「重启服务」。"
    if not key_ok:
        notes.append(key_msg)
        notes.append("请点「更多 → 重启服务」，由 TOA 用正确密钥重新拉起（勿继续用外部脏环境实例）。")
        return True, "\n".join(notes)
    notes.append(key_msg)
    notes.append("若历史会话仍接不上模型：点「更多 → 重启服务」刷新 Sidecar 凭证。")
    return True, "\n".join(notes)
