# -*- coding: utf-8 -*-
"""班级交付目录 → Word 封面大纲贴图 + Excel 层级图片统计（TOA2 DirectoryCheckerApp 逻辑）。"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image

LogFn = Callable[[str, bool], None]
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")


@dataclass
class DeliveryReportContext:
    selected_dir: str
    base_dir_name: str

    @classmethod
    def from_root(cls, root: str | Path) -> DeliveryReportContext:
        path = Path(root).resolve()
        if not path.is_dir():
            raise ValueError(f"根路径不是目录: {path}")
        return cls(selected_dir=str(path), base_dir_name=path.name)


def _log(log: LogFn | None, message: str, *, error: bool = False) -> None:
    if log:
        log(message, error)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _set_paragraph_bottom_border(paragraph, color="1F4E79", size=18) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _add_cover_spacer(doc, height_pt: float) -> None:
    from docx.shared import Pt

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(0)
    spacer.paragraph_format.line_spacing = Pt(height_pt)


def _parse_project_info(base_dir_name: str) -> dict[str, str]:
    parts = [part.strip() for part in base_dir_name.split("-") if part.strip()]
    info = {
        "project_code": parts[0] if parts else base_dir_name,
        "project_name": base_dir_name,
        "location": "",
        "start_date": "",
        "end_date": "",
        "version": "",
    }
    if len(parts) >= 2:
        info["project_name"] = parts[1]
    if len(parts) >= 3:
        info["location"] = parts[2]
    if len(parts) >= 4:
        info["start_date"] = parts[3]
    if len(parts) >= 5:
        info["end_date"] = parts[4]
    if "简化版" in base_dir_name:
        info["version"] = "简化版"
    elif "完整版" in base_dir_name:
        info["version"] = "完整版"
    return info


def _add_delivery_cover_page(doc, ctx: DeliveryReportContext) -> None:
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_BREAK, WD_PARAGRAPH_ALIGNMENT
    from docx.shared import Inches, Pt, RGBColor

    project = _parse_project_info(ctx.base_dir_name)
    report_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    report_no = datetime.now().strftime("%Y%m%d%H%M%S")

    _add_cover_spacer(doc, 36)

    org_para = doc.add_paragraph()
    org_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    org_para.paragraph_format.space_after = Pt(18)
    org_run = org_para.add_run("培训交付中心")
    org_run.font.name = "微软雅黑"
    org_run.font.size = Pt(14)
    org_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    org_run.bold = True

    title_para = doc.add_paragraph()
    title_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    title_para.paragraph_format.space_after = Pt(10)
    title_run = title_para.add_run("项  目  交  付  报  告")
    title_run.font.name = "微软雅黑"
    title_run.font.size = Pt(32)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    subtitle_para = doc.add_paragraph()
    subtitle_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    subtitle_para.paragraph_format.space_after = Pt(24)
    subtitle_run = subtitle_para.add_run("PROJECT DELIVERY REPORT")
    subtitle_run.font.name = "Arial"
    subtitle_run.font.size = Pt(11)
    subtitle_run.font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)

    divider_para = doc.add_paragraph()
    divider_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    divider_para.paragraph_format.space_after = Pt(28)
    _set_paragraph_bottom_border(divider_para)

    project_para = doc.add_paragraph()
    project_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    project_para.paragraph_format.space_after = Pt(36)
    project_run = project_para.add_run(ctx.base_dir_name)
    project_run.font.name = "微软雅黑"
    project_run.font.size = Pt(16)
    project_run.font.bold = True
    project_run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    info_rows = [
        ("报告编号", report_no),
        ("项目编号", project["project_code"]),
        ("项目名称", project["project_name"]),
        ("交付地点", project["location"] or "—"),
        (
            "交付周期",
            f"{project['start_date']} 至 {project['end_date']}"
            if project["start_date"]
            else "—",
        ),
        ("报告版本", project["version"] or "标准版"),
        ("报告类型", "项目交付确认报告"),
        ("生成时间", report_time),
        ("交付目录", ctx.selected_dir),
    ]

    info_table = doc.add_table(rows=len(info_rows), cols=2)
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for index, (label, value) in enumerate(info_rows):
        row_cells = info_table.rows[index].cells
        for cell in row_cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

        label_para = row_cells[0].paragraphs[0]
        label_para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
        label_run = label_para.add_run(f"{label}：")
        label_run.font.name = "微软雅黑"
        label_run.font.size = Pt(11)
        label_run.font.bold = True
        label_run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

        value_para = row_cells[1].paragraphs[0]
        value_para.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
        value_run = value_para.add_run(value)
        value_run.font.name = "微软雅黑"
        value_run.font.size = Pt(11)
        value_run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    for row in info_table.rows:
        row.cells[0].width = Inches(1.4)
        row.cells[1].width = Inches(4.8)

    _add_cover_spacer(doc, 24)

    footer_para = doc.add_paragraph()
    footer_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    footer_para.paragraph_format.space_before = Pt(12)
    footer_run = footer_para.add_run("内部交付文档 · 仅供项目验收与归档使用")
    footer_run.font.name = "微软雅黑"
    footer_run.font.size = Pt(10)
    footer_run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    # 分页符须接在封面最后一行，勿另起空段（否则会多出一页空白）
    footer_run.add_break(WD_BREAK.PAGE)


def export_word_report(
    ctx: DeliveryReportContext,
    out_path: str | Path,
    log: LogFn | None = None,
) -> Path:
    """导出 Word：封面 + 大纲层级 + 图片等比嵌入。"""
    try:
        import docx
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
        from docx.shared import Inches, Pt
    except ImportError as exc:
        raise ImportError("需要 python-docx：pip install python-docx") from exc

    path = _unique_path(Path(out_path))
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = docx.Document()
    exported_sections = 0

    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(10)
    style.paragraph_format.space_after = Pt(3)

    for level in range(1, 10):
        heading_style = doc.styles[f"Heading {level}"]
        heading_style.paragraph_format.page_break_before = False
        heading_style.paragraph_format.space_after = Pt(3)

    _add_delivery_cover_page(doc, ctx)
    _log(log, "开始导出 Word 文档…")

    def get_heading_level(dir_path: str) -> int:
        rel_path = os.path.relpath(dir_path, ctx.selected_dir)
        if rel_path == ".":
            return 1
        return min(rel_path.count(os.sep) + 1, 9)

    def list_image_files(dir_path: str) -> list[str]:
        try:
            return sorted(
                os.path.join(dir_path, name)
                for name in os.listdir(dir_path)
                if name.lower().endswith(IMAGE_EXTENSIONS)
            )
        except OSError:
            return []

    def is_valid_image(img_path: str) -> bool:
        try:
            if not os.path.isfile(img_path) or os.path.getsize(img_path) == 0:
                return False
            with Image.open(img_path) as img:
                img.load()
                return img.width > 0 and img.height > 0
        except Exception:
            return False

    def get_valid_image_files(dir_path: str) -> list[str]:
        return [p for p in list_image_files(dir_path) if is_valid_image(p)]

    def get_picture_size(img_path: str, max_width=Inches(6.0), max_height=Inches(7.2)):
        with Image.open(img_path) as img:
            width_px, height_px = img.size
        if width_px <= 0 or height_px <= 0:
            raise ValueError("无效图片尺寸")
        width = max_width
        height = width * height_px / width_px
        if height > max_height:
            height = max_height
            width = height * width_px / height_px
        return width, height

    def get_embeddable_files(dir_path: str) -> list[str]:
        all_image_files = list_image_files(dir_path)
        image_files = get_valid_image_files(dir_path)
        embeddable_files: list[str] = []
        if all_image_files and not image_files:
            _log(log, f"跳过无效图片目录: {dir_path}")
        for img_path in image_files:
            try:
                get_picture_size(img_path)
                embeddable_files.append(img_path)
            except Exception as e:
                _log(
                    log,
                    f"无法嵌入图片: {os.path.basename(img_path)} ({e})",
                    error=True,
                )
        return embeddable_files

    def add_directory_heading(dir_path: str, keep_with_content: bool) -> None:
        dir_name = os.path.basename(dir_path)
        heading = doc.add_heading(level=get_heading_level(dir_path))
        heading.paragraph_format.page_break_before = False
        heading.paragraph_format.space_after = Pt(3)
        if keep_with_content:
            heading.paragraph_format.keep_with_next = True
        heading_run = heading.add_run("📁 " + dir_name)
        heading_run.font.name = "微软雅黑"
        heading_run.bold = True

    def process_directory(dir_path: str) -> None:
        nonlocal exported_sections
        is_root = os.path.normpath(dir_path) == os.path.normpath(ctx.selected_dir)
        embeddable_files = get_embeddable_files(dir_path)

        if not is_root:
            add_directory_heading(dir_path, bool(embeddable_files))

        if embeddable_files:
            exported_sections += 1
            path_para = doc.add_paragraph(f"路径: {dir_path}")
            path_para.paragraph_format.space_after = Pt(3)
            if not is_root:
                path_para.paragraph_format.keep_with_next = True

            for index, img_path in enumerate(embeddable_files):
                picture_width, picture_height = get_picture_size(img_path)
                paragraph = doc.add_paragraph()
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                paragraph.paragraph_format.space_before = Pt(3)
                paragraph.paragraph_format.space_after = Pt(3)
                if index == 0:
                    paragraph.paragraph_format.keep_with_next = True
                run = paragraph.add_run()
                run.add_picture(img_path, width=picture_width, height=picture_height)
                caption = doc.add_paragraph(
                    f"文件名: {os.path.basename(img_path)}",
                    style="List Bullet",
                )
                caption.paragraph_format.space_after = Pt(
                    6 if index < len(embeddable_files) - 1 else 3
                )

        subdirs: list[str] = []
        try:
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                if os.path.isdir(item_path):
                    subdirs.append(item_path)
        except OSError:
            pass

        for subdir in sorted(subdirs):
            process_directory(subdir)

    process_directory(ctx.selected_dir)

    if exported_sections == 0:
        doc.add_paragraph("所选目录及其子目录中未发现图片文件。")

    doc.save(str(path))
    _log(log, f"Word 文档已成功导出到: {path}")
    return path


def export_excel_report(
    ctx: DeliveryReportContext,
    out_path: str | Path,
    log: LogFn | None = None,
) -> Path:
    """导出 Excel：层级路径 + 图片总数(含子目录) + 状态。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as exc:
        raise ImportError("需要 openpyxl：pip install openpyxl") from exc

    path = _unique_path(Path(out_path))
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "目录统计"

    headers = ["层级路径", "图片总数(含子目录)", "状态"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, name="微软雅黑")

    _log(log, "开始扫描目录结构(递归统计图片)…")

    dir_tree: dict[str, list[str]] = defaultdict(list)
    all_dirs: set[str] = set()
    dir_stats: dict[str, tuple[int, bool]] = {}

    for root, dirs, _files in os.walk(ctx.selected_dir):
        all_dirs.add(root)
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            dir_tree[root].append(dir_path)
            all_dirs.add(dir_path)

    def count_images(dir_path: str) -> tuple[int, bool]:
        if dir_path in dir_stats:
            return dir_stats[dir_path]

        total = 0
        exists = os.path.exists(dir_path)

        if exists:
            try:
                for file in os.listdir(dir_path):
                    if file.lower().endswith(IMAGE_EXTENSIONS):
                        total += 1
                for subdir in dir_tree.get(dir_path, []):
                    sub_total, _ = count_images(subdir)
                    total += sub_total
            except PermissionError:
                exists = False

        dir_stats[dir_path] = (total, exists)
        return (total, exists)

    for dir_path in all_dirs:
        count_images(dir_path)

    def get_level(dir_path: str) -> int:
        return dir_path[len(ctx.selected_dir) :].count(os.sep)

    sorted_dirs = sorted(all_dirs, key=lambda x: (get_level(x), x.lower()))

    for dir_path in sorted_dirs:
        rel_path = os.path.relpath(dir_path, ctx.selected_dir)
        if rel_path == ".":
            display_path = ctx.base_dir_name
        else:
            parts = [ctx.base_dir_name] + rel_path.split(os.sep)
            display_path = "/".join(parts)

        total_images, exists = dir_stats[dir_path]
        status = "正常" if exists else "缺失"
        row = [display_path, total_images if exists else "N/A", status]
        ws.append(row)

        font = Font(color="FF0000", name="微软雅黑") if not exists else Font(name="微软雅黑")
        for col in range(1, len(row) + 1):
            ws.cell(row=ws.max_row, column=col).font = font

    from services.excel_export import autofit_workbook

    autofit_workbook(wb)
    wb.save(str(path))
    _log(log, f"Excel 统计已成功导出到: {path}")
    return path


def export_all_reports(
    ctx: DeliveryReportContext,
    out_dir: str | Path,
    log: LogFn | None = None,
) -> tuple[Path, Path]:
    """在同一输出目录导出 Word + Excel。"""
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    word_path = export_word_report(
        ctx,
        base / f"{ctx.base_dir_name}_交付报告.docx",
        log,
    )
    excel_path = export_excel_report(
        ctx,
        base / f"{ctx.base_dir_name}_目录统计.xlsx",
        log,
    )
    return word_path, excel_path
