# -*- coding: utf-8 -*-
"""Harness web profile 插件依赖管理。"""
from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from services.harness_config import dsh_bin_path, dsh_home_path, node_exe_path

logger = logging.getLogger(__name__)

_PROFILE = "web"
_WEB_BUNDLES = ("@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app")
_CORE_MARKERS = (
    "@deepseek-ai/dsh-base",
    "@deepseek-ai/dsh-web-app",
    "@deepseek-ai/cordis-plugin-timer",
)


def dsh_vendored_node_modules(dsh: Path) -> Path | None:
    """dsh 包内自带的 node_modules（WorkBuddy / npm 安装均会有）。"""
    pkg_root = dsh.resolve().parent.parent
    vendored = pkg_root / "node_modules"
    if vendored.is_dir() and (vendored / "@deepseek-ai").is_dir():
        return vendored
    return None


def profile_dir_for(home: Path) -> Path:
    return home / "profiles" / _PROFILE


def web_profile_node_modules(home: Path) -> Path:
    return profile_dir_for(home) / "node_modules"


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name == "nt":
            return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False
    return False


def _same_resolved(path: Path, target: Path) -> bool:
    try:
        return path.resolve() == target.resolve()
    except OSError:
        return False


def _remove_node_modules(path: Path) -> None:
    if not path.exists():
        return
    if _is_reparse_point(path):
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        else:
            path.unlink()
        return
    shutil.rmtree(path, ignore_errors=True)


def web_profile_ready(home: Path) -> bool:
    """profile/web/node_modules 是否已具备 dsh web 启动所需包。"""
    mods = web_profile_node_modules(home)
    if not mods.is_dir():
        return False
    for rel in _CORE_MARKERS:
        if not (mods / rel).exists():
            return False
    return True


def link_web_profile_node_modules(dsh: Path, home: Path) -> tuple[bool, str]:
    """
    将 profile/web/node_modules 链接到 dsh 包内 vendored 目录。
    公开 npm 无法拉取 @deepseek-ai 私有包时，这是 WorkBuddy 路径的可靠修复方式。
    """
    vendored = dsh_vendored_node_modules(dsh)
    if vendored is None:
        return False, "未找到 dsh 内置组件目录"
    profile = profile_dir_for(home)
    profile.mkdir(parents=True, exist_ok=True)
    link = web_profile_node_modules(home)
    if link.exists():
        if web_profile_ready(home):
            return True, "Web 组件目录已就绪"
        if _same_resolved(link, vendored):
            return True, "Web 组件已链接"
        _remove_node_modules(link)
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(vendored)],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip()[-300:]
                return False, tail or "创建 node_modules 联接失败"
        else:
            link.symlink_to(vendored, target_is_directory=True)
    except OSError as exc:
        return False, str(exc)
    if web_profile_ready(home):
        return True, "已链接 dsh 内置 Web 组件"
    return False, "链接后仍缺少核心 Web 组件，请点「修复运行环境」"


def _run_plugin_add(
    node: Path,
    dsh: Path,
    home: Path,
    *,
    timeout: float = 300.0,
) -> tuple[bool, str]:
    cmd = [str(node), str(dsh), "plugin", "--profile", _PROFILE, "add", *_WEB_BUNDLES]
    env = os.environ.copy()
    env["DSH_HOME"] = str(home)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(dsh.parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        combined = f"{out}\n{err}".lower()
        if result.returncode == 0:
            return True, "web profile 就绪"
        if "already" in combined or "已存在" in combined:
            return True, "web profile 已存在"
        return False, (err or out or "plugin add 失败")[-500:]
    except subprocess.TimeoutExpired:
        return False, "安装 web 组件超时，请检查网络后重试"
    except OSError as exc:
        return False, str(exc)


def ensure_web_profile_bundles(
    node: Path,
    dsh: Path,
    home: Path,
    *,
    timeout: float = 300.0,
) -> tuple[bool, str]:
    """确保 web profile 核心 bundle 已安装（dsh web 启动必需）。"""
    from services.harness_setup import init_dsh_home

    if not node.is_file() or not dsh.is_file():
        return False, "Node 或 dsh 路径无效"
    home.mkdir(parents=True, exist_ok=True)
    init_dsh_home(home)

    if web_profile_ready(home):
        return True, "web profile 已就绪"

    ok_link, link_msg = link_web_profile_node_modules(dsh, home)
    if ok_link:
        return True, link_msg

    # 仅有 vendored 目录时不再走 pnpm（公开 npm 无法拉取 @deepseek-ai 私有包）
    if dsh_vendored_node_modules(dsh) is not None:
        return False, link_msg or "无法链接 dsh 内置 Web 组件"

    ok_add, add_msg = _run_plugin_add(node, dsh, home, timeout=timeout)
    if ok_add and web_profile_ready(home):
        return True, add_msg

    ok_link2, link_msg2 = link_web_profile_node_modules(dsh, home)
    if ok_link2:
        return True, link_msg2

    detail = add_msg if not ok_add else link_msg2
    return False, detail or link_msg or "Web 组件安装失败"


def profile_dir() -> Path:
    return dsh_home_path() / "profiles" / _PROFILE


def profile_package_json() -> Path:
    return profile_dir() / "package.json"


def list_plugins() -> list[dict[str, str]]:
    path = profile_package_json()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[dict[str, str]] = []
    bundles = (data.get("dsh") or {}).get("profile", {}).get("bundles") or []
    for b in bundles:
        out.append({"name": str(b), "kind": "核心组件"})
    deps = data.get("dependencies") or {}
    for name, ver in deps.items():
        out.append({"name": str(name), "kind": f"扩展 {ver}"})
    return out


def _run_dsh_plugin(pnpm_args: list[str], *, timeout: float = 300.0) -> tuple[bool, str]:
    node = node_exe_path()
    dsh = dsh_bin_path()
    if not node.is_file() or not dsh.is_file():
        return False, "请先完成 Node 与 dsh 安装。"
    home = dsh_home_path()
    home.mkdir(parents=True, exist_ok=True)
    cmd = [str(node), str(dsh), "plugin", "--profile", _PROFILE, *pnpm_args]
    env = os.environ.copy()
    env["DSH_HOME"] = str(home)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(dsh.parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if result.returncode != 0:
            return False, (err or out or "插件命令失败")[-500:]
        return True, (out or "完成")[-500:]
    except subprocess.TimeoutExpired:
        return False, "操作超时，请检查网络。"
    except OSError as exc:
        return False, str(exc)


def add_plugin(package_name: str) -> tuple[bool, str]:
    pkg = (package_name or "").strip()
    if not pkg:
        return False, "请输入插件包名，例如 @deepseek-ai/dsh-xxx。"
    return _run_dsh_plugin(["add", pkg])


def remove_plugin(package_name: str) -> tuple[bool, str]:
    pkg = (package_name or "").strip()
    if not pkg:
        return False, "请输入要移除的包名。"
    return _run_dsh_plugin(["remove", pkg])
