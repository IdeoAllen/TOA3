# -*- coding: utf-8 -*-
"""生成 TOA3 品牌图标：正式版（圆形徽标）与开发版（徽标 + 橙色 DEV 角标）。

母版（唯一来源，换 Logo 只换这里）：
  resources/brand/toa_logo_master.png    方形图：上部圆形徽标 + 下方「TOA 智能办公助手」
  resources/brand/toa_lockup_master.png  横版：徽标 + 文字（运营台/下载页用，见 cloud/）
"""
from __future__ import annotations

from pathlib import Path

MASTER_REL = Path("resources") / "brand" / "toa_logo_master.png"

# 母版 1024×1024 中圆形徽标的位置（圆心 / 半径，像素）
DISC_CENTER = (512, 453)
DISC_RADIUS = 254

OUT_SIZE = 512
DEV_ORANGE = (234, 88, 12)


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


def _emblem_from_master(master: Path):
    """裁出圆形徽标，圆外透明（4× 超采样抗锯齿遮罩）。"""
    from PIL import Image, ImageDraw

    src = Image.open(master).convert("RGBA")
    cx, cy = DISC_CENTER
    r = DISC_RADIUS + 2
    crop = src.crop((cx - r, cy - r, cx + r, cy + r))

    ss = 4
    big = 2 * r * ss
    inset = 6 * ss  # 吃掉母版白底在圆边的抗锯齿像素，深色背景下不留白圈
    mask_big = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask_big).ellipse([inset, inset, big - 1 - inset, big - 1 - inset], fill=255)
    mask = mask_big.resize(crop.size, Image.LANCZOS)
    crop.putalpha(mask)
    return crop.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)


def _with_dev_badge(img):
    from PIL import ImageDraw

    out = img.copy()
    d = ImageDraw.Draw(out)
    size = out.size[0]
    w, h = int(size * 0.56), int(size * 0.22)
    x0 = (size - w) // 2
    y0 = size - h - 6
    d.rounded_rectangle(
        [x0, y0, x0 + w, y0 + h],
        radius=h // 2,
        fill=(*DEV_ORANGE, 255),
        outline=(255, 255, 255, 255),
        width=8,
    )
    font = _load_font(int(h * 0.62))
    text = "DEV"
    bb = d.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text((x0 + (w - tw) / 2 - bb[0], y0 + (h - th) / 2 - bb[1]), text, fill=(255, 255, 255, 255), font=font)
    return out


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
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for path, key in ico_targets:
        if force or not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, format="ICO", sizes=sizes)
            out[key] = path


def generate_toa3_brand_assets(root: Path | None = None, *, force: bool = True) -> dict[str, Path]:
    """由母版写出正式版与开发版图标（PNG + 多尺寸 ICO）。"""
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:
        raise RuntimeError("需要 Pillow 生成 TOA3 图标") from e

    if root is None:
        root = Path(__file__).resolve().parents[1]

    master = root / MASTER_REL
    if not master.is_file():
        raise FileNotFoundError(f"缺少品牌母版: {master}")

    avatars = root / "avatars"
    icons = root / "resources" / "icons"
    avatars.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    release_img = _emblem_from_master(master)
    dev_img = _with_dev_badge(release_img)

    out: dict[str, Path] = {}
    _write_icon_set(release_img, avatars=avatars, icons=icons, avatar_stem="logo", icon_stem="logo", force=force, out=out)
    _write_icon_set(dev_img, avatars=avatars, icons=icons, avatar_stem="logo_dev", icon_stem="logo_dev", force=force, out=out)
    return out


def generate_cloud_brand_assets(root: Path | None = None) -> dict[str, Path]:
    """运营台 / 下载页品牌资源（cloud/admin/brand/ · cloud/download/）。"""
    from PIL import Image
    import numpy as np

    if root is None:
        root = Path(__file__).resolve().parents[1]
    emblem = _emblem_from_master(root / MASTER_REL)
    brand_dir = root / "cloud" / "admin" / "brand"
    brand_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    for name, size in (("toa-mark.png", 256), ("favicon-32.png", 32), ("apple-touch-icon.png", 180)):
        p = brand_dir / name
        emblem.resize((size, size), Image.LANCZOS).save(p, "PNG")
        out[f"cloud/admin/brand/{name}"] = p
    ico = brand_dir / "favicon.ico"
    emblem.save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    out["cloud/admin/brand/favicon.ico"] = ico

    lockup = Image.open(root / "resources" / "brand" / "toa_lockup_master.png").convert("RGB")
    a = np.asarray(lockup).astype(int)
    ys, xs = np.nonzero(a.min(axis=2) < 235)
    pad = 12
    box = (
        max(0, xs.min() - pad),
        max(0, ys.min() - pad),
        min(lockup.width, xs.max() + pad),
        min(lockup.height, ys.max() + pad),
    )
    tight = lockup.crop(box)
    h = 160
    tight = tight.resize((round(tight.width * h / tight.height), h), Image.LANCZOS)
    lp = root / "cloud" / "download" / "toa-lockup.png"
    lp.parent.mkdir(parents=True, exist_ok=True)
    tight.save(lp, "PNG", optimize=True)
    out["cloud/download/toa-lockup.png"] = lp
    return out


if __name__ == "__main__":
    paths = generate_toa3_brand_assets(force=True)
    paths.update(generate_cloud_brand_assets())
    for k, v in paths.items():
        print("wrote", k, "->", v)
