# -*- coding: utf-8 -*-
"""图片调整服务：旋转 / 翻转 / 缩放 / 亮度对比度。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def ensure_pillow() -> Tuple[bool, str]:
    try:
        import PIL  # noqa: F401

        return True, ""
    except ImportError:
        return False, "未安装 Pillow，请执行: pip install Pillow"


@dataclass
class AdjustOptions:
    rotate: int = 0  # 0 / 90 / 180 / 270
    flip_h: bool = False
    flip_v: bool = False
    resize_w: int = 0  # 0 = 不改
    resize_h: int = 0
    brightness: float = 1.0  # 1.0 = 原样
    contrast: float = 1.0


def apply_adjust(src: str | Path, options: AdjustOptions):
    """返回处理后的 PIL.Image（调用方负责 close）。"""
    ok, msg = ensure_pillow()
    if not ok:
        raise RuntimeError(msg)

    from PIL import Image, ImageEnhance, ImageOps

    img = Image.open(str(src))
    img.load()
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    rot = int(options.rotate) % 360
    if rot == 90:
        img = img.transpose(Image.Transpose.ROTATE_90)
    elif rot == 180:
        img = img.transpose(Image.Transpose.ROTATE_180)
    elif rot == 270:
        img = img.transpose(Image.Transpose.ROTATE_270)

    if options.flip_h:
        img = ImageOps.mirror(img)
    if options.flip_v:
        img = ImageOps.flip(img)

    rw, rh = int(options.resize_w), int(options.resize_h)
    if rw > 0 or rh > 0:
        ow, oh = img.size
        nw = rw if rw > 0 else ow
        nh = rh if rh > 0 else oh
        if rw > 0 and rh <= 0:
            nh = max(1, int(oh * (rw / float(ow))))
        elif rh > 0 and rw <= 0:
            nw = max(1, int(ow * (rh / float(oh))))
        img = img.resize((max(1, nw), max(1, nh)), Image.Resampling.LANCZOS)

    b = float(options.brightness)
    c = float(options.contrast)
    if abs(b - 1.0) > 1e-3:
        img = ImageEnhance.Brightness(img).enhance(b)
    if abs(c - 1.0) > 1e-3:
        img = ImageEnhance.Contrast(img).enhance(c)
    return img


def save_adjusted(
    src: str | Path,
    output_dir: str | Path,
    options: AdjustOptions,
    *,
    suffix: str = "_adjusted",
) -> str:
    from PIL import Image  # noqa: F401 — used if convert needed below

    img = apply_adjust(src, options)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem
    ext = Path(src).suffix.lower() or ".png"
    if ext not in IMAGE_EXTENSIONS:
        ext = ".png"
    dest = out_dir / f"{stem}{suffix}{ext}"
    save_kw: dict = {}
    if ext in (".jpg", ".jpeg"):
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        save_kw["quality"] = 95
    img.save(str(dest), **save_kw)
    img.close()
    return str(dest)


def preview_to_file(
    src: str | Path,
    preview_path: str | Path,
    options: AdjustOptions,
    *,
    max_side: int = 1600,
) -> str:
    """写出预览图（缩小），返回路径。"""
    from PIL import Image

    img = apply_adjust(src, options)
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
    dest = Path(preview_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        bg.save(str(dest), "PNG")
        bg.close()
    else:
        img.convert("RGB").save(str(dest), "PNG")
    img.close()
    return str(dest)
