# -*- coding: utf-8 -*-
"""TOA 业务插件包：契约解析与路径约定（见 docs/architecture/28）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+")


@dataclass(frozen=True)
class PluginManifest:
    schema_version: int
    plugin_id: str
    name: str
    group: str
    order: int
    version: str
    requires_license: bool
    feature_id: str
    author: str
    description: str
    module_path: str
    class_name: str
    page_id: str
    entry_surface: str
    web_root: str
    allow_network: bool
    allow_shell: bool
    integrations: tuple[str, ...]
    root: Path
    raw: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    @property
    def page_file(self) -> Path:
        # modules/<id>/<id>_page.py
        mid = self.plugin_id
        return self.root / "modules" / mid / f"{mid}_page.py"

    @property
    def web_entry_file(self) -> Path:
        rel = (self.web_root or "ui/index.html").strip().lstrip("/\\")
        return self.root / rel

    @property
    def is_webview_surface(self) -> bool:
        return str(self.entry_surface or "qt").strip().lower() == "webview"


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _load_toml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib

        data = tomllib.loads(text)
    except ModuleNotFoundError:
        # Python < 3.11：允许同目录 plugin.yml 兜底（发版环境应为 3.11+）
        yml = path.with_suffix(".yml")
        if not yml.is_file():
            raise RuntimeError("需要 Python 3.11+（tomllib）或提供 plugin.yml") from None
        import yaml

        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("plugin.toml 根节点须为表")
    return data


def find_manifest_path(root: Path) -> Path | None:
    root = root.resolve()
    for name in ("plugin.toml", "plugin.yml"):
        p = root / name
        if p.is_file():
            return p
    return None


def parse_plugin_root(root: Path | str) -> PluginManifest:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError(f"插件根目录不存在：{root_path}")
    man_path = find_manifest_path(root_path)
    if man_path is None:
        raise ValueError("缺少 plugin.toml（或 plugin.yml）")

    if man_path.suffix.lower() == ".yml":
        import yaml

        data = yaml.safe_load(man_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("plugin.yml 根节点须为映射")
    else:
        data = _load_toml(man_path)

    plugin = data.get("plugin") if isinstance(data.get("plugin"), dict) else {}
    entry = data.get("entry") if isinstance(data.get("entry"), dict) else {}
    safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}

    pid = str(plugin.get("id") or "").strip()
    if not _PLUGIN_ID_RE.match(pid):
        raise ValueError("plugin.id 须为小写 snake_case（字母开头）")

    name = str(plugin.get("name") or pid).strip()
    group = str(plugin.get("group") or "business").strip().lower()
    from services.menu_registry import GROUP_ORDER, normalize_menu_group_id

    g = normalize_menu_group_id(group)
    if g not in GROUP_ORDER:
        raise ValueError(f"plugin.group 须为 {GROUP_ORDER} 之一（可用别名 ai→engines, directory/file→files）")

    version = str(plugin.get("version") or "0.1.0").strip()
    if not _VERSION_RE.match(version):
        raise ValueError("plugin.version 须为 x.y.z")

    entry_surface = str(entry.get("surface") or "qt").strip().lower()
    if entry_surface not in ("qt", "webview"):
        raise ValueError("entry.surface 须为 qt 或 webview")

    web_root = str(entry.get("web_root") or "ui/index.html").strip().lstrip("/\\")
    if ".." in web_root.replace("\\", "/").split("/"):
        raise ValueError("entry.web_root 不能含 ..")

    class_name = str(entry.get("class_name") or "").strip()
    if not class_name:
        class_name = "WebExtensionHost" if entry_surface == "webview" else ""
    if not class_name or not class_name.isidentifier():
        raise ValueError("entry.class_name 无效")

    module_path = str(entry.get("module_path") or f"modules.{pid}.{pid}_page").strip()
    page_id = str(entry.get("page_id") or pid).strip()
    if page_id != pid:
        raise ValueError("entry.page_id 必须与 plugin.id 一致")

    ints_raw = safety.get("integrations") or []
    if not isinstance(ints_raw, list):
        ints_raw = []
    integrations = tuple(str(x).strip() for x in ints_raw if str(x).strip())

    schema_version = int(data.get("schema_version") or plugin.get("schema_version") or 1)

    return PluginManifest(
        schema_version=schema_version,
        plugin_id=pid,
        name=name,
        group=g,
        order=int(plugin.get("order") or 90),
        version=version,
        requires_license=_as_bool(plugin.get("requires_license"), False),
        feature_id=str(plugin.get("feature_id") or "").strip(),
        author=str(plugin.get("author") or "").strip(),
        description=str(plugin.get("description") or "").strip(),
        module_path=module_path,
        class_name=class_name,
        page_id=page_id,
        entry_surface=entry_surface,
        web_root=web_root,
        allow_network=_as_bool(safety.get("allow_network"), False),
        allow_shell=_as_bool(safety.get("allow_shell"), False),
        integrations=integrations,
        root=root_path,
        raw=data,
    )


def menu_item_from_manifest(manifest: PluginManifest, *, show: bool = True) -> dict[str, Any]:
    return {
        "id": manifest.plugin_id,
        "name": manifest.name,
        "group": manifest.group,
        "order": manifest.order,
        "show": bool(show),
        "icon": "llm_assistant",
        "desc": manifest.description,
        "requires_license": manifest.requires_license,
        "feature_id": manifest.feature_id or None,
        "module_path": manifest.module_path,
        "class_name": manifest.class_name,
        "source": "user_plugin",
        "plugin_root": str(manifest.root),
        "plugin_version": manifest.version,
    }
