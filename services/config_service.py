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


def _default_menu_items_from_app() -> list[dict]:
    """app.yml 菜单真相源（未合并用户覆盖）。"""
    cfg = load_config()
    menu = cfg.get("menu") or {}
    items = [dict(i) for i in (menu.get("menu_items") or []) if isinstance(i, dict)]
    items.sort(key=lambda x: int(x.get("order") or 0))
    return items


_USER_MENU_OVERRIDE_KEYS = frozenset({"show", "order", "group", "name", "desc", "icon", "sidebar"})


def _merge_menu_with_user_overrides(
    base_items: list[dict],
    user_items: list[dict],
) -> list[dict]:
    """以 app.yml 为基准，按 id 合并用户可维护字段；新项自动出现，已删项移除。"""
    override_by_id: dict[str, dict] = {}
    for raw in user_items:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("id") or "").strip()
        if mid:
            override_by_id[mid] = raw

    base_ids: set[str] = set()
    merged: list[dict] = []
    for base_item in base_items:
        mid = str(base_item.get("id") or "").strip()
        if not mid:
            continue
        base_ids.add(mid)
        item = dict(base_item)
        override = override_by_id.get(mid)
        if override:
            for key in _USER_MENU_OVERRIDE_KEYS:
                if key in override and override[key] is not None:
                    item[key] = override[key]
        merged.append(item)

    for mid, override in override_by_id.items():
        if mid not in base_ids:
            merged.append(dict(override))

    merged.sort(key=lambda x: int(x.get("order") or 0))
    return merged


def _apply_overrides_map(
    base_items: list[dict],
    overrides: dict[str, Any],
) -> list[dict]:
    """把 overrides[id] 中的可维护字段套到 app.yml 基准项上。"""
    override_by_id: dict[str, dict] = {}
    for raw_id, raw in overrides.items():
        mid = str(raw_id or "").strip()
        if not mid or not isinstance(raw, dict):
            continue
        override_by_id[mid] = raw

    base_ids: set[str] = set()
    merged: list[dict] = []
    for base_item in base_items:
        mid = str(base_item.get("id") or "").strip()
        if not mid:
            continue
        base_ids.add(mid)
        item = dict(base_item)
        override = override_by_id.get(mid)
        if override:
            for key in _USER_MENU_OVERRIDE_KEYS:
                if key in override and override[key] is not None:
                    item[key] = override[key]
        merged.append(item)

    for mid, override in override_by_id.items():
        if mid not in base_ids:
            merged.append(dict(override))

    merged.sort(key=lambda x: int(x.get("order") or 0))
    return merged


def _merged_to_overrides_map(base_items: list[dict], merged_items: list[dict]) -> dict[str, dict]:
    base_by_id = {str(i.get("id") or ""): i for i in base_items if i.get("id")}
    out: dict[str, dict] = {}
    for raw in merged_items:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("id") or "").strip()
        if not mid:
            continue
        base = base_by_id.get(mid)
        if base is not None:
            delta = _menu_item_override_delta(base, raw)
            if delta:
                out[mid] = {k: delta[k] for k in delta if k != "id"}
        else:
            entry = {k: raw[k] for k in _USER_MENU_OVERRIDE_KEYS if k in raw}
            if entry:
                out[mid] = entry
    return out


def _read_user_menu_doc() -> dict:
    path = user_menu_path()
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def get_user_group_label_overrides() -> dict[str, str]:
    gl = _read_user_menu_doc().get("group_labels")
    if not isinstance(gl, dict):
        return {}
    out: dict[str, str] = {}
    for raw_id, raw_name in gl.items():
        gid = str(raw_id or "").strip().lower()
        name = str(raw_name or "").strip()
        if gid and name:
            out[gid] = name
    return out


def get_group_labels() -> dict[str, str]:
    """顶栏/侧栏子模块展示名（出厂默认 + 用户覆盖）。"""
    from services.menu_registry import DOMAIN_TAB_LABELS

    labels = dict(DOMAIN_TAB_LABELS)
    labels.update(get_user_group_label_overrides())
    return labels


