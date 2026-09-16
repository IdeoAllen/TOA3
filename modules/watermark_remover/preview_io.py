# -*- coding: utf-8 -*-
"""去水印预览 IO：大图限边解码，避免 UI 线程吃满幅像素。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QImageReader, QPixmap

# 标记画布显示上限（物理像素边长）
DISPLAY_MAX_EDGE = 2400
# 右侧实时效果预览处理上限（再降一档，保证跟手）
EFFECT_PREVIEW_MAX_EDGE = 1600


def probe_image_size(path: str | Path) -> tuple[int, int] | None:
    """只读尺寸，不解码全图。"""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        return int(size.width()), int(size.height())
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            if w > 0 and h > 0:
                return int(w), int(h)
    except Exception:
        pass
    return None


def load_display_pixmap(
    path: str | Path,
    *,
    max_edge: int = DISPLAY_MAX_EDGE,
) -> tuple[QPixmap, int, int]:
    """解码为预览用 pixmap；返回 (pixmap, 原图宽, 原图高)。

    超大图按 max_edge 等比缩小；坐标需乘 (orig/display) 映射回原图。
    """
    path = Path(path)
    orig = probe_image_size(path)
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
        pm = QPixmap.fromImage(img)
        ow = orig[0] if orig else pm.width()
        oh = orig[1] if orig else pm.height()
        return pm, ow, oh
    return _load_via_pil(path, max_edge=max_edge, orig=orig)


def _load_via_pil(
    path: Path,
    *,
    max_edge: int,
    orig: tuple[int, int] | None,
) -> tuple[QPixmap, int, int]:
    try:
        from PIL import Image, ImageOps
    except Exception:
        return QPixmap(), 0, 0
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            ow, oh = im.size
            if orig:
                ow, oh = orig
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
                return QPixmap(), ow, oh
            return QPixmap.fromImage(qimg), int(ow), int(oh)
    except Exception:
        return QPixmap(), 0, 0


def scale_boxes_to_orig(
    boxes: list[tuple[int, int, int, int]],
    *,
    scale: float,
) -> list[tuple[int, int, int, int]]:
    if scale == 1.0 or not boxes:
        return list(boxes)
    out: list[tuple[int, int, int, int]] = []
    for x, y, w, h in boxes:
        out.append(
            (
                int(round(x * scale)),
                int(round(y * scale)),
                max(1, int(round(w * scale))),
                max(1, int(round(h * scale))),
            )
        )
    return out


def scale_boxes_from_orig(
    boxes: list[tuple[int, int, int, int]],
    *,
    scale_to_orig: float,
) -> list[tuple[int, int, int, int]]:
    if scale_to_orig <= 0 or scale_to_orig == 1.0 or not boxes:
        return list(boxes)
    inv = 1.0 / scale_to_orig
    return scale_boxes_to_orig(boxes, scale=inv)
