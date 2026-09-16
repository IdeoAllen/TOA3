# -*- coding: utf-8 -*-
"""班级会话 handoff：培训交付看板绑定上下文，供串链模块读取。

落盘在 shared_data，不依赖 DMS；换班覆盖 current.json。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.storage_paths import shared_data_dir

MODULE_ID = "training_delivery_board"
HANDOFF_NAME = "class_session_current.json"

STAGE_IDS = (
    "bind",
    "mkdir",
    "table_card",
    "watermark",
    "inspect",
    "report",
    "pack",
)


@dataclass
class ClassSession:
    class_name: str = ""
    root_path: str = ""
    doc_url: str = ""
    roster_text: str = ""
    stage_done: dict[str, bool] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ClassSession:
        if not isinstance(data, dict):
            return cls()
        stages = data.get("stage_done") or {}
        if not isinstance(stages, dict):
            stages = {}
        return cls(
            class_name=str(data.get("class_name") or "").strip(),
            root_path=str(data.get("root_path") or "").strip(),
            doc_url=str(data.get("doc_url") or "").strip(),
            roster_text=str(data.get("roster_text") or ""),
            stage_done={str(k): bool(v) for k, v in stages.items()},
            updated_at=str(data.get("updated_at") or ""),
        )


def _handoff_path() -> Path:
    base = shared_data_dir(create=True) / MODULE_ID
    base.mkdir(parents=True, exist_ok=True)
    return base / HANDOFF_NAME


def load_session() -> ClassSession:
    path = _handoff_path()
    if not path.is_file():
        return ClassSession()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ClassSession()
    return ClassSession.from_dict(raw if isinstance(raw, dict) else None)


def save_session(session: ClassSession) -> Path:
    session.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = _handoff_path()
    path.write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def mark_stage(stage_id: str, *, done: bool = True) -> ClassSession:
    session = load_session()
    session.stage_done[str(stage_id)] = bool(done)
    save_session(session)
    return session


def clear_session() -> None:
    path = _handoff_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
