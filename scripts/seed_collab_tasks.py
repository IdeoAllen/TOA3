# -*- coding: utf-8 -*-
"""把 docs/handoff/collab_tasks.json 种子进本机四象限任务。

默认写入「当前运行环境」数据目录（仓库开发版 = TOA3/data/...）。
正式版（安装包绿标）请加 --edition release，写入 %LOCALAPPDATA%\\YCZH-TOA3\\...

用法：
  python scripts/seed_collab_tasks.py                  # 开发版数据
  python scripts/seed_collab_tasks.py --edition release  # 正式版数据
  python scripts/seed_collab_tasks.py --edition both
  python scripts/seed_collab_tasks.py --wipe-collab --edition release
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.quadrant_tasks.task_store import _normalize_task  # noqa: E402

SEED = ROOT / "docs" / "handoff" / "collab_tasks.json"
BOARD_MD = ROOT / "docs" / "handoff" / "OPS-02-协作任务说明.md"


def _is_collab(task: dict) -> bool:
    tid = str(task.get("id") or "")
    title = str(task.get("title") or "")
    return tid.startswith("collab-") or title.startswith("[协作]")


def _dev_tasks_path() -> Path:
    return ROOT / "data" / "module" / "quadrant_tasks" / "tasks.json"


def _release_tasks_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "YCZH-TOA3" / "data" / "module" / "quadrant_tasks" / "tasks.json"


def _read_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for x in raw:
        if isinstance(x, dict):
            t = _normalize_task(x)
            if t:
                out.append(t)
    return out


def _write_list(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge(
    existing: list[dict[str, Any]],
    seeded: list[dict[str, Any]],
    *,
    wipe_collab: bool,
    replace: bool,
) -> list[dict[str, Any]]:
    if replace:
        return list(seeded)
    base = [t for t in existing if not _is_collab(t)] if wipe_collab else list(existing)
    by_id = {str(t.get("id")): t for t in base}
    for t in seeded:
        by_id[str(t["id"])] = t
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in base:
        tid = str(t.get("id"))
        if tid in by_id and tid not in seen:
            merged.append(by_id[tid])
            seen.add(tid)
    for t in seeded:
        tid = str(t["id"])
        if tid not in seen:
            merged.append(t)
            seen.add(tid)
    return merged


def _seed_one(
    path: Path,
    seeded: list[dict[str, Any]],
    *,
    wipe_collab: bool,
    replace: bool,
    label: str,
) -> None:
    existing = _read_list(path)
    if path.is_file() and not path.with_suffix(".json.bak-before-collab").is_file():
        path.with_suffix(".json.bak-before-collab").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    merged = _merge(existing, seeded, wipe_collab=wipe_collab, replace=replace)
    _write_list(path, merged)
    collab_n = sum(1 for t in merged if _is_collab(t))
    print(f"OK [{label}] total={len(merged)} collab={collab_n}")
    print(f"     {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed collab tasks into quadrant_tasks")
    ap.add_argument(
        "--edition",
        choices=("dev", "release", "both"),
        default="dev",
        help="dev=仓库 data；release=正式版 %%LOCALAPPDATA%%\\YCZH-TOA3；both=两边都写",
    )
    ap.add_argument(
        "--replace",
        action="store_true",
        help="Replace entire tasks.json with seed only (destructive)",
    )
    ap.add_argument(
        "--wipe-collab",
        action="store_true",
        help="Remove existing collab-* / [协作] tasks before merge",
    )
    args = ap.parse_args()

    if not SEED.is_file():
        print(f"FAIL: missing seed {SEED}")
        return 1

    raw = json.loads(SEED.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("FAIL: seed must be a JSON array")
        return 1

    seeded: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        t = _normalize_task(item)
        if t:
            seeded.append(t)

    targets: list[tuple[str, Path]] = []
    if args.edition in ("dev", "both"):
        targets.append(("dev", _dev_tasks_path()))
    if args.edition in ("release", "both"):
        targets.append(("release", _release_tasks_path()))

    for label, path in targets:
        _seed_one(
            path,
            seeded,
            wipe_collab=args.wipe_collab,
            replace=args.replace,
            label=label,
        )

    try:
        from services.collab_board import sync_board_to_user_copies

        synced = sync_board_to_user_copies(BOARD_MD if BOARD_MD.is_file() else None)
        if synced:
            print(f"OK [board] synced Markdown → shared/collab ({synced.name})")
        else:
            print("WARN [board] OPS-02-协作任务说明.md not found; notepad open may fail on 正式版")
    except Exception as exc:
        print(f"WARN [board] sync skipped: {exc}")

    print("→ 正式版：顶栏办公 → 四象限任务（离开再进一次刷新）")
    print("→ 记事本：更多 → 打开协作任务表（可读描述）")
    print("→ 无终端备选：资源管理器复制 collab_tasks.json 覆盖上面的 tasks.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
