# -*- coding: utf-8 -*-
"""生成 TOA3 品牌图标：正式版（蓝 + 3.0）与开发版（橙 + DEV）。"""
from __future__ import annotations

from pathlib import Path


def _load_font(size: int):
    from PIL import ImageFont

    for fp in (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
    ):
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_brand_icon(
    *,
    fill_rgb: tuple[int, int, int],
    outline_rgb: tuple[int, int, int],
    badge_text: str,
    badge_fill: tuple[int, int, int] = (255, 255, 255, 255),
    badge_text_rgb: tuple[int, int, int] | None = None,
):
    from PIL import Image, ImageDraw

    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    fill = (*fill_rgb, 255)
    outline = (*outline_rgb, 255)
    white = (255, 255, 255, 255)
    badge_text_rgb = badge_text_rgb or fill_rgb

    margin = 28
    d.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=96,
        fill=fill,
        outline=outline,
        width=6,
    )

    font_big = _load_font(156)
    text = "TOA"
    bb = d.textbbox((0, 0), text, font=font_big)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(
        ((size - tw) / 2 - bb[0], (size - th) / 2 - bb[1] - 28),
        text,
        fill=white,
        font=font_big,
    )

    badge_r = 96
    bx, by = size - margin - 20, size - margin - 20
    d.ellipse(
        [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
        fill=badge_fill,
        outline=outline,
        width=10,
    )
    font_badge = _load_font(72 if len(badge_text) > 3 else 88)
    bb2 = d.textbbox((0, 0), badge_text, font=font_badge)
    tw2, th2 = bb2[2] - bb2[0], bb2[3] - bb2[1]
    d.text(
        (bx - tw2 / 2 - bb2[0], by - th2 / 2 - bb2[1]),
        badge_text,
        fill=(*badge_text_rgb, 255),
        font=font_badge,
    )
    return img


def _write_icon_set(
    img,
    *,
    avatars: Path,
    icons: Path,
    avatar_stem: str,
    icon_stem: str,
    force: bool,
    out: dict[str, Path],
) -> None:
    png_targets = [
        (avatars / f"{avatar_stem}.png", f"avatars/{avatar_stem}.png"),
        (icons / f"brand_{icon_stem}.png", f"icons/brand_{icon_stem}.png"),
        (icons / f"app_{icon_stem}.png", f"icons/app_{icon_stem}.png"),
    ]
    for path, key in png_targets:
        if force or not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, "PNG")
            out[key] = path

    ico_targets = [
        (icons / f"app_{icon_stem}.ico", f"icons/app_{icon_stem}.ico"),
        (avatars / f"{avatar_stem}.ico", f"avatars/{avatar_stem}.ico"),
    ]
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for path, key in ico_targets:
        if force or not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, format="ICO", sizes=sizes)
            out[key] = path


def generate_toa3_brand_assets(root: Path | None = None, *, force: bool = True) -> dict[str, Path]:
    """写出正式版（蓝 + 3.0）与开发版（橙 + DEV）图标。"""
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:
        raise RuntimeError("需要 Pillow 生成 TOA3 图标") from e

    if root is None:
        root = Path(__file__).resolve().parents[1]

    avatars = root / "avatars"
    icons = root / "resources" / "icons"
    avatars.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    release_img = _draw_brand_icon(
        fill_rgb=(37, 99, 235),
        outline_rgb=(29, 78, 216),
        badge_text="3.0",
        badge_text_rgb=(37, 99, 235),
    )
    dev_img = _draw_brand_icon(
        fill_rgb=(234, 88, 12),
        outline_rgb=(194, 65, 12),
        badge_text="DEV",
        badge_text_rgb=(234, 88, 12),
    )

    out: dict[str, Path] = {}
    _write_icon_set(
        release_img,
        avatars=avatars,
        icons=icons,
        avatar_stem="logo",
        icon_stem="logo",
        force=force,
        out=out,
    )
    _write_icon_set(
        dev_img,
        avatars=avatars,
        icons=icons,
        avatar_stem="logo_dev",
        icon_stem="logo_dev",
        force=force,
        out=out,
    )
    return out


if __name__ == "__main__":
    paths = generate_toa3_brand_assets(force=True)
    for k, v in paths.items():
        print("wrote", k, "->", v)
