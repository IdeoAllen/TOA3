# -*- coding: utf-8 -*-
"""协作任务表路径与同步自检。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.collab_board import (
        NOTE_TITLE,
        read_board_text,
        repo_board_path,
        sync_board_to_user_copies,
    )

    assert NOTE_TITLE == "协作任务表"
    repo = repo_board_path()
    if not repo.is_file():
        print(f"FAIL: missing {repo}")
        return 1
    synced = sync_board_to_user_copies(repo)
    body, path = read_board_text()
    if not body or path is None:
        print("FAIL: read_board_text empty")
        return 1
    if "人机协作任务表" not in body and "C-01" not in body:
        print("FAIL: board content unexpected")
        return 1
    print(f"OK: board {path} ({len(body)} chars) synced={synced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
