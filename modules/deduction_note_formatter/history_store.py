# -*- coding: utf-8 -*-
"""扣分备注历史记录（本机 JSON）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

_HISTORY_MAX = 80


class DeductionNoteHistory:
    def __init__(self, max_items: int = _HISTORY_MAX) -> None:
        self.max_items = max_items
        self.path = module_data_dir("deduction_note_formatter", create=True) / "history.json"
        self.items: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8")) or []
                if isinstance(raw, list):
                    self.items = [
                        x
                        for x in raw
                        if isinstance(x, dict) and (x.get("text") or x.get("source"))
                    ]
                    return
        except Exception:
            pass
        self.items = []

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.items[: self.max_items], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add(self, source: str, result: str, count: int) -> None:
        source = (source or "").strip()
        result = (result or "").strip()
        if not result and not source:
            return
        if self.items:
            last = self.items[0]
            if (last.get("text") or "").strip() == result and (last.get("source") or "").strip() == source:
                return
        preview = (result or source).replace("\r\n", "\n").replace("\r", "\n")
        self.items.insert(
            0,
            {
                "ts": datetime.now().strftime("%m-%d %H:%M:%S"),
                "count": int(count or 0),
                "preview": preview,
                "source": source,
                "text": result,
            },
        )
        self.items = self.items[: self.max_items]
        self.save()

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self.items):
            self.items.pop(index)
            self.save()

    def clear(self) -> None:
        self.items = []
        self.save()