def _group_labels_delta(group_labels: dict[str, str] | None) -> dict[str, str]:
    from services.menu_registry import DOMAIN_TAB_LABELS, GROUP_ORDER

    if not group_labels:
        return {}
    out: dict[str, str] = {}
    for gid in GROUP_ORDER:
        name = str(group_labels.get(gid) or "").strip()
        default = str(DOMAIN_TAB_LABELS.get(gid) or "").strip()
        if name and name != default:
            out[gid] = name
    return out


def _write_menu_user_file(
    overrides_map: dict[str, dict],
    group_labels_map: dict[str, str],
) -> Path:
    """写入本机菜单调整（模块 overrides + 子模块名）。"""
    global _CONFIG_CACHE
    path = user_menu_path()
    if not overrides_map and not group_labels_map:
        if path.is_file():
            path.unlink()
        _CONFIG_CACHE = None
        return path
    payload: dict[str, Any] = {
        "_note": "本机菜单调整；删本文件或「恢复默认」= 出厂菜单。",
    }
    if overrides_map:
        payload["overrides"] = overrides_map
    if group_labels_map:
        payload["group_labels"] = group_labels_map
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    _CONFIG_CACHE = None
    return path


def _migrate_legacy_menu_file(base: list[dict], doc: dict) -> list[dict] | None:
    """旧 menu_items 列表 → 合并后自动压成 overrides 格式。"""
    items = doc.get("menu_items")
    if not isinstance(items, list) or not items:
        return None
    user_items = [i for i in items if isinstance(i, dict)]
    if not user_items:
        return None
    merged = _merge_menu_with_user_overrides(base, user_items)
    overrides_map = _merged_to_overrides_map(base, merged)
    gl_map: dict[str, str] = {}
    raw_gl = doc.get("group_labels")
    if isinstance(raw_gl, dict):
        for raw_id, raw_name in raw_gl.items():
            gid = str(raw_id or "").strip().lower()
            name = str(raw_name or "").strip()
            if gid and name:
                gl_map[gid] = name
    _write_menu_user_file(overrides_map, gl_map)
    return merged


def _menu_item_override_delta(base: dict, item: dict) -> dict | None:
    """相对 app.yml 的用户差异；无差异则 None。"""
    mid = str(item.get("id") or "").strip()
    if not mid:
        return None
    delta: dict[str, Any] = {"id": mid}
    for key in _USER_MENU_OVERRIDE_KEYS:
        if key in item and item.get(key) != base.get(key):
            delta[key] = item[key]
    return delta if len(delta) > 1 else None


def get_menu_items() -> list[dict]:
    items = get_all_menu_items()
    visible = [i for i in items if i.get("show", True)]
    return visible


def get_all_menu_items() -> list[dict]:
    """出厂菜单 app.yml + 本机 menu.yml 里的 overrides（有改动的项）。"""
    base = _default_menu_items_from_app()
    doc = _read_user_menu_doc()
    if not doc:
        return base
    try:
        raw_overrides = doc.get("overrides")
        if isinstance(raw_overrides, dict) and raw_overrides:
            return _apply_overrides_map(base, raw_overrides)
        migrated = _migrate_legacy_menu_file(base, doc)
        if migrated is not None:
            return migrated
        if doc.get("group_labels"):
            return base
    except Exception:
        pass
    return base


def get_menu_item_by_id(module_id: str) -> dict | None:
    for item in get_all_menu_items():
        if str(item.get("id") or "") == module_id:
            return item
    return None


def user_menu_path() -> Path:
    path = resolve_path("data_dir") / "user" / "menu.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_menu_items(
    items: list[dict],
    *,
    group_labels: dict[str, str] | None = None,
) -> Path:
    """保存本机菜单调整（模块差异 + 子模块名）。"""
    base = _default_menu_items_from_app()
    overrides_map = _merged_to_overrides_map(base, items)
    gl_delta = _group_labels_delta(group_labels)
    return _write_menu_user_file(overrides_map, gl_delta)


def reset_user_menu() -> bool:
    """删除用户菜单覆盖，恢复 app.yml。"""
    global _CONFIG_CACHE
    path = user_menu_path()
    if path.is_file():
        path.unlink()
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
