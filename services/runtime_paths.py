# -*- coding: utf-8 -*-
"""运行时路径：开发 / 打包环境解析 + 用户可写目录。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_APP_DATA_DIRNAME = "YCZH-TOA3"

_WRITABLE_PATH_KEYS = (
    "log_dir",
    "output_dir",
    "data_dir",
    "license_file",
    "user_config_file",
    "knowledge_base",
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_app_root() -> Path:
    """应用根：开发时为项目根，打包后为 exe 所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def get_bundle_root() -> Path:
    """打包资源根：onefile 时为 _MEIPASS。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", str(get_app_root())))
    return get_app_root()


def get_runtime_environment() -> str:
    return "release" if is_frozen() else "development"


def get_user_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / _APP_DATA_DIRNAME


def get_user_logs_dir() -> Path:
    return get_user_data_root() / "logs"


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _under_program_files(path: str | Path) -> bool:
    p = _norm(path)
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        v = os.environ.get(key)
        if not v:
            continue
        root = _norm(v)
        if p == root or p.startswith(root + os.sep):
            return True
    return False


def prefer_user_writable_paths() -> bool:
    if is_frozen():
        return True
    try:
        if _under_program_files(os.getcwd()):
            return True
        if _under_program_files(get_app_root()):
            return True
    except Exception:
        pass
    return False


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def can_write_dir(path: str | Path) -> bool:
    try:
        target = ensure_dir(path)
        probe = target / ".toa3_write_probe"
        probe.write_text("1", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _remap_one(value: str, key: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return raw
    if os.path.isabs(raw) and not _under_program_files(raw):
        return raw

    root = get_user_data_root()
    if key == "log_dir":
        return str(root / "logs")
    if key == "output_dir":
        return str(root / "output")
    if key == "data_dir":
        return str(root / "data")
    if key == "license_file":
        return str(root / "config" / "license.json")
    if key == "user_config_file":
        return str(root / "config" / "user_app.yml")
    if key == "knowledge_base":
        return str(root / "data" / "knowledge_base.json")
    return str(root / os.path.basename(raw.replace("\\", "/")))


def apply_writable_path_overrides(path_config: dict[str, Any] | None) -> dict[str, Any]:
    """冻结或 Program Files 安装时，将可写路径映射到 %LOCALAPPDATA%\\YCZH-TOA3。"""
    cfg = dict(path_config or {})
    force = prefer_user_writable_paths()
    if not force:
        log_dir = str(cfg.get("log_dir") or "").strip()
        if log_dir:
            abs_log = os.path.abspath(log_dir)
            if not _under_program_files(abs_log) and can_write_dir(abs_log):
                return cfg
        else:
            return cfg

    for key in _WRITABLE_PATH_KEYS:
        if key in cfg and cfg[key]:
            cfg[key] = _remap_one(str(cfg[key]), key)

    for key in ("log_dir", "output_dir", "data_dir"):
        p = cfg.get(key)
        if p:
            try:
                ensure_dir(str(p))
            except Exception:
                pass
    for key in ("license_file", "user_config_file", "knowledge_base"):
        p = cfg.get(key)
        if p:
            try:
                ensure_dir(Path(str(p)).parent)
            except Exception:
                pass
    return cfg


def resolve_log_root(configured: str | None = None) -> Path:
    user_logs = get_user_logs_dir()
    if prefer_user_writable_paths():
        return ensure_dir(user_logs)

    cfg = (configured or "").strip()
    if cfg:
        target = Path(cfg).resolve()
        if can_write_dir(target):
            return target
        return ensure_dir(user_logs)

    fallback = get_app_root() / "common" / "logs"
    if can_write_dir(fallback):
        return fallback
    return ensure_dir(user_logs)
