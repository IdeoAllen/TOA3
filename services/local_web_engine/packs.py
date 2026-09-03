# -*- coding: utf-8 -*-
"""引擎宿主扩展包（engine pack）。

与业务插件（surface=qt/webview）并列的第三种扩展面：
只托管「本机开源 Web UI」的安装 / 启停 / 内嵌，不改 Guest 业务能力。

落盘：
  data/user/engine_packs/<id>/engine.toml
  assets/samples/engine_packs/<id>/engine.toml
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore

from services.config_service import project_root, resolve_path

logger = logging.getLogger("TOA3.local_web_engine.packs")


def engine_packs_user_root() -> Path:
    return resolve_path("data_dir") / "user" / "engine_packs"


def engine_packs_sample_root() -> Path:
    return project_root() / "assets" / "samples" / "engine_packs"


def _read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("读取引擎包失败 %s: %s", path, exc)
        return {}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("读取引擎包失败 %s: %s", path, exc)
        return {}


def _iter_pack_dirs() -> list[Path]:
    out: list[Path] = []
    for root in (engine_packs_user_root(), engine_packs_sample_root()):
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and (
                (child / "engine.toml").is_file() or (child / "engine.yml").is_file()
            ):
                out.append(child)
    return out


def load_pack_engine_configs() -> dict[str, dict[str, Any]]:
    """返回 {engine_id: cfg_dict}，可直接并入 local_web_engines engines 块。"""
    result: dict[str, dict[str, Any]] = {}
    for pack_dir in _iter_pack_dirs():
        toml_path = pack_dir / "engine.toml"
        yml_path = pack_dir / "engine.yml"
        raw = _read_toml(toml_path) if toml_path.is_file() else _read_yaml(yml_path)
        eng = raw.get("engine") if isinstance(raw.get("engine"), dict) else raw
        if not isinstance(eng, dict):
            continue
        eid = str(eng.get("id") or pack_dir.name).strip()
        if not eid:
            continue
        cfg = dict(eng)
        cfg.pop("id", None)
        roots = [str(x) for x in (cfg.get("default_roots") or [])]
        local_app = pack_dir / "app"
        if local_app.is_dir():
            roots = [str(local_app), *roots]
        cfg["default_roots"] = roots
        cfg.setdefault("menu_show", True)
        cfg["_pack_dir"] = str(pack_dir)
        cfg["_from_pack"] = True
        result[eid] = cfg
    return result


_BUILTIN_ENGINE_IDS = frozenset({"open_pencil", "drawio_web", "comfyui_web", "harness_agent"})


def is_engine_pack(engine_id: str) -> bool:
    eid = str(engine_id or "").strip()
    if not eid or eid in _BUILTIN_ENGINE_IDS:
        return False
    return eid in load_pack_engine_configs()


def engine_pack_menu_items() -> list[dict[str, Any]]:
    """用户/样例引擎包 → 顶栏「引擎」侧栏（不覆盖内置同 id）。"""
    items: list[dict[str, Any]] = []
    for eid, cfg in load_pack_engine_configs().items():
        if eid in _BUILTIN_ENGINE_IDS:
            continue
        if not bool(cfg.get("menu_show", True)):
            continue
        items.append(
            {
                "id": eid,
                "name": str(cfg.get("title") or eid),
                "desc": str(cfg.get("description") or "引擎宿主扩展包 · 安装/启停/内嵌"),
                "group": "engines",
                "icon": str(cfg.get("icon") or "image_creator"),
                "order": int(cfg.get("order") or 80),
                "show": True,
                "feature_id": eid,
                "requires_license": False,
                "source": "engine_pack",
                "module_path": "modules.local_web_host.engine_pack_page",
                "class_name": "EnginePackPage",
            }
        )
    return items
