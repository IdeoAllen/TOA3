# -*- coding: utf-8 -*-
"""MACOS 桌面：根目录与浏览偏好（本地 JSON）。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

logger = logging.getLogger(__name__)

_ROOT_FILE = "desktop_root.json"
_VALID_MODES = frozenset({"columns", "icons", "list", "details"})
_VALID_HTML = frozenset({"code", "web"})
_VALID_MD = frozenset({"code", "preview"})


def _state_path() -> Path:
    return module_data_dir("column_preview", create=True) / _ROOT_FILE


def _read_doc() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("load desktop state failed: %s", exc)
        return {}


def _write_doc(doc: dict[str, Any]) -> None:
    out = _state_path()
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def load_saved_root() -> Path | None:
    raw = str((_read_doc().get("root") or "")).strip()
    if not raw:
        return None
    try:
        p = Path(raw).expanduser()
        if p.is_dir():
            return p.resolve()
    except OSError as exc:
        logger.warning("resolve desktop root failed: %s", exc)
    return None


def load_browse_mode() -> str | None:
    mode = str((_read_doc().get("mode") or "")).strip()
    return mode if mode in _VALID_MODES else None


def load_html_view_mode() -> str | None:
    mode = str((_read_doc().get("html_view_mode") or "")).strip()
    return mode if mode in _VALID_HTML else None


def load_md_view_mode() -> str | None:
    mode = str((_read_doc().get("md_view_mode") or "")).strip()
    return mode if mode in _VALID_MD else None


def save_root(root: Path) -> None:
    try:
        resolved = root.resolve()
    except OSError:
        resolved = root
    doc = _read_doc()
    doc["root"] = str(resolved)
    _write_doc(doc)


def save_ui_prefs(
    *,
    mode: str | None = None,
    html_view_mode: str | None = None,
    md_view_mode: str | None = None,
) -> None:
    """合并写入浏览模式 / HTML·Markdown 双模式偏好，不丢根目录。"""
    doc = _read_doc()
    changed = False
    if mode is not None and mode in _VALID_MODES:
        doc["mode"] = mode
        changed = True
    if html_view_mode is not None and html_view_mode in _VALID_HTML:
        doc["html_view_mode"] = html_view_mode
        changed = True
    if md_view_mode is not None and md_view_mode in _VALID_MD:
        doc["md_view_mode"] = md_view_mode
        changed = True
    if changed:
        _write_doc(doc)
