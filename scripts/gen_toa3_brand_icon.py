# -*- coding: utf-8 -*-
"""生成 TOA3 蓝色品牌图标（带 3.0 角标，与 2.0 区分）。"""
from __future__ import annotations

from pathlib import Path


def generate_toa3_brand_assets(root: Path | None = None, *, force: bool = True) -> dict[str, Path]:
    """写出 avatars/logo.png、resources/icons/brand_logo.png、app_logo.ico（多尺寸）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise RuntimeError("需要 Pillow 生成 TOA3 图标") from e

    if root is None:
        root = Path(__file__).resolve().parents[1]

    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    blue = (37, 99, 235, 255)  # #2563EB
    blue_dark = (29, 78, 216, 255)
    white = (255, 255, 255, 255)

    margin = 28
    d.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=96,
        fill=blue,
        outline=blue_dark,
        width=6,
    )

    font_big = None
    for fp in (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
    ):
        try:
            font_big = ImageFont.truetype(fp, 156)
            break
        except Exception:
            continue
    if font_big is None:
        font_big = ImageFont.load_default()

    text = "TOA"
    bb = d.textbbox((0, 0), text, font=font_big)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(
        ((size - tw) / 2 - bb[0], (size - th) / 2 - bb[1] - 28),
        text,
        fill=white,
        font=font_big,
    )

    # 右下角 3.0 角标（加大，任务栏小尺寸仍可辨）
    badge_r = 96
    bx, by = size - margin - 20, size - margin - 20
    d.ellipse(
        [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
        fill=(255, 255, 255, 255),
        outline=blue_dark,
        width=10,
    )
    font_badge = None
    for fp in (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
    ):
        try:
            font_badge = ImageFont.truetype(fp, 88)
            break
        except Exception:
            continue
    if font_badge is None:
        font_badge = font_big
    badge = "3.0"
    bb2 = d.textbbox((0, 0), badge, font=font_badge)
    tw2, th2 = bb2[2] - bb2[0], bb2[3] - bb2[1]
    d.text(
        (bx - tw2 / 2 - bb2[0], by - th2 / 2 - bb2[1]),
        badge,
        fill=blue,
        font=font_badge,
    )

    out: dict[str, Path] = {}
    avatars = root / "avatars"
    icons = root / "resources" / "icons"
    avatars.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    png_paths = [
        avatars / "logo.png",
        icons / "brand_logo.png",
        icons / "app_logo.png",
    ]
    for p in png_paths:
        if force or not p.is_file():
            img.save(p, "PNG")
            out[str(p.name)] = p

    # ICO：直接从主图按 sizes 嵌入多档（勿用 append_images，Pillow 会只写出 16×16）
    ico = icons / "app_logo.ico"
    avatar_ico = avatars / "logo.ico"
    if force or not ico.is_file():
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico, format="ICO", sizes=sizes)
        out["app_logo.ico"] = ico
        img.save(avatar_ico, format="ICO", sizes=sizes)
        out["avatars/logo.ico"] = avatar_ico

    return out


if __name__ == "__main__":
    paths = generate_toa3_brand_assets(force=True)
    for k, v in paths.items():
        print("wrote", v)
