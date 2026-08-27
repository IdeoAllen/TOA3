# -*- coding: utf-8 -*-
"""批量重命名服务。"""
from __future__ import annotations

import re
from pathlib import Path


def preview_rename(
    folder: str,
    *,
    pattern: str = "*",
    prefix: str = "",
    suffix: str = "",
    find: str = "",
    replace: str = "",
    start_index: int = 1,
) -> list[tuple[Path, Path]]:
    root = Path(folder)
    if not root.is_dir():
        return []
    files = sorted([p for p in root.glob(pattern) if p.is_file()])
    out: list[tuple[Path, Path]] = []
    idx = start_index
    for p in files:
        stem, ext = p.stem, p.suffix
        name = stem
        if find:
            name = name.replace(find, replace)
        if "{n}" in prefix or "{n}" in suffix:
            new_stem = f"{prefix.replace('{n}', str(idx))}{name}{suffix.replace('{n}', str(idx))}"
        else:
            new_stem = f"{prefix}{name}{suffix}"
        new_stem = re.sub(r'[<>:"/\\|?*]', "_", new_stem)
        dest = p.with_name(new_stem + ext)
        if dest != p:
            out.append((p, dest))
        idx += 1
    return out


def apply_rename(pairs: list[tuple[Path, Path]]) -> tuple[int, list[str]]:
    ok = 0
    errors: list[str] = []
    for src, dst in pairs:
        try:
            if dst.exists():
                errors.append(f"目标已存在: {dst.name}")
                continue
            src.rename(dst)
            ok += 1
        except OSError as e:
            errors.append(f"{src.name}: {e}")
    return ok, errors
