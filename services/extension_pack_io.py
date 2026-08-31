# -*- coding: utf-8 -*-
"""扩展包 zip 导出/导入（对齐 doc 29b extension.pack · P2 本机管道）。"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.notify_bus import request_nav_rebuild
from services.plugin_loader import audit_plugin_root
from services.plugin_pack import parse_plugin_root
from services.plugin_registry import register_plugin, set_plugin_field
from services.plugin_sandbox import default_plugin_root, user_extensions_root

logger = logging.getLogger(__name__)

META_NAME = "pack.meta.json"
SCHEMA_VERSION = 1


@dataclass
class PackExportResult:
    zip_path: Path
    plugin_id: str
    content_sha256: str
    meta: dict[str, Any]


@dataclass
class PackImportResult:
    plugin_id: str
    root: Path
    name: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_pack_meta(
    root: Path,
    *,
    content_sha256: str,
    audit_ok: bool,
    audit_summary: str = "",
) -> dict[str, Any]:
    man = parse_plugin_root(root)
    integrations: list[str] = []
    try:
        import tomllib

        raw = tomllib.loads((root / "plugin.toml").read_text(encoding="utf-8"))
        integrations = list((raw.get("safety") or {}).get("integrations") or [])
    except Exception:
        pass
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_kind": "extension.pack",
        "plugin_id": man.plugin_id,
        "name": man.name,
        "version": man.version,
        "group": man.group,
        "description": man.description or "",
        "author": man.author or "",
        "capabilities": ["l1"],
        "integrations": integrations,
        "content_sha256": content_sha256,
        "audit_ok": bool(audit_ok),
        "audit_summary": audit_summary or "",
        "exported_at": _now_iso(),
        "review_status": "draft",
    }


def export_extension_zip(
    root: Path | str,
    dest_zip: Path | str | None = None,
) -> PackExportResult:
    """审计通过后打包扩展目录为 zip（含 pack.meta.json）。"""
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"扩展目录不存在：{path}")
    man, report = audit_plugin_root(path)
    if man is None or not report.ok:
        summary = ""
        if hasattr(report, "user_summary"):
            summary = str(report.user_summary() or "")
        raise ValueError(summary or "扩展未通过审计，无法导出")

    out = (
        Path(dest_zip).expanduser().resolve()
        if dest_zip
        else path.parent / f"{man.plugin_id}.toa-ext.zip"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    # 先打无 meta 的 zip 算内容摘要，再重打含 meta
    tmp_body = out.with_suffix(out.suffix + ".body")
    if tmp_body.exists():
        tmp_body.unlink()
    with zipfile.ZipFile(tmp_body, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in path.rglob("*"):
            if not fp.is_file():
                continue
            if "__pycache__" in fp.parts or fp.suffix == ".pyc":
                continue
            if fp.name == META_NAME:
                continue
            zf.write(fp, arcname=fp.relative_to(path).as_posix())
    digest = _sha256_file(tmp_body)
    summary = ""
    if hasattr(report, "user_summary"):
        summary = str(report.user_summary() or "")
    meta = build_pack_meta(
        path, content_sha256=digest, audit_ok=True, audit_summary=summary
    )

    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in path.rglob("*"):
            if not fp.is_file():
                continue
            if "__pycache__" in fp.parts or fp.suffix == ".pyc":
                continue
            if fp.name == META_NAME:
                continue
            zf.write(fp, arcname=fp.relative_to(path).as_posix())
        zf.writestr(META_NAME, json.dumps(meta, ensure_ascii=False, indent=2))
    tmp_body.unlink(missing_ok=True)

    logger.info("export_extension_zip: %s -> %s", man.plugin_id, out)
    return PackExportResult(
        zip_path=out,
        plugin_id=man.plugin_id,
        content_sha256=digest,
        meta=meta,
    )


def import_extension_zip(
    zip_path: Path | str,
    *,
    target_id: str = "",
    show: bool = False,
) -> PackImportResult:
    """解压到用户扩展区、审计、登记（默认不上业务侧栏）。"""
    zp = Path(zip_path).expanduser().resolve()
    if not zp.is_file():
        raise ValueError(f"包不存在：{zp}")

    ensure = user_extensions_root()
    staging = ensure / f"_import_{zp.stem}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zp, "r") as zf:
            zf.extractall(staging)
        root = staging
        if not (root / "plugin.toml").is_file():
            subs = [p for p in root.iterdir() if p.is_dir()]
            if len(subs) == 1 and (subs[0] / "plugin.toml").is_file():
                root = subs[0]
        if not (root / "plugin.toml").is_file():
            raise ValueError("包内缺少 plugin.toml")

        man = parse_plugin_root(root)
        pid = str(target_id or man.plugin_id).strip()
        if pid != man.plugin_id:
            raise ValueError("暂不支持导入时改 id；请与包内 plugin_id 一致")

        dest = default_plugin_root(pid)
        if dest.exists():
            raise ValueError(f"扩展目录已存在：{dest}（请先移除）")

        shutil.copytree(root, dest)
        # 去掉 meta 文件（可选保留）
        meta_fp = dest / META_NAME
        if meta_fp.is_file():
            meta_fp.unlink(missing_ok=True)

        man2, report = audit_plugin_root(dest)
        if man2 is None or not report.ok:
            shutil.rmtree(dest, ignore_errors=True)
            summary = ""
            if hasattr(report, "user_summary"):
                summary = str(report.user_summary() or "")
            raise ValueError(summary or "导入审计失败")

        register_plugin(dest, show=show, status="mvp", gaps=[])
        try:
            set_plugin_field(pid, lifecycle="scaffold")
        except Exception:
            pass
        request_nav_rebuild()
        return PackImportResult(plugin_id=pid, root=dest, name=man2.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
