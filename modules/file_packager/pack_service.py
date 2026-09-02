# -*- coding: utf-8 -*-
"""文件打包归档：预览清单 → 规范命名 zip → 可选相对路径清单。"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


PRESETS: dict[str, tuple[str, str]] = {
    "general": ("通用归档", "归档_{date}"),
    "class_deliver": ("班级交付", "班级交付_{class}_{date}"),
}


@dataclass
class PackEntry:
    abs_path: Path
    arcname: str
    is_dir: bool = False
    empty_dir: bool = False


@dataclass
class PackResult:
    zip_path: str = ""
    manifest_path: str = ""
    file_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines: list[str] = []
        if self.zip_path:
            lines.append(f"已打包 {self.file_count} 个文件 → {self.zip_path}")
        if self.manifest_path:
            lines.append(f"清单 → {self.manifest_path}")
        for e in self.errors:
            lines.append(f"  ! {e}")
        return "\n".join(lines) if lines else "无输出。"


def stamp_date() -> str:
    return datetime.now().strftime("%Y%m%d")


def stamp_full() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def render_zip_name(template: str, *, class_name: str = "") -> str:
    name = (template or "归档_{date}").replace("{date}", stamp_date())
    name = name.replace("{class}", (class_name or "未命名班级").strip() or "未命名班级")
    name = name.replace("{time}", stamp_full())
    if not name.lower().endswith(".zip"):
        name += ".zip"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name


def collect_entries(
    roots: list[str | Path],
    *,
    exclude_suffixes: list[str] | None = None,
    skip_empty_dirs: bool = True,
) -> list[PackEntry]:
    suffixes = {
        s.lower() if s.startswith(".") else f".{s.lower()}"
        for s in (exclude_suffixes or [])
        if s.strip()
    }
    entries: list[PackEntry] = []
    seen_arc: set[str] = set()

    for root in [Path(r) for r in roots if r]:
        if not root.exists():
            continue
        if root.is_file():
            if suffixes and root.suffix.lower() in suffixes:
                continue
            arc = root.name
            if arc not in seen_arc:
                seen_arc.add(arc)
                entries.append(PackEntry(root, arc, is_dir=False))
            continue

        base_name = root.name
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            arc = f"{base_name}/{rel}"
            if p.is_dir():
                try:
                    has_child = any(p.iterdir())
                except OSError:
                    has_child = True
                if has_child:
                    continue
                if skip_empty_dirs:
                    continue
                arc_dir = arc if arc.endswith("/") else arc + "/"
                if arc_dir not in seen_arc:
                    seen_arc.add(arc_dir)
                    entries.append(PackEntry(p, arc_dir, is_dir=True, empty_dir=True))
                continue
            if suffixes and p.suffix.lower() in suffixes:
                continue
            if arc not in seen_arc:
                seen_arc.add(arc)
                entries.append(PackEntry(p, arc, is_dir=False))

    return entries


def write_zip(
    entries: list[PackEntry],
    zip_path: str | Path,
    *,
    write_manifest: bool = False,
) -> PackResult:
    result = PackResult()
    out = Path(zip_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".partial")
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass

    selected = list(entries)
    if not selected:
        result.errors.append("没有可打包的条目")
        return result

    written_files = 0
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for e in selected:
                if e.is_dir:
                    name = e.arcname if e.arcname.endswith("/") else e.arcname + "/"
                    zf.writestr(name, b"")
                    continue
                try:
                    zf.write(e.abs_path, arcname=e.arcname)
                    written_files += 1
                except OSError as err:
                    result.errors.append(f"{e.arcname}: {err}")
        if written_files == 0 and not any(e.is_dir for e in selected):
            tmp.unlink(missing_ok=True)
            if not result.errors:
                result.errors.append("没有成功写入的文件")
            return result
        tmp.replace(out)
        result.zip_path = str(out)
        result.file_count = written_files
    except Exception as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        result.errors.append(str(e))
        return result

    if write_manifest and result.zip_path:
        man = out.with_name(out.stem + "_清单.txt")
        lines = [e.arcname for e in selected]
        man.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        result.manifest_path = str(man)
    return result
