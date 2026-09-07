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
# Windows STATUS_UNTRUSTED_MOUNT_POINT — 穿越「不受信任」联接/装入点
_WINERR_UNTRUSTED_MOUNT = 448


def _dsh_pkg_root(dsh: Path) -> Path:
    """bin.js → …/@deepseek-ai/dsh 包根。"""
    try:
        return dsh.resolve().parent.parent
    except OSError:
        return dsh.parent.parent


def _vendored_candidates(dsh: Path) -> list[Path]:
    """候选 node_modules：包内嵌套目录，以及 npm hoist 到安装根的目录。"""
    pkg_root = _dsh_pkg_root(dsh)
    out: list[Path] = [pkg_root / "node_modules"]
    # npm --prefix 安装：…/node_modules/@deepseek-ai/dsh → …/node_modules
    if pkg_root.name == "dsh" and pkg_root.parent.name == "@deepseek-ai":
        out.append(pkg_root.parent.parent)
    return out


def dsh_vendored_node_modules(dsh: Path) -> Path | None:
    """具备核心 Web 组件标记的 node_modules（嵌套或 npm hoist 均可）。

    注意：仅有空的 ``@deepseek-ai`` 目录不算就绪——旧逻辑会误把残缺树当可用。
    """
    for vendored in _vendored_candidates(dsh):
        if _markers_ready_at(vendored):
            return vendored
    return None


def find_external_vendored_node_modules() -> Path | None:
    """从本机 WorkBuddy 等已装 dsh 中找完整 vendored 目录。"""
    home = Path.home()
    roots = [home / ".workbuddy", home / "WorkBuddy"]
    for root in roots:
        binaries = root / "binaries" / "node" / "versions"
        if not _safe_is_dir(binaries):
            continue
        try:
            versions = sorted(binaries.iterdir(), key=lambda p: p.name, reverse=True)
        except OSError:
            continue
        for ver in versions:
            # WorkBuddy 多为包内嵌套；也可能 hoist
            for vendored in (
                ver / "node_modules" / "@deepseek-ai" / "dsh" / "node_modules",
                ver / "node_modules",
            ):
                if _markers_ready_at(vendored):
                    return vendored
    return None


def seed_dsh_vendored_node_modules(dsh: Path) -> tuple[bool, str]:
    """若 TOA 的 dsh 缺核心 Web 组件，从本机已装完整树复制到包内嵌套目录。"""
    if dsh_vendored_node_modules(dsh) is not None:
        return True, "dsh 内置组件已存在"
    src = find_external_vendored_node_modules()
    if src is None:
        return False, "未找到可复制的 Web 组件源（需本机曾装过带完整 dsh 的 WorkBuddy，或官方发行包）"
    pkg_root = _dsh_pkg_root(dsh)
    dst = pkg_root / "node_modules"
    try:
        if _path_lexists(dst):
            _remove_node_modules(dst)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    except OSError as exc:
        return False, _friendly_os_error(exc)
    if dsh_vendored_node_modules(dsh) is None:
        return False, "复制后仍缺少 dsh 内置组件"
    return True, "已从本机已装 dsh 复制 Web 组件"


def profile_dir_for(home: Path) -> Path:
    return home / "profiles" / _PROFILE


def web_profile_node_modules(home: Path) -> Path:
    return profile_dir_for(home) / "node_modules"


def _is_winerr_untrusted(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) == _WINERR_UNTRUSTED_MOUNT


def _friendly_os_error(exc: BaseException) -> str:
    if _is_winerr_untrusted(exc):
        return (
            "Web 组件目录联接失效（WinError 448：不受信任的装入点）。"
            "请点「更多 → 修复运行环境」，或关闭后重开本页再试。"
        )
    return str(exc)


def _path_lexists(path: Path) -> bool:
    """仅 lstat，不跟随联接（避免 WinError 448）。"""
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name == "nt":
            st = path.lstat()
            attrs = getattr(st, "st_file_attributes", None)
            if attrs is None:
                return False
            return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False
    except Exception:
        return False
    return False


