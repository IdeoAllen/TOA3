# -*- coding: utf-8 -*-
"""用户业务插件登记表：data/user/plugins.yml。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from services.config_service import resolve_path
from services.plugin_pack import (
    PluginManifest,
    menu_item_from_manifest,
    parse_plugin_root,
)

logger = logging.getLogger(__name__)

_CACHE: list[dict[str, Any]] | None = None


def list_managed_extensions() -> list[dict[str, Any]]:
    """合并扩展区磁盘扫描 + 登记表，供管理中心列表。"""
    from services.plugin_sandbox import list_extension_dirs

    by_id: dict[str, dict[str, Any]] = {}
    for rec in load_plugin_records(force=True):
        pid = str(rec.get("id") or "").strip()
        if not pid:
            continue
        root = str(rec.get("root") or "").strip()
        name = pid
        group = "business"
        version = ""
        try:
            if root:
                man = parse_plugin_root(root)
                name = man.name
                group = man.group
                version = man.version
        except Exception:
            pass
        by_id[pid] = {
            "id": pid,
            "name": name,
            "group": group,
            "version": version,
            "root": root,
            "registered": True,
            "show": bool(rec.get("show", True)),
            "status": str(rec.get("status") or "mvp"),
            "lifecycle": str(rec.get("lifecycle") or "").strip(),
        }

    for path in list_extension_dirs():
        try:
            man = parse_plugin_root(path)
        except Exception:
            continue
        if man.plugin_id in by_id:
            by_id[man.plugin_id]["root"] = str(man.root)
            by_id[man.plugin_id]["name"] = man.name
            by_id[man.plugin_id]["group"] = man.group
            by_id[man.plugin_id]["version"] = man.version
        else:
            by_id[man.plugin_id] = {
                "id": man.plugin_id,
                "name": man.name,
                "group": man.group,
                "version": man.version,
                "root": str(man.root),
                "registered": False,
                "show": False,
                "status": "draft",
            }
    return sorted(by_id.values(), key=lambda r: str(r.get("name") or r.get("id") or ""))


def plugins_registry_path() -> Path:
    return resolve_path("data_dir") / "user" / "plugins.yml"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def invalidate_plugin_cache() -> None:
    global _CACHE
    _CACHE = None


def load_plugin_records(*, force: bool = False) -> list[dict[str, Any]]:
    global _CACHE
    if _CACHE is not None and not force:
        return list(_CACHE)
    path = plugins_registry_path()
    if not path.is_file():
        _CACHE = []
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("读取 plugins.yml 失败: %s", exc)
        _CACHE = []
        return []
    raw = data.get("plugins") if isinstance(data, dict) else None
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict) and str(row.get("id") or "").strip():
                out.append(dict(row))
    _CACHE = out
    return list(out)


def save_plugin_records(records: list[dict[str, Any]]) -> Path:
    path = plugins_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "plugins": list(records)}
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    invalidate_plugin_cache()
    return path


def get_plugin_record(plugin_id: str) -> dict[str, Any] | None:
    pid = str(plugin_id or "").strip()
    for row in load_plugin_records():
        if str(row.get("id") or "").strip() == pid:
            return dict(row)
    return None


def is_registered_plugin(plugin_id: str) -> bool:
    rec = get_plugin_record(plugin_id)
    return bool(rec and rec.get("show", True))


def resolve_manifest(plugin_id: str) -> PluginManifest | None:
    rec = get_plugin_record(plugin_id)
    if not rec:
        return None
    root = str(rec.get("root") or "").strip()
    if not root:
        return None
    try:
        return parse_plugin_root(root)
    except Exception as exc:
        logger.warning("插件清单解析失败 %s: %s", plugin_id, exc)
        return None


def plugin_menu_items() -> list[dict[str, Any]]:
    """已登记、show、且已「开发完成」的插件 → 业务侧栏。"""
    from services.extension_lifecycle import LIFE_DEVELOPING, LIFE_SCAFFOLD

    items: list[dict[str, Any]] = []
    for rec in load_plugin_records():
        if not rec.get("show", True):
            continue
        life = str(rec.get("lifecycle") or "").strip()
        # 开发中 / 刚创建：绝不进业务侧栏（即使误标 show）
        if life in (LIFE_SCAFFOLD, LIFE_DEVELOPING):
            continue
        pid = str(rec.get("id") or "").strip()
        root = str(rec.get("root") or "").strip()
        if not pid or not root:
            continue
        try:
            man = parse_plugin_root(root)
        except Exception as exc:
            logger.warning("跳过无效插件 %s: %s", pid, exc)
            continue
        if man.plugin_id != pid:
            logger.warning("插件 id 与目录清单不一致: registry=%s toml=%s", pid, man.plugin_id)
            continue
        items.append(menu_item_from_manifest(man, show=True))
    return items


def register_plugin(
    root: Path | str,
    *,
    show: bool = True,
    status: str = "mvp",
    gaps: list[str] | None = None,
) -> PluginManifest:
    """解析并写入登记表；冲突内置 id 或落在安装树内时抛错。"""
    from services.plugin_sandbox import assert_registerable_root, resolve_plugin_workspace

    root_resolved = resolve_plugin_workspace(root)
    assert_registerable_root(root_resolved, allow_sample=True)
    man = parse_plugin_root(root_resolved)
    from services.menu_registry import MIGRATED_MODULES

    if man.plugin_id in MIGRATED_MODULES:
        raise ValueError(f"插件 id「{man.plugin_id}」与内置模块冲突，请更换 id")

    records = load_plugin_records(force=True)
    now = _now_iso()
    found = False
    for row in records:
        if str(row.get("id") or "").strip() == man.plugin_id:
            row["root"] = str(man.root)
            row["show"] = bool(show)
            row["status"] = str(status or "mvp")
            row["gaps"] = list(gaps or [])
            row["imported_at"] = now
            # 保留既有 lifecycle
            found = True
            break
    if not found:
        records.append(
            {
                "id": man.plugin_id,
                "root": str(man.root),
                "show": bool(show),
                "status": str(status or "mvp"),
                "gaps": list(gaps or []),
                "lifecycle": "scaffold",
                "imported_at": now,
            }
        )
    save_plugin_records(records)
    return man


def set_plugin_field(plugin_id: str, **fields: Any) -> None:
    """更新登记表任意字段（如 last_session_id）。"""
    pid = str(plugin_id or "").strip()
    if not pid or not fields:
        return
    records = load_plugin_records(force=True)
    for row in records:
        if str(row.get("id") or "").strip() == pid:
            for k, v in fields.items():
                if v is None:
                    continue
                row[str(k)] = v
            save_plugin_records(records)
            return
    raise ValueError(f"未登记插件：{pid}")


def set_plugin_show(plugin_id: str, show: bool) -> None:
    set_plugin_field(plugin_id, show=bool(show))


def unregister_plugin(plugin_id: str) -> None:
    pid = str(plugin_id or "").strip()
    records = [r for r in load_plugin_records(force=True) if str(r.get("id") or "").strip() != pid]
    save_plugin_records(records)


def remove_plugin(
    plugin_id: str,
    *,
    delete_files: bool = True,
    root: Path | str | None = None,
) -> Path | None:
    """移除插件：取消侧栏登记；可选删除扩展目录（仅用户扩展区，不删官方样例源）。

    未写入 plugins.yml、仅磁盘存在的扩展（registered=False）也能删掉目录。
    """
    import shutil

    from services.plugin_sandbox import (
        default_plugin_root,
        is_bundled_sample,
        list_extension_dirs,
        user_extensions_root,
    )

    pid = str(plugin_id or "").strip()
    if not pid:
        raise ValueError("缺少插件 id")

    resolved: Path | None = None
    if root:
        resolved = Path(root).expanduser().resolve()
    else:
        for row in load_plugin_records(force=True):
            if str(row.get("id") or "").strip() == pid:
                raw = str(row.get("root") or "").strip()
                if raw:
                    resolved = Path(raw).expanduser().resolve()
                break

    if resolved is None or not resolved.is_dir():
        # 未登记：按扩展区目录 / plugin.toml id 回落
        candidate = default_plugin_root(pid)
        if candidate.is_dir():
            resolved = candidate.resolve()
        else:
            for path in list_extension_dirs():
                try:
                    man = parse_plugin_root(path)
                except Exception:
                    continue
                if man.plugin_id == pid:
                    resolved = Path(man.root).resolve()
                    break

    unregister_plugin(pid)

    if not delete_files:
        return resolved
    if resolved is None or not resolved.is_dir():
        return resolved

    if is_bundled_sample(resolved):
        # 官方样例只取消登记，不删仓库内样例文件
        return resolved

    ext_home = user_extensions_root()
    try:
        resolved.relative_to(ext_home)
    except ValueError as exc:
        raise ValueError(f"拒绝删除非用户扩展区路径：{resolved}") from exc

    shutil.rmtree(resolved, ignore_errors=False)
    return resolved
