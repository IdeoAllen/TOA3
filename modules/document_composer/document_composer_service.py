# -*- coding: utf-8 -*-
"""图片文件夹 → DOCX / PPTX / ZIP 回退。"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def list_images(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录: {root}")
    files = [p for p in sorted(root.iterdir()) if p.is_file() and p.suffix.lower() in _IMAGE_EXTS]
    return files


def compose_from_images(
    folder: str | Path,
    out_dir: str | Path,
    *,
    prefer: str = "auto",
) -> Path:
    """
    prefer: auto | pdf | docx | pptx | zip
    auto: pdf > docx > pptx > zip
    """
    images = list_images(folder)
    if not images:
        raise FileNotFoundError("文件夹内没有支持的图片文件。")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = (prefer or "auto").lower()

    if mode in {"auto", "pdf"}:
        path = _try_pdf(images, out / f"compose_{stamp}.pdf")
        if path is not None:
            return path
        if mode == "pdf":
            raise RuntimeError("未安装 Pillow，无法生成 PDF。")

    if mode in {"auto", "docx"}:
        path = _try_docx(images, out / f"compose_{stamp}.docx")
        if path is not None:
            return path
        if mode == "docx":
            raise RuntimeError("未安装 python-docx，无法生成 DOCX。")

    if mode in {"auto", "pptx"}:
        path = _try_pptx(images, out / f"compose_{stamp}.pptx")
        if path is not None:
            return path
        if mode == "pptx":
            raise RuntimeError("未安装 python-pptx，无法生成 PPTX。")

    return _write_zip(images, out / f"compose_{stamp}.zip")


def compose_from_paths(
    image_paths: list[str | Path],
    out_dir: str | Path,
    *,
    prefer: str = "pdf",
) -> Path:
    """按指定图片路径列表合成（对标 TOA2 多选文件）。"""
    images = [Path(p) for p in image_paths if Path(p).is_file()]
    if not images:
        raise FileNotFoundError("没有有效的图片文件。")
    # 临时放入逻辑：直接调用底层
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = (prefer or "pdf").lower()
    if mode == "pdf":
        path = _try_pdf(images, out / f"compose_{stamp}.pdf")
        if path:
            return path
        raise RuntimeError("无法生成 PDF（需要 Pillow）")
    if mode in {"docx", "word"}:
        path = _try_docx(images, out / f"compose_{stamp}.docx")
        if path:
            return path
        raise RuntimeError("无法生成 DOCX")
    if mode in {"pptx", "ppt"}:
        path = _try_pptx(images, out / f"compose_{stamp}.pptx")
        if path:
            return path
        raise RuntimeError("无法生成 PPTX")
    return _write_zip(images, out / f"compose_{stamp}.zip")


def _try_pdf(images: list[Path], dest: Path) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    pil_images = []
    for img in images:
        try:
            im = Image.open(img)
            if im.mode != "RGB":
                im = im.convert("RGB")
            pil_images.append(im)
        except Exception:
            continue
    if not pil_images:
        return None
    first, rest = pil_images[0], pil_images[1:]
    first.save(str(dest), save_all=True, append_images=rest)
    return dest


def _try_docx(images: list[Path], dest: Path) -> Path | None:
    try:
        from docx import Document  # type: ignore
        from docx.shared import Inches  # type: ignore
    except ImportError:
        return None
    doc = Document()
    doc.add_heading("图片合成文档", level=1)
    for img in images:
        doc.add_paragraph(img.name)
        try:
            doc.add_picture(str(img), width=Inches(5.5))
        except Exception:
            doc.add_paragraph(f"（无法嵌入图片: {img.name}）")
    doc.save(str(dest))
    return dest


def _try_pptx(images: list[Path], dest: Path) -> Path | None:
    try:
        from pptx import Presentation  # type: ignore
        from pptx.util import Inches  # type: ignore
    except ImportError:
        return None
    prs = Presentation()
    blank = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[5]
    for img in images:
        slide = prs.slides.add_slide(blank)
        try:
            slide.shapes.add_picture(str(img), Inches(0.5), Inches(0.5), width=Inches(9))
        except Exception:
            box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(1))
            box.text_frame.text = f"无法嵌入: {img.name}"
    prs.save(str(dest))
    return dest


def _write_zip(images: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.txt",
            "未安装 python-docx / python-pptx，已打包原图。\n"
            + "\n".join(p.name for p in images)
            + "\n",
        )
        for img in images:
            zf.write(img, arcname=img.name)
    return dest
