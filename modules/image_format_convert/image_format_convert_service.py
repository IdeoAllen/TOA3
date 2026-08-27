# -*- coding: utf-8 -*-
"""图片格式转换服务：PNG / JPG / WEBP / 多页 PDF。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Sequence, Tuple

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".gif"}
FORMATS = ("PNG", "JPG", "WEBP", "PDF")


def ensure_pillow() -> Tuple[bool, str]:
    try:
        import PIL  # noqa: F401

        return True, ""
    except ImportError:
        return False, "未安装 Pillow，请执行: pip install Pillow"


def collect_images(paths: Sequence[str | Path], *, recursive: bool = True) -> List[str]:
    out: List[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            out.append(str(p))
        elif p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            out.extend(
                sorted(str(x) for x in it if x.is_file() and x.suffix.lower() in IMAGE_EXTENSIONS)
            )
    # 去重保序
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _to_rgb(img):
    from PIL import Image

    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def convert_one(
    src: str | Path,
    output_dir: str | Path,
    fmt: str,
    *,
    quality: int = 90,
) -> str:
    ok, msg = ensure_pillow()
    if not ok:
        raise RuntimeError(msg)
    from PIL import Image

    fmt_u = (fmt or "PNG").upper()
    if fmt_u == "JPEG":
        fmt_u = "JPG"
    img = Image.open(str(src))
    img.load()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem

    if fmt_u == "PNG":
        dest = out_dir / f"{stem}.png"
        if img.mode not in ("RGB", "RGBA", "L", "P"):
            img = img.convert("RGBA")
        img.save(str(dest), "PNG")
    elif fmt_u == "JPG":
        dest = out_dir / f"{stem}.jpg"
        _to_rgb(img).save(str(dest), "JPEG", quality=max(1, min(100, int(quality))))
    elif fmt_u == "WEBP":
        dest = out_dir / f"{stem}.webp"
        save_img = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA")
        save_img.save(str(dest), "WEBP", quality=max(1, min(100, int(quality))))
    else:
        raise ValueError(f"单文件不支持格式 {fmt_u}（PDF 请走 batch）")
    img.close()
    return str(dest)


def convert_to_pdf(
    sources: Sequence[str | Path],
    output_path: str | Path,
    *,
    quality: int = 90,
) -> str:
    ok, msg = ensure_pillow()
    if not ok:
        raise RuntimeError(msg)
    from PIL import Image

    paths = [str(p) for p in sources]
    if not paths:
        raise ValueError("没有可转换的图片")
    pages = []
    for p in paths:
        im = Image.open(p)
        im.load()
        pages.append(_to_rgb(im))
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    first, rest = pages[0], pages[1:]
    # JPEG 质量影响嵌入；PDF 容器固定
    first.save(
        str(dest),
        "PDF",
        resolution=100.0,
        save_all=True,
        append_images=rest,
        quality=max(1, min(100, int(quality))),
    )
    for im in pages:
        im.close()
    return str(dest)


def convert_batch(
    sources: Sequence[str | Path],
    output_dir: str | Path,
    fmt: str,
    *,
    quality: int = 90,
    recursive: bool = True,
    pdf_name: str = "converted.pdf",
) -> Tuple[int, int, List[str], str]:
    """
    批量转换。PDF：多图合并为一个多页 PDF。
    返回 (成功数, 失败数, 失败路径, 输出提示路径)。
    """
    paths = collect_images(sources, recursive=recursive)
    if not paths:
        return 0, 0, [], str(output_dir)

    fmt_u = (fmt or "PNG").upper()
    if fmt_u == "JPEG":
        fmt_u = "JPG"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if fmt_u == "PDF":
        try:
            dest = convert_to_pdf(paths, out / pdf_name, quality=quality)
            return len(paths), 0, [], dest
        except Exception as exc:
            logger.error("PDF 转换失败: %s", exc)
            return 0, len(paths), list(paths), str(out)

    ok = fail = 0
    failed: List[str] = []
    for p in paths:
        try:
            convert_one(p, out, fmt_u, quality=quality)
            ok += 1
        except Exception as exc:
            logger.warning("convert fail %s: %s", p, exc)
            fail += 1
            failed.append(p)
    return ok, fail, failed, str(out)
