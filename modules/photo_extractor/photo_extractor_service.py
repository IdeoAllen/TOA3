# -*- coding: utf-8 -*-
"""
照片提取服务（自 TOA2 PhotoExtractor 迁移）。

支持复制、长图、Word、PPT、PDF 导出。
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass
class ExtractResult:
    copied: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    output_path: str = ""
    mode: str = "copy"

    @property
    def summary(self) -> str:
        lines = [
            f"模式 {self.mode}：成功 {len(self.copied)}，失败 {len(self.failed)}。",
            f"输出：{self.output_path}",
        ]
        for err in self.failed[:12]:
            lines.append(f"  ! {err}")
        if len(self.failed) > 12:
            lines.append(f"  …另有 {len(self.failed) - 12} 项失败")
        return "\n".join(lines)


def collect_photos(directory: str | Path, *, recursive: bool = True) -> list[str]:
    root = Path(directory)
    if not root.is_dir():
        return []
    photos: list[str] = []
    it: Iterable[Path] = root.rglob("*") if recursive else root.glob("*")
    for p in it:
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            photos.append(str(p))
    photos.sort(key=lambda x: Path(x).stat().st_ctime if Path(x).exists() else x)
    return photos


def list_subdirectories(directory: str | Path) -> list[str]:
    """一级子目录（班级文件夹下的小组 / 日期夹等）。"""
    root = Path(directory)
    if not root.is_dir():
        return []
    dirs = sorted(
        str(p) for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    return dirs


def collect_photos_from_dirs(dirs: list[str | Path], *, recursive: bool = True) -> list[str]:
    photos: list[str] = []
    seen: set[str] = set()
    for d in dirs:
        for p in collect_photos(d, recursive=recursive):
            if p not in seen:
                seen.add(p)
                photos.append(p)
    return photos


def get_photo_creation_date(photo_path: str) -> str:
    try:
        with Image.open(photo_path) as image:
            exif = image.getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == "DateTimeOriginal":
                        return str(value).replace(":", "-", 2)
        ctime = Path(photo_path).stat().st_ctime
        return datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        logger.warning("读取创建日期失败 %s: %s", photo_path, exc)
        return "未知日期"


def generate_word(photos: list[str], output_path: str | Path) -> bool:
    try:
        from docx import Document
        from docx.shared import Inches
    except ImportError:
        logger.error("生成 Word 需要 python-docx")
        return False
    try:
        doc = Document()
        for i, photo_path in enumerate(photos):
            doc.add_paragraph(f"照片 {i + 1}: {Path(photo_path).name}")
            doc.add_paragraph(f"创建日期: {get_photo_creation_date(photo_path)}")
            doc.add_picture(photo_path, width=Inches(6))
            if i < len(photos) - 1:
                doc.add_page_break()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
        return True
    except Exception as exc:
        logger.error("生成 Word 失败: %s", exc)
        return False


def generate_ppt(photos: list[str], output_path: str | Path) -> bool:
    try:
        from pptx import Presentation
    except ImportError:
        logger.error("生成 PPT 需要 python-pptx")
        return False
    try:
        prs = Presentation()
        blank = prs.slide_layouts[6]
        for photo_path in photos:
            slide = prs.slides.add_slide(blank)
            name = Path(photo_path).name
            date_s = get_photo_creation_date(photo_path)
            if slide.shapes.title is not None:
                slide.shapes.title.text = f"{name} - {date_s}"
            pic = slide.shapes.add_picture(
                photo_path,
                left=None,
                top=None,
                width=int(prs.slide_width * 0.8),
            )
            pic.left = (prs.slide_width - pic.width) // 2
            pic.top = (prs.slide_height - pic.height) // 2
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out))
        return True
    except Exception as exc:
        logger.error("生成 PPT 失败: %s", exc)
        return False


def generate_pdf(photos: list[str], output_path: str | Path) -> bool:
    try:
        from io import BytesIO

        import PyPDF2
        from PyPDF2 import PdfWriter
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        logger.error("生成 PDF 需要 PyPDF2 与 reportlab")
        return False
    try:
        writer = PdfWriter()
        for photo_path in photos:
            try:
                img = Image.open(photo_path)
                img_byte_arr = BytesIO()
                if img.mode == "RGBA":
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    background.save(img_byte_arr, format="PDF")
                else:
                    img.save(img_byte_arr, format="PDF")
                img_byte_arr.seek(0)
                reader = PyPDF2.PdfReader(img_byte_arr)
                writer.add_page(reader.pages[0])
                info_page = BytesIO()
                c = canvas.Canvas(info_page, pagesize=letter)
                c.setFont("Helvetica", 12)
                c.drawString(100, 750, f"照片: {Path(photo_path).name}")
                c.drawString(100, 730, f"创建时间: {get_photo_creation_date(photo_path)}")
                c.save()
                info_page.seek(0)
                info_reader = PyPDF2.PdfReader(info_page)
                writer.add_page(info_reader.pages[0])
            except Exception as exc:
                logger.error("添加照片到 PDF 失败 %s: %s", photo_path, exc)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as output_file:
            writer.write(output_file)
        return True
    except Exception as exc:
        logger.error("生成 PDF 失败: %s", exc)
        return False


def generate_long_image(photos: list[str], output_path: str | Path) -> bool:
    """TOA2 长图逻辑：缩略后垂直拼接。"""
    try:
        images: list[Image.Image] = []
        max_width = 0
        total_height = 0
        padding = 20
        for photo_path in photos:
            try:
                img = Image.open(photo_path)
                img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                images.append(img)
                max_width = max(max_width, img.width)
                total_height += img.height + padding
            except Exception as exc:
                logger.error("处理图片失败 %s: %s", photo_path, exc)
        if not images:
            return False
        result = Image.new(
            "RGB",
            (max_width + 2 * padding, total_height + padding),
            (255, 255, 255),
        )
        current_y = padding
        for img in images:
            x = (max_width - img.width) // 2 + padding
            result.paste(img, (x, current_y))
            current_y += img.height + padding
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(out))
        return True
    except Exception as exc:
        logger.error("生成长图失败: %s", exc)
        return False


def extract_photos(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    mode: str = "copy",
    recursive: bool = True,
) -> ExtractResult:
    """
    mode:
      - copy: 复制到输出目录（扁平化，重名加序号）
      - long_image: 生成一张竖向长图
      - word / ppt / pdf: 生成对应文档（需可选依赖）
    """
    photos = collect_photos(source_dir, recursive=recursive)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    result = ExtractResult(mode=mode, output_path=str(out_root))
    if not photos:
        result.failed.append("目录内未找到图片")
        return result

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_modes = {
        "word": (".docx", generate_word),
        "ppt": (".pptx", generate_ppt),
        "pdf": (".pdf", generate_pdf),
    }
    if mode in doc_modes:
        ext, fn = doc_modes[mode]
        dest = out_root / f"photos_{stamp}{ext}"
        if fn(photos, dest):
            result.copied.append(str(dest))
            result.output_path = str(dest)
        else:
            result.failed.append(f"{mode} 生成失败（检查是否安装对应依赖）")
        return result

    if mode == "long_image":
        dest = out_root / f"photos_long_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        if generate_long_image(photos, dest):
            result.copied.append(str(dest))
            result.output_path = str(dest)
        else:
            result.failed.append("长图生成失败")
        return result

    used_names: set[str] = set()
    for src in photos:
        name = Path(src).name
        stem, suffix = Path(name).stem, Path(name).suffix
        dest_name = name
        n = 1
        while dest_name.lower() in used_names or (out_root / dest_name).exists():
            dest_name = f"{stem}_{n}{suffix}"
            n += 1
        used_names.add(dest_name.lower())
        dest = out_root / dest_name
        try:
            shutil.copy2(src, dest)
            result.copied.append(str(dest))
        except OSError as exc:
            result.failed.append(f"{name}: {exc}")
    result.output_path = str(out_root)
    return result
