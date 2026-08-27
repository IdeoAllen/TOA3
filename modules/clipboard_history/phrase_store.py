# -*- coding: utf-8 -*-
"""剪贴板常用短语（本地 JSON）。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

_STORE: list[dict[str, Any]] | None = None


def _path() -> Path:
    return module_data_dir("clipboard_history", create=True) / "phrases.json"


def load_phrases() -> list[dict[str, Any]]:
    global _STORE
    if _STORE is not None:
        return _STORE
    path = _path()
    if not path.is_file():
        _STORE = [
            {"id": "p1", "text": "收到，马上处理。"},
            {"id": "p2", "text": "稍后回电，谢谢。"},
            {"id": "p3", "text": "已安排，请知悉。"},
        ]
        save_phrases(_STORE)
        return _STORE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _STORE = []
        return _STORE
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, dict) and str(x.get("text") or "").strip():
                items.append(
                    {
                        "id": str(x.get("id") or uuid.uuid4().hex[:8]),
                        "text": str(x.get("text") or "").strip(),
                    }
                )
    _STORE = items
    return _STORE


def save_phrases(items: list[dict[str, Any]]) -> None:
    global _STORE
    _STORE = list(items)
    _path().write_text(json.dumps(_STORE, ensure_ascii=False, indent=2), encoding="utf-8")


def add_phrase(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if not t:
        raise ValueError("短语不能为空")
    items = load_phrases()
    entry = {"id": uuid.uuid4().hex[:8], "text": t}
    items.insert(0, entry)
    save_phrases(items)
    return entry


def delete_phrase(phrase_id: str) -> bool:
    items = load_phrases()
    new = [x for x in items if x.get("id") != phrase_id]
    if len(new) == len(items):
        return False
    save_phrases(new)
    return True
