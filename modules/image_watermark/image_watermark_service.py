# -*- coding: utf-8 -*-
"""通用加水印服务：文字 / Logo，对齐 TOA 通用水印能力（非水印相机业务）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
POSITIONS = (
    "center",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "tile",
)
COLOR_PRESETS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (220, 40, 40),
    "blue": (40, 100, 220),
    "yellow": (240, 200, 40),
    "gray": (160, 160, 160),
}


def ensure_pillow() -> Tuple[bool, str]:
    try:
        import PIL  # noqa: F401

        return True, ""
    except ImportError:
        return False, "未安装 Pillow，请执行: pip install Pillow"


@dataclass
class WatermarkOptions:
    text: str = "WATERMARK"
    opacity: int = 40  # 0–100
    position: str = "bottom-right"
    font_size: int = 0  # 0 = 按图宽自适应
    color: str = "white"  # preset name or #RRGGBB
    rotation: int = 0  # degrees, counter-clockwise for text layer
    logo_path: str = ""  # optional PNG/JPG logo; empty = text only
    logo_scale: int = 18  # logo width as % of image width


def collect_images(path: str | Path, *, recursive: bool = True) -> List[str]:
    p = Path(path)
    if p.is_file():
        return [str(p)] if p.suffix.lower() in IMAGE_EXTENSIONS else []
    if not p.is_dir():
        return []
    it = p.rglob("*") if recursive else p.glob("*")
    out = sorted(str(x) for x in it if x.is_file() and x.suffix.lower() in IMAGE_EXTENSIONS)
    return out


def _parse_color(color: str) -> tuple[int, int, int]:
    raw = (color or "white").strip().lower()
    if raw in COLOR_PRESETS:
        return COLOR_PRESETS[raw]
    if raw.startswith("#") and len(raw) == 7:
        try:
            return int(raw[1:3], 16), int(raw[3:5], 16), int(raw[5:7], 16)
        except ValueError:
            pass
    return COLOR_PRESETS["white"]


def _anchor_positions(
    w: int,
    h: int,
    tw: int,
    th: int,
    pad: int,
    position: str,
) -> list[tuple[int, int]]:
    pos = (position or "bottom-right").lower()
    positions: list[tuple[int, int]] = []
    if pos == "center":
        positions.append(((w - tw) // 2, (h - th) // 2))
    elif pos == "top-left":
        positions.append((pad, pad))
    elif pos == "top-right":
        positions.append((w - tw - pad, pad))
    elif pos == "bottom-left":
        positions.append((pad, h - th - pad))
    elif pos == "tile":
        step_x = tw + pad * 4
        step_y = th + pad * 4
        y = pad
        row = 0
        while y < h:
            x = pad + (row % 2) * (step_x // 2)
            while x < w:
                positions.append((x, y))
                x += step_x
            y += step_y
            row += 1
    else:
        positions.append((w - tw - pad, h - th - pad))
    return positions


def _draw_text_layer(base_size, text: str, options: WatermarkOptions):
    from PIL import Image, ImageDraw, ImageFont

    w, h = base_size
    size = options.font_size if options.font_size > 0 else max(16, int(w * 0.045))
    try:
        font = ImageFont.truetype("msyh.ttc", size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except OSError:
            font = ImageFont.load_default()

    alpha = max(0, min(255, int(255 * (int(options.opacity) / 100.0))))
    rgb = _parse_color(options.color)
    fill = (*rgb, alpha)
    stroke = (0, 0, 0, min(255, alpha + 40)) if sum(rgb) > 380 else (255, 255, 255, min(255, alpha + 40))

    # 先画到紧凑层再旋转，避免平铺旋转扭曲整图
    measure = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(measure)
    bbox = mdraw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(8, size // 4)
    rot = int(options.rotation) % 360

    if rot == 0:
        overlay = measure
        draw = mdraw
        for x, y in _anchor_positions(w, h, tw, th, pad, options.position):
            draw.text((x, y), text, font=font, fill=fill, stroke_width=1, stroke_fill=stroke)
        return overlay

    # 旋转：生成单块文字层，按锚点贴到大图；tile 则网格贴
    chip_pad = max(4, size // 8)
    chip = Image.new("RGBA", (tw + chip_pad * 2, th + chip_pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(chip).text(
        (chip_pad - bbox[0], chip_pad - bbox[1]),
        text,
        font=font,
        fill=fill,
        stroke_width=1,
        stroke_fill=stroke,
    )
    chip = chip.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
    cw, ch = chip.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x, y in _anchor_positions(w, h, cw, ch, pad, options.position):
        overlay.alpha_composite(chip, (max(0, x), max(0, y)))
    return overlay


def _draw_logo_layer(base_size, options: WatermarkOptions):
    from PIL import Image

    logo_path = (options.logo_path or "").strip()
    if not logo_path or not Path(logo_path).is_file():
        return None
    w, h = base_size
    logo = Image.open(logo_path).convert("RGBA")
    target_w = max(16, int(w * max(5, min(60, int(options.logo_scale))) / 100.0))
    scale = target_w / float(max(1, logo.width))
    target_h = max(8, int(logo.height * scale))
    logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    alpha = max(0, min(255, int(255 * (int(options.opacity) / 100.0))))
    if alpha < 255:
        r, g, b, a = logo.split()
        a = a.point(lambda v: int(v * alpha / 255))
        logo = Image.merge("RGBA", (r, g, b, a))
    rot = int(options.rotation) % 360
    if rot:
        logo = logo.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)
    lw, lh = logo.size
    pad = max(8, target_w // 10)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x, y in _anchor_positions(w, h, lw, lh, pad, options.position):
        overlay.alpha_composite(logo, (max(0, x), max(0, y)))
    return overlay


def apply_text_watermark(src: str | Path, options: WatermarkOptions):
    ok, msg = ensure_pillow()
    if not ok:
        raise RuntimeError(msg)
    from PIL import Image

    img = Image.open(str(src)).convert("RGBA")
    layers: list = []
    logo_layer = _draw_logo_layer(img.size, options)
    if logo_layer is not None:
        layers.append(logo_layer)
    text = (options.text or "").strip()
    if text:
        layers.append(_draw_text_layer(img.size, text, options))
    if not layers:
        raise RuntimeError("请填写水印文字或选择 Logo 图片")
    out = img
    for layer in layers:
        out = Image.alpha_composite(out, layer)
    return out.convert("RGB")


def watermark_one(
    src: str | Path,
    output_dir: str | Path,
    options: WatermarkOptions,
) -> str:
    img = apply_text_watermark(src, options)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{Path(src).stem}_wm.jpg"
    img.save(str(dest), "JPEG", quality=92)
    img.close()
    return str(dest)


def watermark_batch(
    source: str | Path,
    output_dir: str | Path,
    options: WatermarkOptions,
    *,
    recursive: bool = True,
) -> Tuple[int, int, List[str], str]:
    paths = collect_images(source, recursive=recursive)
    ok = fail = 0
    failed: List[str] = []
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for p in paths:
        try:
            watermark_one(p, out, options)
            ok += 1
        except Exception as exc:
            logger.warning("watermark fail %s: %s", p, exc)
            fail += 1
            failed.append(p)
    return ok, fail, failed, str(out)
