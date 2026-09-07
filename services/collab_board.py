# -*- coding: utf-8 -*-
"""人机协作任务表（OPS-02-协作任务说明.md）路径解析与用户副本同步。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from services.runtime_paths import get_app_root, get_user_data_root
from services.storage_paths import shared_data_dir

BOARD_NAME = "OPS-02-协作任务说明.md"
NOTE_TITLE = "协作任务表"
_SETTINGS_KEY = "collab_board_note_id"


def repo_board_path() -> Path:
    return get_app_root() / "docs" / "handoff" / BOARD_NAME


def shared_board_path(*, create_dir: bool = False) -> Path:
    base = shared_data_dir(create=create_dir) / "collab"
    if create_dir:
        base.mkdir(parents=True, exist_ok=True)
    return base / BOARD_NAME


def release_board_path() -> Path:
    return get_user_data_root() / "data" / "shared" / "collab" / BOARD_NAME


def candidate_board_paths() -> list[Path]:
    """按优先级：仓库真相源 → 当前 data/shared → 正式版用户目录。"""
    seen: set[str] = set()
    out: list[Path] = []
    for p in (repo_board_path(), shared_board_path(), release_board_path()):
        key = os.path.normcase(str(p.resolve()) if p.exists() else str(p))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def resolve_board_path() -> Path | None:
    """返回可读的最新协作表路径；都不存在则 None。"""
    found: list[Path] = []
    for p in candidate_board_paths():
        if p.is_file():
            found.append(p)
    if not found:
        return None
    found.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return found[0]


def sync_board_to_user_copies(source: Path | None = None) -> Path | None:
    """把真相源复制到开发/正式版 shared，便于正式版与无仓库环境打开。"""
    src = source or repo_board_path()
    if not src.is_file():
        src = resolve_board_path()
    if src is None or not src.is_file():
        return None
    targets = [shared_board_path(create_dir=True), release_board_path()]
    for t in targets:
        try:
            t.parent.mkdir(parents=True, exist_ok=True)
            if t.resolve() == src.resolve():
                continue
            shutil.copy2(src, t)
        except OSError:
            continue
    return src


def read_board_text() -> tuple[str | None, Path | None]:
    """返回 (正文, 路径)。优先 sync 后再读最新。"""
    sync_board_to_user_copies()
    path = resolve_board_path()
    if path is None:
        return None, None
    try:
        return path.read_text(encoding="utf-8"), path
    except OSError:
        return None, path
