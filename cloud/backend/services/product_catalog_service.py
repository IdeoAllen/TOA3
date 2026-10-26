# -*- coding: utf-8 -*-
"""产品目录 DB：菜单 module 池 + 功能包 SKU（运营台主维护）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy.orm import Session

from models import AdminUser, ToaFeaturePack, ToaMenuModule

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
SPECIAL_MODULE_IDS = frozenset({"all", "home", "system_settings", "job_scheduler", "notifications", "about"})
PROTECTED_PACK_IDS = frozenset({"local_free"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def _dump_json_list(items: list[str] | None) -> str:
    clean = [str(x).strip() for x in (items or []) if str(x).strip()]
    return json.dumps(clean, ensure_ascii=False)


def menu_module_to_dict(row: ToaMenuModule) -> dict[str, Any]:
    try:
        sort_order = int(getattr(row, "sort_order", None) or 0)
    except Exception:
        sort_order = 0
    try:
        group_order = int(getattr(row, "group_order", None) or 99)
    except Exception:
        group_order = 99
    return {
        "id": row.id,
        "name": row.name,
        "group": row.group_id,
        "group_label": row.group_label,
        "order": sort_order,
        "group_order": group_order,
        "show": bool(row.show_in_menu),
        "requires_license": bool(row.requires_license),
        "feature_id": row.feature_id or row.id,
        "migration_status": row.migration_status or "",
        "app_version": row.app_version or "",
        "is_active": bool(row.is_active),
        "published_at": row.published_at.isoformat() if row.published_at else "",
        "published_by": row.published_by or "",
    }


def pack_row_to_dict(row: ToaFeaturePack, *, db: Session | None = None, expanded: bool = True) -> dict[str, Any]:
    features = _json_list(row.features_json)
    includes = _json_list(row.includes_json)
    if expanded and db is not None:
        expanded_features = expand_pack_features_db(db, row.id)
    elif expanded:
        expanded_features = expand_pack_features(features, includes)
    else:
        expanded_features = features
    try:
        validity_days = max(1, int(getattr(row, "validity_days", None) or 365))
    except Exception:
        validity_days = 365
    out: dict[str, Any] = {
        "id": row.id,
        "plan_id": row.id,
        "name": row.name,
        "plan_name": row.name,
        "desc": row.desc or "",
        "sellable": bool(row.sellable),
        "price_yuan": int(row.price_yuan or 0),
        "validity_days": validity_days,
        "features": expanded_features,
        "raw_features": features,
        "includes": includes,
        "feature_count": len(expanded_features) if expanded_features != ["all"] else -1,
        "is_active": bool(row.is_active),
        "catalog_version": int(row.catalog_version or 1),
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        # 兼容旧客户端
        "pack_id": row.id,
    }
    return out


def list_menu_modules(
    db: Session,
    *,
    active_only: bool = True,
    q: str = "",
    show_hidden: bool = True,
) -> list[dict[str, Any]]:
    query = db.query(ToaMenuModule)
    if active_only:
        query = query.filter(ToaMenuModule.is_active.is_(True))
    rows = query.all()
    items = [menu_module_to_dict(r) for r in rows]
    needle = str(q or "").strip().lower()
    if needle:
        items = [
            m
            for m in items
            if needle
            in " ".join(
                [
                    str(m.get("id") or ""),
                    str(m.get("name") or ""),
                    str(m.get("group") or ""),
                    str(m.get("group_label") or ""),
                    str(m.get("feature_id") or ""),
                    str(m.get("migration_status") or ""),
                ]
            ).lower()
        ]
    if not show_hidden:
        items = [m for m in items if m.get("show", True)]
    items.sort(
        key=lambda m: (
            int(m.get("group_order") or 99),
            int(m.get("order") or 0),
            str(m.get("id") or ""),
        )
    )
    return items


def active_module_ids(db: Session) -> frozenset[str]:
    rows = db.query(ToaMenuModule.id).filter(ToaMenuModule.is_active.is_(True)).all()
    ids = {str(r[0]) for r in rows if r and r[0]}
    return frozenset(ids | SPECIAL_MODULE_IDS)


def publish_menu_modules(
    db: Session,
    modules: list[dict],
    *,
    app_version: str = "",
    published_by: str = "",
) -> dict[str, Any]:
    if not modules:
        raise ValueError("菜单目录不能为空")
    seen: set[str] = set()
    now = _now()
    incoming_ids: set[str] = set()
    for raw in modules:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        incoming_ids.add(mid)
        row = db.query(ToaMenuModule).filter(ToaMenuModule.id == mid).first()
        if row is None:
            row = ToaMenuModule(id=mid)
            db.add(row)
        row.name = str(raw.get("name") or mid)
        row.group_id = str(raw.get("group") or raw.get("group_id") or "other")
        row.group_label = str(raw.get("group_label") or raw.get("group_name") or "")
        try:
            row.sort_order = int(raw.get("order") if raw.get("order") is not None else raw.get("sort_order") or 0)
        except Exception:
            row.sort_order = 0
        try:
            row.group_order = int(raw.get("group_order") if raw.get("group_order") is not None else 99)
        except Exception:
            row.group_order = 99
        row.show_in_menu = bool(raw.get("show", raw.get("show_in_menu", True)))
        row.requires_license = bool(raw.get("requires_license", False))
        row.feature_id = str(raw.get("feature_id") or mid)
        row.migration_status = str(raw.get("migration_status") or "")
        row.app_version = str(app_version or raw.get("app_version") or "")
        row.is_active = True
        row.published_at = now
        row.published_by = published_by or row.published_by
        row.updated_at = now

    for row in db.query(ToaMenuModule).filter(ToaMenuModule.is_active.is_(True)).all():
        if row.id not in incoming_ids:
            row.is_active = False
            row.updated_at = now

    db.commit()
    return {
        "published": len(incoming_ids),
        "app_version": app_version,
        "published_by": published_by,
    }


def expand_pack_features(features: list[str], includes: list[str] | None = None, *, _stack: frozenset[str] | None = None) -> list[str]:
    stack = set(_stack or ())
    result: set[str] = set()
    for raw in list(features or []) + list(includes or []):
        token = str(raw or "").strip()
        if not token:
            continue
        if token == "all":
            return ["all"]
        if token in stack:
            continue
        result.add(token)
    if "all" in result:
        return ["all"]
    return sorted(result)


def expand_pack_features_db(db: Session, pack_id: str, *, _stack: frozenset[str] | None = None) -> list[str]:
    pid = str(pack_id or "").strip()
    if not pid:
        return []
    if pid == "all":
        return ["all"]
    stack = set(_stack or ())
    if pid in stack:
        return []
    row = db.query(ToaFeaturePack).filter(ToaFeaturePack.id == pid, ToaFeaturePack.is_active.is_(True)).first()
    if not row:
        return []
    features = _json_list(row.features_json)
    includes = _json_list(row.includes_json)
    if "all" in features:
        return ["all"]
    result: set[str] = set(features)
    for inc in includes:
        for token in expand_pack_features_db(db, inc, _stack=frozenset(stack | {pid})):
            if token == "all":
                return ["all"]
            result.add(token)
    return sorted(result)


def validate_pack_modules(
    db: Session,
    features: list[str],
    includes: list[str] | None = None,
    *,
    pack_id: str = "",
) -> dict[str, Any]:
    pid = str(pack_id or "").strip()
    if pid:
        expanded = expand_pack_features_db(db, pid)
    else:
        expanded = expand_pack_features(features, includes)
    if expanded == ["all"]:
        return {"ok": True, "unknown": [], "modules": [], "module_count": -1, "scope": "all"}
    known = active_module_ids(db)
    unknown = sorted({t for t in expanded if t not in known})
    idx = {m["id"]: m for m in list_menu_modules(db)}
    modules = [idx[t] for t in expanded if t in idx]
    return {
        "ok": not unknown,
        "unknown": unknown,
        "modules": modules,
        "module_count": len(modules),
        "scope": "partial",
    }


def list_packs_db(
    db: Session,
    *,
    sellable_only: bool = False,
    include_free: bool = True,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    q = db.query(ToaFeaturePack)
    if active_only:
        q = q.filter(ToaFeaturePack.is_active.is_(True))
    rows = q.order_by(ToaFeaturePack.id).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        if sellable_only and not row.sellable:
            continue
        if not include_free and row.id == "local_free":
            continue
        item = pack_row_to_dict(row, db=db)
        item["menu_validation"] = validate_pack_modules(
            db, _json_list(row.features_json), _json_list(row.includes_json), pack_id=row.id
        )
        out.append(item)
    out.sort(key=lambda x: (not x.get("sellable"), x.get("id") or ""))
    return out


def get_pack_db(db: Session, pack_id: str) -> dict[str, Any] | None:
    pid = str(pack_id or "").strip()
    if not pid:
        return None
    row = db.query(ToaFeaturePack).filter(ToaFeaturePack.id == pid, ToaFeaturePack.is_active.is_(True)).first()
    if not row:
        return None
    item = pack_row_to_dict(row, db=db)
    item["menu_validation"] = validate_pack_modules(
        db, _json_list(row.features_json), _json_list(row.includes_json), pack_id=pid
    )
    return item


def save_pack_db(
    db: Session,
    pack_id: str,
    data: dict,
    *,
    operator: Optional[AdminUser] = None,
    skip_validation: bool = False,
) -> dict[str, Any]:
    pid = str(pack_id or data.get("id") or "").strip()
    if not pid:
        raise ValueError("功能包 ID 不能为空")
    if not pid.replace("_", "").isalnum() or pid[0].isdigit():
        raise ValueError("功能包 ID 须字母开头，仅含小写字母、数字、下划线")
    features = _json_list(_dump_json_list(data.get("features") or []))
    includes = _json_list(_dump_json_list(data.get("includes") or []))
    if not features and not includes and pid not in ("local_free", "experience_beta"):
        raise ValueError("请至少选择一个终端 module 或 includes 包")
    validation = validate_pack_modules(db, features, includes)
    if not skip_validation:
        if not validation.get("ok"):
            unknown = validation.get("unknown") or []
            raise ValueError(f"含未发布 module：{', '.join(unknown)}（请终端管理员先同步菜单目录）")
        for inc in includes:
            if not db.query(ToaFeaturePack).filter(ToaFeaturePack.id == inc, ToaFeaturePack.is_active.is_(True)).first():
                if inc != pid:
                    raise ValueError(f"includes 引用了不存在功能包：{inc}")

    row = db.query(ToaFeaturePack).filter(ToaFeaturePack.id == pid).first()
    if row is None:
        row = ToaFeaturePack(id=pid)
        db.add(row)
    row.name = str(data.get("name") or pid)
    row.desc = str(data.get("desc") or "")
    row.sellable = bool(data.get("sellable", True))
    try:
        row.price_yuan = max(0, int(data.get("price_yuan") or 0))
    except Exception as exc:
        raise ValueError("定价格式无效") from exc
    try:
        row.validity_days = max(1, int(data.get("validity_days") or getattr(row, "validity_days", None) or 365))
    except Exception as exc:
        raise ValueError("有效期天数无效") from exc
    row.features_json = _dump_json_list(features)
    row.includes_json = _dump_json_list(includes)
    row.is_active = bool(data.get("is_active", True))
    row.catalog_version = int(row.catalog_version or 0) + 1
    row.updated_by_id = operator.id if operator else None
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    saved = get_pack_db(db, pid)
    if not saved:
        raise ValueError("保存失败")
    return saved


def _assert_pack_mutable(pack_id: str, *, action: str) -> str:
    pid = str(pack_id or "").strip()
    if not pid:
        raise ValueError("产品方案 ID 不能为空")
    if pid in PROTECTED_PACK_IDS:
        raise ValueError(f"系统方案 {pid} 不可{action}")
    return pid


def disable_pack_db(
    db: Session,
    pack_id: str,
    *,
    operator: Optional[AdminUser] = None,
) -> dict[str, Any]:
    """停用售卖：sellable=False，方案仍保留供历史订单/授权引用。"""
    pid = _assert_pack_mutable(pack_id, action="停用")
    row = db.query(ToaFeaturePack).filter(ToaFeaturePack.id == pid, ToaFeaturePack.is_active.is_(True)).first()
    if not row:
        raise ValueError("产品方案不存在或已清除")
    row.sellable = False
    row.catalog_version = int(row.catalog_version or 0) + 1
    row.updated_by_id = operator.id if operator else None
    row.updated_at = _now()
    db.commit()
    saved = get_pack_db(db, pid)
    if not saved:
        raise ValueError("停用失败")
    return saved


def enable_pack_db(
    db: Session,
    pack_id: str,
    *,
    operator: Optional[AdminUser] = None,
) -> dict[str, Any]:
    """恢复售卖：sellable=True。"""
    pid = _assert_pack_mutable(pack_id, action="恢复")
    row = db.query(ToaFeaturePack).filter(ToaFeaturePack.id == pid, ToaFeaturePack.is_active.is_(True)).first()
    if not row:
        raise ValueError("产品方案不存在或已清除")
    row.sellable = True
    row.catalog_version = int(row.catalog_version or 0) + 1
    row.updated_by_id = operator.id if operator else None
    row.updated_at = _now()
    db.commit()
    saved = get_pack_db(db, pid)
    if not saved:
        raise ValueError("恢复失败")
    return saved


def clear_pack_db(
    db: Session,
    pack_id: str,
    *,
    operator: Optional[AdminUser] = None,
) -> dict[str, Any]:
    """清除方案：is_active=False，不再出现在目录与下单列表。"""
    pid = _assert_pack_mutable(pack_id, action="清除")
    row = db.query(ToaFeaturePack).filter(ToaFeaturePack.id == pid).first()
    if not row or not row.is_active:
        raise ValueError("产品方案不存在或已清除")
    for other in db.query(ToaFeaturePack).filter(
        ToaFeaturePack.is_active.is_(True),
        ToaFeaturePack.id != pid,
    ).all():
        includes = _json_list(other.includes_json)
        if pid in includes:
            raise ValueError(f"方案「{other.name or other.id}」仍引用 {pid}，请先编辑后再清除")
    row.sellable = False
    row.is_active = False
    row.catalog_version = int(row.catalog_version or 0) + 1
    row.updated_by_id = operator.id if operator else None
    row.updated_at = _now()
    db.commit()
    return {"id": pid, "cleared": True}


def catalog_meta_db(db: Session) -> dict[str, Any]:
    modules = list_menu_modules(db)
    latest = db.query(ToaMenuModule).filter(ToaMenuModule.is_active.is_(True)).order_by(ToaMenuModule.published_at.desc()).first()
    group_labels: dict[str, str] = {}
    for m in modules:
        gid = str(m.get("group") or "").strip()
        glabel = str(m.get("group_label") or "").strip()
        if gid and glabel and gid not in group_labels:
            group_labels[gid] = glabel
    yaml_path = CONFIG_DIR / "menu_catalog.yml"
    if yaml_path.is_file():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            raw = data.get("group_labels") or {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    group_labels[str(k)] = str(v)
        except Exception:
            pass
    return {
        "product": "TOA3",
        "source": "database",
        "app_version": (latest.app_version if latest else "") or "",
        "exported_at": (latest.published_at.isoformat() if latest and latest.published_at else ""),
        "module_count": len(modules),
        "published_by": (latest.published_by if latest else "") or "",
        "synced": bool(modules),
        "group_labels": group_labels,
    }


def seed_from_yaml_files(db: Session) -> dict[str, int]:
    """首次部署：yaml → DB（之后以 DB 为准）。"""
    menu_path = CONFIG_DIR / "menu_catalog.yml"
    packs_path = CONFIG_DIR / "feature_packs.yml"
    commerce_path = CONFIG_DIR / "commerce.yml"
    inserted_m = 0
    inserted_p = 0

    if db.query(ToaMenuModule).count() == 0 and menu_path.is_file():
        data = yaml.safe_load(menu_path.read_text(encoding="utf-8")) or {}
        modules = data.get("modules") or []
        publish_menu_modules(
            db,
            modules,
            app_version=str(data.get("app_version") or ""),
            published_by="seed:menu_catalog.yml",
        )
        inserted_m = len(modules)

    if db.query(ToaFeaturePack).count() == 0 and packs_path.is_file():
        packs_raw = yaml.safe_load(packs_path.read_text(encoding="utf-8")) or {}
        prices = {}
        if commerce_path.is_file():
            comm = yaml.safe_load(commerce_path.read_text(encoding="utf-8")) or {}
            prices = comm.get("pack_prices_yuan") or {}
        blocks = [(str(pid), block) for pid, block in (packs_raw.get("packs") or {}).items() if isinstance(block, dict)]
        blocks.sort(key=lambda x: (0 if not (x[1].get("includes") or []) else 1, x[0]))
        for pid, block in blocks:
            try:
                validity_days = max(1, int(block.get("validity_days") or 365))
            except Exception:
                validity_days = 365
            save_pack_db(
                db,
                str(pid),
                {
                    "id": pid,
                    "name": block.get("name"),
                    "desc": block.get("desc"),
                    "sellable": block.get("sellable", True),
                    "price_yuan": prices.get(pid, 0),
                    "validity_days": validity_days,
                    "features": list(block.get("features") or []),
                    "includes": list(block.get("includes") or []),
                },
                operator=None,
                skip_validation=True,
            )
            inserted_p += 1
    return {"menu_modules": inserted_m, "packs": inserted_p}
