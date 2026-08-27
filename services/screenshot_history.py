# -*- coding: utf-8 -*-
"""截图历史清单（轻量索引 + 目录扫描兜底）。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_output_dir

logger = logging.getLogger(__name__)

_MAX_ITEMS = 120


def _index_path() -> Path:
    return module_output_dir("screenshot", create=True) / "history_index.json"


def _load_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]
    except Exception:
        logger.debug("load screenshot index failed", exc_info=True)
        return []


def _save_index(items: list[dict[str, Any]]) -> None:
    path = _index_path()
    payload = {
        "items": items[:_MAX_ITEMS],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def record_screenshot(path: Path | str, *, source: str = "annotate") -> dict[str, Any] | None:
    """登记一张已保存的成品图。"""
    p = Path(path)
    if not p.is_file():
        return None
    item = {
        "path": str(p.resolve()),
        "source": source,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "size": p.stat().st_size,
    }
    items = [item] + [x for x in _load_index() if str(x.get("path") or "") != item["path"]]
    try:
        _save_index(items)
    except Exception:
        logger.debug("save screenshot index failed", exc_info=True)
    return item


def list_recent_screenshots(limit: int = 30) -> list[Path]:
    """优先读索引中仍存在的文件，不足时用目录扫描补齐。"""
    limit = max(1, int(limit))
    seen: set[str] = set()
    out: list[Path] = []
    for it in _load_index():
        raw = str(it.get("path") or "")
        if not raw:
            continue
        p = Path(raw)
        if p.is_file() and raw not in seen:
            seen.add(raw)
            out.append(p)
        if len(out) >= limit:
            return out[:limit]

    root = module_output_dir("screenshot", create=True)
    files = sorted(
        (p for p in root.rglob("*.png") if p.name != "history_index.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in files:
        key = str(p.resolve())
        if key in seen:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out[:limit]
