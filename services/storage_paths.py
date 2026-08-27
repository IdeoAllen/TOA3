# -*- coding: utf-8 -*-
"""结构化存储路径服务（模板 / 示例 / 模块数据 / 生成输出）。"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from core.exceptions import ConfigError
from services.config_service import project_root, resolve_path

logger = logging.getLogger(__name__)

_STORAGE_CACHE: dict | None = None


def _load_storage_config(force: bool = False) -> dict:
    global _STORAGE_CACHE
    if _STORAGE_CACHE is not None and not force:
        return _STORAGE_CACHE
    path = project_root() / "config" / "storage.yml"
    if not path.is_file():
        _STORAGE_CACHE = {}
        return _STORAGE_CACHE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _STORAGE_CACHE = data if isinstance(data, dict) else {}
    return _STORAGE_CACHE


def bundled_root() -> Path:
    cfg = _load_storage_config()
    rel = str((cfg.get("roots") or {}).get("bundled") or "assets")
    p = Path(rel)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def data_root() -> Path:
    return resolve_path("data_dir")


def output_root() -> Path:
    return resolve_path("output_dir")


def cache_root() -> Path:
    cfg = _load_storage_config()
    rel = str((cfg.get("roots") or {}).get("cache") or "./cache")
    p = Path(rel)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def _layout(key: str, default: str) -> str:
    cfg = _load_storage_config()
    layout = cfg.get("layout") or {}
    return str(layout.get(key) or default)


def bundled_templates_dir() -> Path:
    return bundled_root() / _layout("templates_bundled", "templates")


def bundled_samples_dir() -> Path:
    return bundled_root() / _layout("samples", "samples")


def user_templates_dir() -> Path:
    return data_root() / _layout("user_templates", "user/templates")


def module_data_dir(module_id: str, *, create: bool = False) -> Path:
    base = data_root() / _layout("module_data", "module") / module_id
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base


def shared_data_dir(*, create: bool = False) -> Path:
    base = data_root() / _layout("shared_data", "shared")
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base


def module_output_dir(module_id: str, *, create: bool = False) -> Path:
    pattern = _layout("module_output_pattern", "{module_id}/{yyyy_mm}")
    yyyy_mm = date.today().strftime("%Y-%m")
    sub = pattern.replace("{module_id}", module_id).replace("{yyyy_mm}", yyyy_mm)
    base = output_root() / sub
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base


def bundled_template(rel_path: str) -> Path:
    """随包模板：assets/templates/<rel_path>"""
    return bundled_templates_dir() / rel_path.replace("\\", "/")


def bundled_sample(rel_path: str) -> Path:
    """随包示例：assets/samples/<rel_path>"""
    return bundled_samples_dir() / rel_path.replace("\\", "/")


def user_template(rel_path: str) -> Path:
    return user_templates_dir() / rel_path.replace("\\", "/")


def resolve_template(rel_path: str) -> Path:
    """
    解析模板路径：优先用户覆盖 → 随包资源 → 项目根相对路径（兼容 app.yml）。
    """
    rel = rel_path.replace("\\", "/").strip()
    if not rel:
        raise ConfigError("模板路径为空")

    candidates = [
        user_template(rel),
        bundled_template(rel),
        project_root() / rel,
    ]
    for p in candidates:
        if p.is_file():
            return p.resolve()

    # 遗留键映射
    cfg = _load_storage_config()
    legacy = cfg.get("legacy_template_keys") or {}
    mapped = legacy.get(rel)
    if mapped:
        return resolve_template(str(mapped))

    raise ConfigError(f"模板不存在: {rel}（已查 user/templates、bundled、项目根）")


def resolve_legacy_template_key(key: str) -> Path:
    """app.yml 键名 → 模板文件（如 resume_template）。"""
    cfg = _load_storage_config()
    legacy = cfg.get("legacy_template_keys") or {}
    rel = legacy.get(key)
    if not rel:
        from services.config_service import get_path_config

        pc = get_path_config()
        raw = pc.get(key)
        if raw:
            return resolve_template(str(raw))
        raise ConfigError(f"未登记模板键: {key}")
    return resolve_template(str(rel))


def module_manifest(module_id: str) -> dict[str, Any]:
    cfg = _load_storage_config()
    modules = cfg.get("modules") or {}
    entry = modules.get(module_id)
    return dict(entry) if isinstance(entry, dict) else {}


def list_module_samples(module_id: str) -> list[Path]:
    manifest = module_manifest(module_id)
    out: list[Path] = []
    for rel in manifest.get("samples") or []:
        p = bundled_sample(str(rel))
        if p.is_file():
            out.append(p)
    return out


def list_module_templates(module_id: str) -> list[Path]:
    manifest = module_manifest(module_id)
    out: list[Path] = []
    for rel in manifest.get("templates") or []:
        try:
            out.append(resolve_template(str(rel)))
        except ConfigError:
            p = bundled_template(str(rel))
            if p.is_file():
                out.append(p)
    return out


def ensure_storage_tree() -> None:
    """创建标准目录树（不含大文件）。"""
    dirs = [
        bundled_templates_dir() / "business",
        bundled_templates_dir() / "deliverables",
        bundled_templates_dir() / "generators",
        bundled_samples_dir() / "modules",
        user_templates_dir(),
        module_data_dir("_placeholder", create=True),
        shared_data_dir(create=True),
        output_root(),
        cache_root(),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    # 移除占位模块目录名，仅保留 module 根
    placeholder = module_data_dir("_placeholder")
    if placeholder.is_dir() and not any(placeholder.iterdir()):
        try:
            placeholder.rmdir()
        except OSError:
            pass
    logger.debug("存储目录树已就绪: data=%s output=%s", data_root(), output_root())
