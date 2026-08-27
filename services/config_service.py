# -*- coding: utf-8 -*-
"""配置加载（TOA3 独立路径，对齐 TOA2 字段名）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from core.exceptions import ConfigError

ROOT = Path(__file__).resolve().parents[1]
_CONFIG_CACHE: dict | None = None
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _bundle_root() -> Path:
    """打包资源根（开发=仓库根；冻结=PyInstaller bundle / _MEIPASS）。"""
    try:
        from services.runtime_paths import get_bundle_root, is_frozen

        if is_frozen():
            return get_bundle_root()
    except Exception:
        pass
    return ROOT


def project_root() -> Path:
    return _bundle_root()


def _config_roots() -> list[Path]:
    """配置查找顺序：bundle → 安装目录（Inno 复制到 exe 旁）。"""
    roots = [_bundle_root()]
    try:
        from services.runtime_paths import get_app_root, is_frozen

        if is_frozen():
            app_root = get_app_root()
            if app_root not in roots:
                roots.append(app_root)
    except Exception:
        pass
    if _bundle_root() == ROOT and ROOT not in roots:
        return [ROOT]
    return roots


def _user_config_path() -> Path | None:
    """用户可写配置（冻结 / Program Files 安装时映射到 LOCALAPPDATA）。"""
    try:
        from services.runtime_paths import get_user_data_root, prefer_user_writable_paths

        if prefer_user_writable_paths():
            p = get_user_data_root() / "config" / "user_app.yml"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return None


def _ensure_user_config(path: Path) -> None:
    if path.is_file():
        return
    path.write_text("{}\n", encoding="utf-8")


def _resolve_env() -> str:
    explicit = os.environ.get("TOA_ENV", "").strip().lower()
    if explicit:
        return explicit
    try:
        from services.runtime_paths import get_runtime_environment

        return get_runtime_environment()
    except Exception:
        return "development"


def _config_files() -> list[Path]:
    env = _resolve_env()
    files: list[Path] = []
    for root in _config_roots():
        base = root / "config" / "app.yml"
        if base.is_file() and base not in files:
            files.append(base)
    for root in _config_roots():
        if env in ("dev", "development"):
            dev = root / "config" / "app.dev.yml"
            if dev.is_file() and dev not in files:
                files.append(dev)
        elif env == "release":
            rel = root / "config" / "app.release.yml"
            if rel.is_file() and rel not in files:
                files.append(rel)
    user_cfg = _user_config_path()
    if user_cfg is not None and user_cfg.is_file() and user_cfg not in files:
        files.append(user_cfg)
    if not files:
        files.append(_bundle_root() / "config" / "app.yml")
    return files


def writable_config_path() -> Path:
    """当前环境用户可写的配置文件（主题等 UI 偏好写入此处）。"""
    user_cfg = _user_config_path()
    if user_cfg is not None:
        _ensure_user_config(user_cfg)
        return user_cfg
    env = _resolve_env()
    if env in ("dev", "development"):
        dev = ROOT / "config" / "app.dev.yml"
        if dev.is_file():
            return dev
    elif env == "release":
        for root in _config_roots():
            rel = root / "config" / "app.release.yml"
            if rel.is_file():
                return rel
    return ROOT / "config" / "app.yml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(force: bool = False) -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force:
        return _CONFIG_CACHE
    merged: dict = {}
    for path in _config_files():
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                merged = _deep_merge(merged, data)
        except Exception as e:
            raise ConfigError(f"无法加载配置 {path}: {e}")
    if not merged:
        raise ConfigError("未找到有效配置文件 config/app.yml")
    _CONFIG_CACHE = merged
    return merged


def _expand_placeholders(value: str) -> str:
    root = str(project_root())
    temp = str(project_root() / "cache")
    mapping = {"base_dir": root, "temp_dir": temp}

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return mapping.get(key, m.group(0))

    return _PLACEHOLDER_RE.sub(repl, value)


def get_path_config() -> dict[str, Any]:
    cfg = load_config()
    merged: dict[str, Any] = {}
    for bucket in ("path", "data_paths"):
        block = cfg.get(bucket)
        if isinstance(block, dict):
            merged.update(block)
    paths = cfg.get("paths")
    if isinstance(paths, dict):
        merged.update(paths)
    try:
        from services.runtime_paths import apply_writable_path_overrides

        merged = apply_writable_path_overrides(merged)
    except Exception:
        pass
    return merged


def resolve_path(key: str) -> Path:
    pc = get_path_config()
    raw = pc.get(key)
    if raw is None:
        defaults = {
            "data_dir": "./data",
            "log_dir": "./common/logs",
            "output_dir": "./output",
            "docs_dir": "./docs",
            "images_dir": "./images",
            "license_file": "./config/license.json",
            "template_dir": "./templates",
        }
        raw = defaults.get(key)
    if raw is None:
        raise ConfigError(f"路径配置缺失: {key}")
    text = _expand_placeholders(str(raw))
    p = Path(text)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def get_menu_items() -> list[dict]:
    items = get_all_menu_items()
    visible = [i for i in items if i.get("show", True)]
    return visible


def get_all_menu_items() -> list[dict]:
    """优先 data/user/menu.yml（用户可维护），否则 app.yml。"""
    user_path = user_menu_path()
    if user_path.is_file():
        try:
            doc = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
            items = doc.get("menu_items") if isinstance(doc, dict) else None
            if isinstance(items, list) and items:
                out = [i for i in items if isinstance(i, dict)]
                out.sort(key=lambda x: int(x.get("order") or 0))
                return out
        except Exception:
            pass
    cfg = load_config()
    menu = cfg.get("menu") or {}
    items = [i for i in (menu.get("menu_items") or []) if isinstance(i, dict)]
    items.sort(key=lambda x: int(x.get("order") or 0))
    return items


def get_menu_item_by_id(module_id: str) -> dict | None:
    for item in get_all_menu_items():
        if str(item.get("id") or "") == module_id:
            return item
    return None


def user_menu_path() -> Path:
    path = resolve_path("data_dir") / "user" / "menu.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_menu_items(items: list[dict]) -> Path:
    """保存用户菜单到 data/user/menu.yml，立即刷新配置缓存。"""
    cleaned: list[dict] = []
    for i, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["order"] = int(item.get("order") or (i + 1))
        if "show" not in item:
            item["show"] = True
        cleaned.append(item)
    cleaned.sort(key=lambda x: int(x.get("order") or 0))
    path = user_menu_path()
    payload = {
        "menu_items": cleaned,
        "_note": "用户菜单覆盖；删除本文件可恢复 app.yml 默认菜单。",
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
    return path


def reset_user_menu() -> bool:
    """删除用户菜单覆盖，恢复 app.yml。"""
    path = user_menu_path()
    if path.is_file():
        path.unlink()
        global _CONFIG_CACHE
        _CONFIG_CACHE = None
        return True
    return False


def get_ui_config() -> dict:
    cfg = load_config()
    ui = dict(cfg.get("ui") or {})
    window = dict(cfg.get("window") or {})
    for k in ("window_title", "default_size", "min_size", "default_start_tab", "default_fullscreen"):
        if window.get(k) is not None:
            ui[k] = window[k]
    theme = window.get("theme") or ui.get("theme")
    if theme:
        ui["theme"] = theme
    return ui


def get_auth_config() -> dict:
    cfg = load_config()
    return dict(cfg.get("auth") or {})


def get_log_config() -> dict:
    cfg = load_config()
    return dict(cfg.get("log_config") or {})


def get_hotkeys_config() -> dict:
    cfg = load_config()
    return dict(cfg.get("hotkeys") or {})


def get_license_config() -> dict:
    cfg = load_config()
    return dict(cfg.get("license") or {})


def get_update_config() -> dict:
    cfg = load_config()
    return dict(cfg.get("update") or {})


def save_hotkeys_config(patch: dict) -> None:
    path = writable_config_path()
    _ensure_user_config(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    hotkeys = dict(data.get("hotkeys") or {})
    hotkeys.update(patch)
    data["hotkeys"] = hotkeys
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


def save_ui_theme(theme_id: str) -> None:
    """写入当前环境可编辑配置文件（不破坏 app.yml 全量结构）。"""
    path = writable_config_path()
    _ensure_user_config(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    window = dict(data.get("window") or {})
    window["theme"] = theme_id
    data["window"] = window
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
