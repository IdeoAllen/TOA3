# -*- coding: utf-8 -*-
"""MACOS 桌面：根目录等本地偏好。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from services.storage_paths import module_data_dir

logger = logging.getLogger(__name__)

_ROOT_FILE = "desktop_root.json"


def _state_path() -> Path:
    return module_data_dir("column_preview", create=True) / _ROOT_FILE


def load_saved_root() -> Path | None:
    path = _state_path()
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        raw = str((doc or {}).get("root") or "").strip()
        if not raw:
            return None
        p = Path(raw).expanduser()
        if p.is_dir():
            return p.resolve()
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("load desktop root failed: %s", exc)
    return None


def save_root(root: Path) -> None:
    try:
        resolved = root.resolve()
    except OSError:
        resolved = root
    payload = {"root": str(resolved)}
    out = _state_path()
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