def _junction_target_nt(path: Path) -> Path | None:
    """读取目录联接目标，不打开目标树。"""
    if os.name != "nt":
        return None
    try:
        # Python 3.8+：Windows 上 readlink 可读 junction
        target = path.readlink()
        if not target.is_absolute():
            target = (path.parent / target).resolve()
        return target
    except OSError:
        pass
    except ValueError:
        pass
    try:
        # Get-Item Target 备用
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Item -LiteralPath '{path}').Target",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        line = (result.stdout or "").strip().splitlines()
        if line:
            return Path(line[0].strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError as exc:
        if _is_winerr_untrusted(exc):
            return False
        return False


def _safe_child_exists(root: Path, rel: str) -> bool:
    child = root.joinpath(*rel.split("/"))
    try:
        return child.exists()
    except OSError as exc:
        if _is_winerr_untrusted(exc):
            return False
        return False


def _same_resolved(path: Path, target: Path) -> bool:
    try:
        if os.name == "nt" and _is_reparse_point(path):
            jt = _junction_target_nt(path)
            if jt is not None:
                try:
                    return jt.resolve() == target.resolve()
                except OSError:
                    return os.path.normcase(str(jt)) == os.path.normcase(str(target))
        return path.resolve() == target.resolve()
    except OSError:
        return False


def _remove_node_modules(path: Path) -> None:
    """删除联接只用 rmdir；禁止对联接 shutil.rmtree（会踩 WinError 448）。"""
    if not _path_lexists(path):
        return
    if _is_reparse_point(path) or (os.name == "nt" and path.is_symlink()):
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            try:
                path.unlink()
            except OSError:
                pass
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError as exc:
        logger.warning("rmtree node_modules failed: %s", exc)


def _markers_ready_at(root: Path) -> bool:
    if not _safe_is_dir(root):
        return False
    for rel in _CORE_MARKERS:
        if not _safe_child_exists(root, rel):
            return False
    return True


def web_profile_ready(home: Path, *, dsh: Path | None = None) -> bool:
    """profile/web/node_modules 是否已具备 dsh web 启动所需包。

    Windows：优先在联接目标 / dsh vendored 实目录上检查，避免穿越不受信任装入点。
    """
    mods = web_profile_node_modules(home)
    if not _path_lexists(mods):
        return False

    candidates: list[Path] = []
    if os.name == "nt" and _is_reparse_point(mods):
        jt = _junction_target_nt(mods)
        if jt is not None:
            candidates.append(jt)
    if dsh is not None:
        vendored = dsh_vendored_node_modules(dsh)
        if vendored is not None:
            candidates.append(vendored)
    if not _is_reparse_point(mods):
        candidates.insert(0, mods)
    else:
        # 联接存在但读不到目标时，仍尝试 vendored
        pass

    seen: set[str] = set()
    for root in candidates:
        key = os.path.normcase(str(root))
        if key in seen:
            continue
        seen.add(key)
        if _markers_ready_at(root):
            return True
    # 最后兜底：直接查 mods（可能触发 448，已吞掉）
    return _markers_ready_at(mods)


def link_web_profile_node_modules(dsh: Path, home: Path) -> tuple[bool, str]:
    """
    将 profile/web/node_modules 链接到 dsh 包内 vendored 目录。
    公开 npm 无法拉取 @deepseek-ai 私有包时，这是 WorkBuddy 路径的可靠修复方式。
    """
    vendored = dsh_vendored_node_modules(dsh)
    if vendored is None:
        return False, "未找到 dsh 内置组件目录"
    profile = profile_dir_for(home)
    try:
        profile.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, _friendly_os_error(exc)
    link = web_profile_node_modules(home)
    try:
        if _path_lexists(link):
            if web_profile_ready(home, dsh=dsh):
                return True, "Web 组件目录已就绪"
            if _same_resolved(link, vendored) and _markers_ready_at(vendored):
                return True, "Web 组件已链接"
            _remove_node_modules(link)
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
        return False, _friendly_os_error(exc)
    if web_profile_ready(home, dsh=dsh):
        return True, "已链接 dsh 内置 Web 组件"
    return False, "链接后仍缺少核心 Web 组件，请点「修复运行环境」"


def heal_web_profile_junction(dsh: Path | None = None, home: Path | None = None) -> tuple[bool, str]:
    """重建 web/node_modules 联接（专治 WinError 448 陈旧装入点）。"""
    dsh = dsh or dsh_bin_path()
    home = home or dsh_home_path()
    if not dsh.is_file():
        return False, f"未找到 dsh：{dsh}"
    link = web_profile_node_modules(home)
    try:
        if _path_lexists(link):
            _remove_node_modules(link)
    except OSError as exc:
        return False, _friendly_os_error(exc)
    return link_web_profile_node_modules(dsh, home)


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
        return False, _friendly_os_error(exc)


def _bundle_resolvable(name: str, search_roots: list[Path]) -> bool:
    """profile bundle 是否能在给定 node_modules 根中解析到包目录。"""
    rels: list[str] = []
    if name.startswith("@"):
        rels.append(name)
    else:
        # 无 scope 包：常见落在根或 @deepseek-ai/
        rels.extend([name, f"@deepseek-ai/{name}"])
    for root in search_roots:
        for rel in rels:
            if _safe_child_exists(root, rel):
                return True
    return False


def sanitize_web_profile_package(home: Path, *, dsh: Path | None = None) -> tuple[bool, str]:
    """去掉无法解析的可选插件，保留官方核心 bundle，避免 dsh 启动即崩。

    WorkBuddy / 历史「dsh plugin add」常写入 dshmarket 等包；若 profile 的
    node_modules 已链到 TOA npm 安装树，这些包不在树上会导致进程秒退。
    """
    path = profile_dir_for(home) / "package.json"
    if not path.is_file():
        return True, "无 package.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, str(exc)

    search: list[Path] = []
    mods = web_profile_node_modules(home)
    if _path_lexists(mods):
        if os.name == "nt" and _is_reparse_point(mods):
            jt = _junction_target_nt(mods)
            if jt is not None:
                search.append(jt)
        if not _is_reparse_point(mods):
            search.insert(0, mods)
    if dsh is not None:
        vendored = dsh_vendored_node_modules(dsh)
        if vendored is not None:
            search.append(vendored)

    seen: set[str] = set()
    roots: list[Path] = []
    for r in search:
        key = os.path.normcase(str(r))
        if key in seen:
            continue
        seen.add(key)
        roots.append(r)

    dsh_block = data.setdefault("dsh", {})
    profile = dsh_block.setdefault("profile", {})
    raw_bundles = list(profile.get("bundles") or [])
    # 始终保留核心；其余仅保留可解析项
    kept: list[str] = []
    for core in _WEB_BUNDLES:
        if core not in kept:
            kept.append(core)
    dropped: list[str] = []
    for b in raw_bundles:
        name = str(b).strip()
        if not name or name in kept:
            continue
        if _bundle_resolvable(name, roots):
            kept.append(name)
        else:
            dropped.append(name)
    profile["bundles"] = kept

    deps = dict(data.get("dependencies") or {})
    new_deps: dict[str, Any] = {}
    for name, ver in deps.items():
        key = str(name).strip()
        if key in kept or _bundle_resolvable(key, roots):
            new_deps[key] = ver
        elif key not in dropped:
            dropped.append(key)
    data["dependencies"] = new_deps

    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return False, _friendly_os_error(exc)
    if dropped:
        return True, "已移除无法解析的插件：" + "、".join(dropped[:8])
    return True, "profile 插件列表正常"


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
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, _friendly_os_error(exc)
    init_dsh_home(home)

    try:
        if web_profile_ready(home, dsh=dsh):
            ok_san, san_msg = sanitize_web_profile_package(home, dsh=dsh)
            if ok_san and "移除" in san_msg:
                return True, san_msg
            return True, "web profile 已就绪"

        if dsh_vendored_node_modules(dsh) is None:
            ok_seed, seed_msg = seed_dsh_vendored_node_modules(dsh)
            if not ok_seed:
                logger.warning("seed dsh vendored failed: %s", seed_msg)

        ok_link, link_msg = link_web_profile_node_modules(dsh, home)
        if ok_link:
            ok_san, san_msg = sanitize_web_profile_package(home, dsh=dsh)
            if ok_san and "移除" in san_msg:
                return True, f"{link_msg}；{san_msg}"
            return True, link_msg

        # 联接可能因 448 陈旧：强制重建一次
        ok_heal, heal_msg = heal_web_profile_junction(dsh, home)
        if ok_heal:
            ok_san, san_msg = sanitize_web_profile_package(home, dsh=dsh)
            base = heal_msg or "已重建 Web 组件联接"
            if ok_san and "移除" in san_msg:
                return True, f"{base}；{san_msg}"
            return True, base

        if dsh_vendored_node_modules(dsh) is not None:
            return False, link_msg or heal_msg or "无法链接 dsh 内置 Web 组件"

        ok_add, add_msg = _run_plugin_add(node, dsh, home, timeout=timeout)
        if ok_add and web_profile_ready(home, dsh=dsh):
            sanitize_web_profile_package(home, dsh=dsh)
            return True, add_msg

        ok_link2, link_msg2 = link_web_profile_node_modules(dsh, home)
        if ok_link2:
            sanitize_web_profile_package(home, dsh=dsh)
            return True, link_msg2

        detail = add_msg if not ok_add else link_msg2
        return False, detail or link_msg or "Web 组件安装失败"
    except OSError as exc:
        logger.exception("ensure_web_profile_bundles OSError")
        if _is_winerr_untrusted(exc):
            ok_heal, heal_msg = heal_web_profile_junction(dsh, home)
            if ok_heal:
                return True, heal_msg
            return False, _friendly_os_error(exc)
        return False, _friendly_os_error(exc)


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
        return False, _friendly_os_error(exc)


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
