# -*- coding: utf-8 -*-
"""批量重命名服务：预览、冲突检测、应用、撤销。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


PRESETS: dict[str, dict[str, str | int]] = {
    "photo": {
        "label": "照片交付",
        "pattern": "*",
        "prefix": "照片_{n}_",
        "suffix": "",
        "find": "",
        "replace": "",
        "start": 1,
    },
    "courseware": {
        "label": "课件序号",
        "pattern": "*",
        "prefix": "{n:02d}_",
        "suffix": "",
        "find": "",
        "replace": "",
        "start": 1,
    },
}


@dataclass
class RenamePlan:
    pairs: list[tuple[Path, Path]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)


def _format_token(template: str, idx: int) -> str:
    """支持 {n} 与简单 {n:02d}。"""
    out = template.replace("{n:02d}", f"{idx:02d}").replace("{n}", str(idx))
    return out


def preview_rename(
    folder: str,
    *,
    pattern: str = "*",
    prefix: str = "",
    suffix: str = "",
    find: str = "",
    replace: str = "",
    start_index: int = 1,
) -> RenamePlan:
    root = Path(folder)
    plan = RenamePlan()
    if not root.is_dir():
        return plan
    files = sorted([p for p in root.glob(pattern) if p.is_file()])
    idx = start_index
    dest_names: dict[str, Path] = {}
    for p in files:
        stem, ext = p.stem, p.suffix
        name = stem
        if find:
            name = name.replace(find, replace)
        new_stem = f"{_format_token(prefix, idx)}{name}{_format_token(suffix, idx)}"
        new_stem = re.sub(r'[<>:"/\\|?*]', "_", new_stem)
        dest = p.with_name(new_stem + ext)
        idx += 1
        if dest == p:
            continue
        plan.pairs.append((p, dest))
        key = dest.name.lower()
        if key in dest_names:
            plan.conflicts.append(f"重名冲突: {dest.name} ← {dest_names[key].name} / {p.name}")
        else:
            dest_names[key] = p
        if dest.exists() and dest.resolve() != p.resolve():
            plan.conflicts.append(f"目标已存在: {dest.name}")
    return plan


def apply_rename(pairs: list[tuple[Path, Path]]) -> tuple[int, list[str], list[tuple[str, str]]]:
    """返回 (成功数, 错误, 成功映射 abs old→new 供撤销)。"""
    ok = 0
    errors: list[str] = []
    mapping: list[tuple[str, str]] = []
    for src, dst in pairs:
        try:
            if dst.exists():
                errors.append(f"目标已存在: {dst.name}")
                continue
            src.rename(dst)
            mapping.append((str(src), str(dst)))
            ok += 1
        except OSError as e:
            errors.append(f"{src.name}: {e}")
    return ok, errors, mapping


def save_undo_map(path: Path, mapping: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"old": a, "new": b} for a, b in mapping]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_undo_map(path: Path) -> list[tuple[Path, Path]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[tuple[Path, Path]] = []
    for row in data:
        old, new = row.get("old"), row.get("new")
        if old and new:
            out.append((Path(new), Path(old)))  # 撤销：new → old
    return out


def apply_undo(pairs: list[tuple[Path, Path]]) -> tuple[int, list[str]]:
    ok = 0
    errors: list[str] = []
    for src, dst in pairs:
        try:
            if not src.exists():
                errors.append(f"找不到: {src.name}")
                continue
            if dst.exists():
                errors.append(f"原名已被占用: {dst.name}")
                continue
            src.rename(dst)
            ok += 1
        except OSError as e:
            errors.append(f"{src.name}: {e}")
    return ok, errors
