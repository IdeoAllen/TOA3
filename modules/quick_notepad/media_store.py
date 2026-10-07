# -*- coding: utf-8 -*-
"""记事媒体库：统一写入 images/；分批落盘；同盘优先 move。"""
from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from services.storage_paths import module_data_dir

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg"}


def images_dir() -> Path:
    d = module_data_dir("quick_notepad", create=True) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def attachments_dir() -> Path:
    d = module_data_dir("quick_notepad", create=True) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _same_volume(a: Path, b: Path) -> bool:
    try:
        a_r, b_r = a.resolve(), b.resolve()
        if os.name == "nt":
            return a_r.drive.upper() == b_r.drive.upper() and bool(a_r.drive)
        return os.stat(a_r).st_dev == os.stat(b_r).st_dev
    except OSError:
        return False


def _unique_dest(suffix: str) -> Path:
    suf = suffix if suffix.startswith(".") else f".{suffix}"
    if suf.lower() not in _IMAGE_SUFFIXES:
        suf = ".png"
    return images_dir() / f"{uuid.uuid4().hex}{suf.lower()}"


def store_image_file(
    src: Path,
    *,
    max_width: int = 960,
    prefer_move: bool = True,
) -> Path:
    """入库单张图片。同盘且 prefer_move 时先尝试 move（再按需缩放重写）。"""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    suffix = src.suffix.lower() or ".png"
    dest = _unique_dest(suffix)
    img = QImage(str(src))
    if img.isNull():
        if prefer_move and _same_volume(src, dest):
            try:
                shutil.move(str(src), str(dest))
                return dest
            except OSError:
                pass
        shutil.copy2(src, dest)
        return dest

    needs_scale = max_width > 0 and img.width() > max_width
    if needs_scale:
        img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
        if not img.save(str(dest)):
            shutil.copy2(src, dest)
        elif prefer_move and _same_volume(src, dest):
            try:
                src.unlink(missing_ok=True)
            except OSError:
                pass
        return dest

    if prefer_move and _same_volume(src, dest):
        try:
            shutil.move(str(src), str(dest))
            return dest
        except OSError:
            pass
    if not img.save(str(dest)):
        shutil.copy2(src, dest)
    return dest


def store_qimage(img: QImage, *, max_width: int = 960, suffix: str = ".png") -> Path | None:
    if img is None or img.isNull():
        return None
    out = img
    if max_width > 0 and out.width() > max_width:
        out = out.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    dest = _unique_dest(suffix)
    if not out.save(str(dest)):
        return None
    return dest


def store_images_batched(
    sources: Sequence[Path | QImage],
    *,
    batch_size: int = 4,
    max_width: int = 960,
    prefer_move: bool = True,
    on_batch: Callable[[int, int], None] | None = None,
) -> list[Path]:
    """多图分批写盘，避免一次塞大量像素卡 UI。返回成功路径列表。"""
    items = list(sources or [])
    total = len(items)
    if total == 0:
        return []
    batch_size = max(1, int(batch_size))
    out: list[Path] = []
    for start in range(0, total, batch_size):
        chunk = items[start : start + batch_size]
        for item in chunk:
            try:
                if isinstance(item, QImage):
                    path = store_qimage(item, max_width=max_width)
                    if path is not None:
                        out.append(path)
                else:
                    out.append(
                        store_image_file(
                            Path(item), max_width=max_width, prefer_move=prefer_move
                        )
                    )
            except OSError:
                continue
        if on_batch is not None:
            on_batch(min(start + len(chunk), total), total)
    return out


def path_as_uri(path: Path) -> str:
    return Path(path).resolve().as_uri()
