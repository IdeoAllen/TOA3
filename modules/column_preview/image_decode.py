# -*- coding: utf-8 -*-
"""桌面预览/图标共用的图片解码（Qt + Pillow 兜底，适配冻结包）。"""
from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QImageReader, QPixmap

_THUMB_CACHE: OrderedDict[tuple[str, int, int], QPixmap] = OrderedDict()
_THUMB_CACHE_MAX = 160


def load_image_via_pil(path: Path, *, max_edge: int = 4096) -> QPixmap:
    """Pillow 兜底（冻结包 Qt imageformats 插件偶发找不到时仍可预览）。"""
    try:
        from PIL import Image, ImageOps
    except Exception:
        return QPixmap()
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if max(im.size) > max_edge:
                im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            data = im.tobytes("raw", im.mode)
            w, h = im.size
            fmt = (
                QImage.Format.Format_RGBA8888
                if im.mode == "RGBA"
                else QImage.Format.Format_RGB888
            )
            qimg = QImage(data, w, h, fmt).copy()
            if qimg.isNull():
                return QPixmap()
            return QPixmap.fromImage(qimg)
    except Exception:
        return QPixmap()


def load_image_as_displayed(path: Path, *, max_edge: int = 4096) -> QPixmap:
    """解码为 1× 像素缓冲（不设 DPR）；Qt 失败则 Pillow。"""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and (size.width() > max_edge or size.height() > max_edge):
        if size.width() >= size.height():
            factor = max_edge / max(1, size.width())
        else:
            factor = max_edge / max(1, size.height())
        reader.setScaledSize(
            QSize(
                max(1, int(size.width() * factor)),
                max(1, int(size.height() * factor)),
            )
        )
    img = reader.read()
    if not img.isNull():
        return QPixmap.fromImage(img)
    return load_image_via_pil(path, max_edge=max_edge)


def _thumb_cache_key(path: Path, max_edge: int) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
        key_path = os.path.normcase(str(path.resolve()))
        return (key_path, int(max_edge), int(st.st_mtime_ns))
    except OSError:
        return None


def load_image_thumb(path: Path, *, max_edge: int = 512) -> QPixmap | None:
    """缩略图物理像素 pixmap（不设 DPR）；按路径+mtime 缓存，供图标模式复用。"""
    key = _thumb_cache_key(path, max_edge)
    if key is not None and key in _THUMB_CACHE:
        _THUMB_CACHE.move_to_end(key)
        return _THUMB_CACHE[key]
    pm = load_image_as_displayed(path, max_edge=max_edge)
    if pm.isNull():
        return None
    if key is not None:
        _THUMB_CACHE[key] = pm
        while len(_THUMB_CACHE) > _THUMB_CACHE_MAX:
            _THUMB_CACHE.popitem(last=False)
    return pm
