# -*- coding: utf-8 -*-
"""DeepSeek Harness 本地 Sidecar 配置加载。"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from services.config_service import project_root

logger = logging.getLogger("TOA3.harness_config")

_CACHE: dict | None = None
_ALIGNED_ONCE = False

# 与 config/harness.yml · packaging/shipped_config/harness.yml 同源行为默认
PRODUCT_WEB_PORT = 3082
PRODUCT_SURFACE_MODE = "embed"


def _user_harness_path() -> Path:
    try:
        from services.runtime_paths import get_user_data_root, prefer_user_writable_paths

        if prefer_user_writable_paths():
            p = get_user_data_root() / "config" / "harness.yml"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return project_root() / "data" / "user" / "harness.yml"


def is_workbuddy_home(path: str | Path) -> bool:
    text = str(path or "").replace("\\", "/")
    if not text.strip():
        return False
    lower = text.lower()
    return ("workbuddy" in lower) or ("/.workbuddy/" in lower) or lower.endswith("/.workbuddy")


def preferred_dsh_home() -> Path:
    """TOA 独立 DSH 目录（勿绑 WorkBuddy）。与 harness_setup.default_install_root 同源。"""
    return Path.home() / ".toa3" / "harness-runtime" / ".dsh"


def load_harness_config(force: bool = False) -> dict:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    merged: dict[str, Any] = {}
    path = project_root() / "config" / "harness.yml"
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            block = data.get("harness") or data
            if isinstance(block, dict):
                merged.update(block)
    user_path = _user_harness_path()
    if user_path.is_file():
        data = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            block = data.get("harness") or data
            if isinstance(block, dict):
                merged.update(block)
    _CACHE = merged
    return _CACHE


def harness_enabled() -> bool:
    return bool(load_harness_config().get("enabled", True))


def save_harness_config(updates: dict[str, Any]) -> Path:
    """写入用户 harness.yml（仅非密钥字段）。"""
    global _CACHE
    user_path = _user_harness_path()
    user_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_harness_config(force=True)
    current.update({k: v for k, v in updates.items() if v is not None})
    # 禁止把 WorkBuddy home 写回用户配置
    home = str(current.get("dsh_home") or "").strip()
    if is_workbuddy_home(home):
        current["dsh_home"] = str(preferred_dsh_home())
    user_path.write_text(
        yaml.safe_dump({"harness": current}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    _CACHE = None
    return user_path


def _copy_credentials_if_needed(old_home: Path, new_home: Path) -> None:
    src = old_home / ".credentials.yaml"
    dst = new_home / ".credentials.yaml"
    if not src.is_file() or dst.is_file():
        return
    try:
        new_home.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except OSError:
        logger.debug("copy credentials failed", exc_info=True)


def align_harness_runtime_config(*, persist: bool = True, force: bool = False) -> list[str]:
    """
    对齐正式版/开发版 Harness 行为：
    - WorkBuddy/.dsh → ~/.toa3/harness-runtime/.dsh
    - 旧发版模板把 enabled/auto_start 关掉时，若已具备 node+dsh 则恢复开启
    - 默认端口/内嵌与产品配置一致（仅在明显为旧默认时纠正）
    """
    global _ALIGNED_ONCE
    if _ALIGNED_ONCE and not force:
        return []
    _ALIGNED_ONCE = True

    cfg = dict(load_harness_config(force=True))
    notes: list[str] = []
    updates: dict[str, Any] = {}

    home_s = str(cfg.get("dsh_home") or "").strip()
    if (not home_s) or is_workbuddy_home(home_s):
        clean = preferred_dsh_home()
        if home_s and is_workbuddy_home(home_s):
            _copy_credentials_if_needed(Path(home_s), clean)
            notes.append("已将 DSH_HOME 从 WorkBuddy 迁到 TOA 独立目录")
        updates["dsh_home"] = str(clean)
        cfg["dsh_home"] = str(clean)

    node_ok = Path(str(cfg.get("node_exe") or "")).is_file()
    dsh_ok = Path(str(cfg.get("dsh_bin") or "")).is_file()
    if node_ok and dsh_ok:
        if not bool(cfg.get("enabled", True)):
            updates["enabled"] = True
            notes.append("已恢复启用编码智能体（正式版与开发版对齐）")
        if not bool(cfg.get("auto_start", True)):
            updates["auto_start"] = True
            notes.append("已恢复进页自动启动")

    # 旧发版模板：3081 + 内嵌；产品默认 3082 + 浏览器优先（doc 33 / C-11）
    try:
        port = int(cfg.get("web_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if port in (0, 3081) and (is_workbuddy_home(home_s) or not home_s or updates.get("dsh_home")):
        updates["web_port"] = PRODUCT_WEB_PORT
        notes.append(f"Web 端口对齐为 {PRODUCT_WEB_PORT}")

    mode = str(cfg.get("surface_mode") or "").strip().lower()
    migrating_home = bool(is_workbuddy_home(home_s) or updates.get("dsh_home"))
    if mode not in ("embed", "browser"):
        updates["surface_mode"] = PRODUCT_SURFACE_MODE
        notes.append("显示方式对齐为套件内嵌")
    # 用户已选 embed/browser 时一律保留；禁止安装/修复把内嵌改回浏览器

    if updates and persist:
        save_harness_config(updates)
        load_harness_config(force=True)
        if notes:
            logger.info("Harness 配置已对齐: %s", "; ".join(notes))
    return notes


def resolve_harness_path(key: str, default: str = "") -> Path:
    raw = str(load_harness_config().get(key) or default).strip()
    if not raw:
        return Path()
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    try:
        return p.resolve()
    except OSError:
        return p


def web_url() -> str:
    port = int(load_harness_config().get("web_port") or PRODUCT_WEB_PORT)
    return f"http://127.0.0.1:{port}"


def dshm_script_path() -> Path:
    return resolve_harness_path("dshm_script", "vendor/dshm/bin/dshm.js")


def node_exe_path() -> Path:
    return resolve_harness_path("node_exe", "")


def dsh_bin_path() -> Path:
    return resolve_harness_path("dsh_bin", "")


def dsh_home_path() -> Path:
    raw = resolve_harness_path("dsh_home", "")
    if raw and not is_workbuddy_home(raw):
        return raw
    return preferred_dsh_home()
