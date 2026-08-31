# -*- coding: utf-8 -*-
"""工作场景样例：只读 assets/samples/scenarios → 复制为我的扩展。"""
from __future__ import annotations

import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from services.config_service import project_root
from services.extension_lifecycle import LIFE_SCAFFOLD, set_lifecycle
from services.menu_registry import MIGRATED_MODULES
from services.notify_bus import request_nav_rebuild
from services.plugin_pack import parse_plugin_root
from services.plugin_registry import register_plugin
from services.plugin_sandbox import default_plugin_root
from services.plugin_scaffold import suggest_plugin_id

logger = logging.getLogger(__name__)


@dataclass
class ScenarioInfo:
    scenario_id: str
    name: str
    description: str
    root: Path


def scenarios_root() -> Path:
    return project_root() / "assets" / "samples" / "scenarios"


def list_scenarios() -> list[ScenarioInfo]:
    root = scenarios_root()
    if not root.is_dir():
        return []
    out: list[ScenarioInfo] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or not (child / "plugin.toml").is_file():
            continue
        try:
            man = parse_plugin_root(child)
        except Exception as exc:
            logger.debug("skip scenario %s: %s", child, exc)
            continue
        desc = ""
        try:
            import tomllib

            raw = tomllib.loads((child / "plugin.toml").read_text(encoding="utf-8"))
            desc = str((raw.get("plugin") or {}).get("description") or "")
        except Exception:
            pass
        out.append(
            ScenarioInfo(
                scenario_id=child.name,
                name=man.name,
                description=desc or man.name,
                root=child,
            )
        )
    return out


def _pascal(plugin_id: str) -> str:
    return "".join(p.capitalize() for p in plugin_id.split("_") if p) + "Page"


def _unique_plugin_id(preferred: str, *, avoid: str) -> str:
    pid = preferred
    if not pid or pid in MIGRATED_MODULES or pid == avoid:
        pid = f"ext_{int(time.time()) % 1_000_000}"
    dest = default_plugin_root(pid)
    if dest.exists() or pid in MIGRATED_MODULES:
        pid = f"ext_{int(time.time()) % 1_000_000}"
    return pid


def _rewrite_identity(root: Path, *, old_id: str, new_id: str, name: str) -> None:
    toml_path = root / "plugin.toml"
    text = toml_path.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^id\s*=\s*".*"', f'id = "{new_id}"', text, count=1)
    text = re.sub(r'(?m)^name\s*=\s*".*"', f'name = "{name}"', text, count=1)
    text = re.sub(
        r'(?m)^module_path\s*=\s*".*"',
        f'module_path = "modules.{new_id}.{new_id}_page"',
        text,
        count=1,
    )
    text = re.sub(
        r'(?m)^class_name\s*=\s*".*"',
        f'class_name = "{_pascal(new_id)}"',
        text,
        count=1,
    )
    text = re.sub(r'(?m)^page_id\s*=\s*".*"', f'page_id = "{new_id}"', text, count=1)
    text = re.sub(r'(?m)^data_key\s*=\s*".*"', f'data_key = "{new_id}"', text, count=1)
    toml_path.write_text(text, encoding="utf-8")

    old_pkg = root / "modules" / old_id
    new_pkg = root / "modules" / new_id
    if old_pkg.is_dir() and old_id != new_id:
        if new_pkg.exists():
            shutil.rmtree(new_pkg, ignore_errors=True)
        old_pkg.rename(new_pkg)

    old_page = new_pkg / f"{old_id}_page.py"
    new_page = new_pkg / f"{new_id}_page.py"
    page = new_page if new_page.is_file() else old_page
    if page.is_file():
        content = page.read_text(encoding="utf-8")
        content = content.replace(f"class {_pascal(old_id)}", f"class {_pascal(new_id)}")
        content = content.replace(f'page_id = "{old_id}"', f'page_id = "{new_id}"')
        content = content.replace(f'"{old_id}"', f'"{new_id}"')
        new_page.write_text(content, encoding="utf-8")
        if page != new_page and old_page.is_file():
            old_page.unlink(missing_ok=True)


def copy_scenario_as_extension(
    scenario_id: str,
    *,
    display_name: str = "",
) -> tuple[str, Path, str]:
    """复制场景到用户扩展区并登记（show=false · scaffold）。返回 (id, root, name)。"""
    sid = str(scenario_id or "").strip()
    src = None
    name_hint = sid
    for row in list_scenarios():
        if row.scenario_id == sid:
            src = row.root
            name_hint = row.name
            break
    if src is None:
        raise ValueError(f"未找到场景：{sid}")

    old_man = parse_plugin_root(src)
    name = (display_name or name_hint).strip() or name_hint
    pid = _unique_plugin_id(suggest_plugin_id(name), avoid=old_man.plugin_id)
    dest = default_plugin_root(pid)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    shutil.copytree(src, dest)
    _rewrite_identity(dest, old_id=old_man.plugin_id, new_id=pid, name=name)

    man = parse_plugin_root(dest)
    register_plugin(man.root, show=False, status="mvp", gaps=[])
    try:
        set_lifecycle(man.plugin_id, LIFE_SCAFFOLD)
    except ValueError:
        pass
    request_nav_rebuild()
    logger.info("copy_scenario_as_extension: %s -> %s (%s)", sid, man.plugin_id, man.name)
    return man.plugin_id, Path(man.root), man.name
