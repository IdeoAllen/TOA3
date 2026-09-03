# -*- coding: utf-8 -*-
"""本地 Web 引擎一键安装（git clone + 可选 post_install）。"""
from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("TOA3.local_web_engine.install")

ProgressCb = Callable[[str, int], None]


def preferred_install_root(engine_id: str) -> Path | None:
    from services.local_web_engine import _expand, get_spec

    spec = get_spec(engine_id)
    if spec is None:
        return None
    for r in spec.default_roots:
        p = _expand(r)
        if p.parts:
            return p
    return None


def can_one_click_install(engine_id: str) -> bool:
    from services.local_web_engine import get_spec

    spec = get_spec(engine_id)
    return bool(spec and str(spec.install_git or "").strip())


def install_engine(
    engine_id: str,
    *,
    on_progress: ProgressCb | None = None,
) -> tuple[bool, str]:
    """一键安装到 default_roots[0]；返回 (ok, msg)。可在后台线程调用。"""
    from services.local_web_engine import (
        _normalize_install_root,
        _which,
        discover_root,
        get_spec,
        load_specs,
        save_user_root,
    )

    load_specs(force=True)
    spec = get_spec(engine_id)
    if spec is None:
        return False, "未知引擎"

    def prog(msg: str, pct: int) -> None:
        if on_progress:
            try:
                on_progress(msg, max(0, min(100, int(pct))))
            except Exception:
                pass

    existing = discover_root(engine_id)
    if existing is not None:
        prog("已安装", 100)
        return True, f"已安装：{existing}"

    git_url = str(spec.install_git or "").strip()
    if not git_url:
        hint = str(spec.install_hint or "").strip()
        return (
            False,
            hint
            or "本引擎不支持一键下载，请点「指定目录」选择已安装根目录。",
        )

    target = preferred_install_root(engine_id)
    if target is None:
        return False, "未配置默认安装路径"

    git = _which("git")
    if git is None:
        return False, "未找到 git。请先安装 Git 后再一键安装。"

    prog(f"准备目录 {target}", 5)
    try:
        if target.exists() and any(target.iterdir()):
            found = _normalize_install_root(target, spec.marker_files)
            if found is not None:
                save_user_root(engine_id, found)
                prog("已安装", 100)
                return True, f"已安装：{found}"
            return (
                False,
                f"目录非空且不是有效安装：{target}\n请清空后重试，或点「指定目录」。",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            cwd = str(target)
            args = [git, "clone", "--depth", "1", "--single-branch", git_url, "."]
        else:
            cwd = str(target.parent)
            args = [git, "clone", "--depth", "1", "--single-branch", git_url, target.name]
    except OSError as exc:
        return False, str(exc)

    prog("正在下载源码…", 15)
    proc = None
    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        assert proc.stdout is not None
        lines = 0
        for line in proc.stdout:
            lines += 1
            if lines % 8 == 0:
                prog(line.strip()[:80] or "下载中…", min(70, 15 + lines))
        code = proc.wait(timeout=600)
        if code != 0:
            return False, f"git clone 失败（exit {code}）"
    except subprocess.TimeoutExpired:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return False, "下载超时，请检查网络后重试"
    except OSError as exc:
        return False, str(exc)

    root = _normalize_install_root(target, spec.marker_files) or target
    post = list(spec.post_install or [])
    total_post = len(post)
    for i, argv in enumerate(post):
        if not argv:
            continue
        exe = _which(argv[0])
        if exe is None:
            prog(f"跳过依赖命令（未找到 {argv[0]}）", 75 + i * 5)
            continue
        cmd = [exe, *argv[1:]]
        pct = 75 + int(20 * (i + 1) / max(1, total_post))
        prog(f"安装依赖：{' '.join(argv[:3])}…", pct)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "")[-400:]
                logger.warning("post_install 失败 %s: %s", cmd, err)
                continue
            break
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("post_install 异常 %s: %s", cmd, exc)
            continue

    if _normalize_install_root(root, spec.marker_files) is None:
        return False, f"下载完成但缺少标记文件：{spec.marker_files}"

    save_user_root(engine_id, root)
    load_specs(force=True)
    prog("安装完成", 100)
    return True, f"已安装到 {root}"
