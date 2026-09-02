# -*- coding: utf-8 -*-
"""目录递归相对路径列表 + 空目录/命名启发式检查。"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_SPACE_RE = re.compile(r"\s")
_SPECIAL_RE = re.compile(r'[<>:"|?*]')
_LEADING_DOT_RE = re.compile(r"^\.")
_CN_OR_ASCII = re.compile(r"^[\w\u4e00-\u9fff\-_. ()（）【】\[\]]+$", re.UNICODE)


@dataclass
class InspectReport:
    root: str
    empty_dirs: list[str] = field(default_factory=list)
    naming_issues: list[str] = field(default_factory=list)
    dir_paths: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    ext_counts: dict[str, int] = field(default_factory=dict)
    dir_count: int = 0
    file_count: int = 0
    include_dirs: bool = True

    def relative_paths(self, *, include_dirs: bool | None = None) -> list[str]:
        """相对路径列表；include_dirs=False 时仅文件。"""
        want_dirs = self.include_dirs if include_dirs is None else include_dirs
        if want_dirs:
            return list(self.dir_paths) + list(self.file_paths)
        return list(self.file_paths)

    def ext_stats_lines(self) -> list[str]:
        """按数量降序的类型统计行。"""
        items = sorted(self.ext_counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
        return [f"  {ext}: {n}" for ext, n in items]

    def as_text(self, *, include_dirs: bool | None = None) -> str:
        want_dirs = self.include_dirs if include_dirs is None else include_dirs
        paths = self.relative_paths(include_dirs=want_dirs)
        lines = [
            "目录透视报告",
            f"根目录: {self.root}",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"子目录数: {self.dir_count} · 文件数: {self.file_count}",
            f"列表含目录: {'是' if want_dirs else '否（仅文件）'}",
            f"列表条数: {len(paths)}",
            "",
            f"【文件类型统计】共 {len(self.ext_counts)} 种",
        ]
        stats = self.ext_stats_lines()
        if stats:
            lines.extend(stats)
        else:
            lines.append("  （无文件）")
        lines.append("")
        lines.append("【相对路径】")
        if paths:
            lines.extend(paths)
        else:
            lines.append("（无）")
        lines.append("")
        lines.append(f"【空目录】共 {len(self.empty_dirs)} 个")
        if self.empty_dirs:
            lines.extend(f"  - {p}" for p in self.empty_dirs)
        else:
            lines.append("  （无）")
        lines.append("")
        lines.append(f"【命名问题】共 {len(self.naming_issues)} 个")
        if self.naming_issues:
            lines.extend(f"  - {p}" for p in self.naming_issues)
        else:
            lines.append("  （无）")
        return "\n".join(lines)


def _rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _naming_reason(name: str) -> str | None:
    if not name:
        return "空名称"
    if _SPACE_RE.search(name) and name != name.strip():
        return "首尾空白"
    if name.strip() != name:
        return "首尾空白"
    if "  " in name:
        return "连续空格"
    if _SPECIAL_RE.search(name):
        return "含非法字符 <>:\"|?*"
    if _LEADING_DOT_RE.match(name):
        return "以点开头"
    if len(name) > 80:
        return "名称过长(>80)"
    if not _CN_OR_ASCII.match(name):
        return "含非常规字符"
    return None


def inspect_directory(root: str | Path, *, include_dirs: bool = True) -> InspectReport:
    base = Path(root)
    report = InspectReport(root=str(base.resolve() if base.exists() else base), include_dirs=include_dirs)
    if not base.is_dir():
        report.naming_issues.append(f"根路径不是目录: {base}")
        return report

    dirs: list[str] = []
    files: list[str] = []
    ext_counter: Counter[str] = Counter()
    for path in sorted(base.rglob("*"), key=lambda p: (not p.is_dir(), p.as_posix().lower())):
        rel = _rel(path, base)
        if not rel:
            continue
        if path.is_dir():
            dirs.append(rel)
            report.dir_count += 1
            try:
                if not any(path.iterdir()):
                    report.empty_dirs.append(rel)
            except OSError as e:
                report.naming_issues.append(f"{rel}: 无法读取 ({e})")
            reason = _naming_reason(path.name)
            if reason:
                report.naming_issues.append(f"{rel}: {reason}")
        elif path.is_file():
            files.append(rel)
            report.file_count += 1
            ext = path.suffix.lower() or "(无扩展名)"
            ext_counter[ext] += 1
            reason = _naming_reason(path.name)
            if reason:
                report.naming_issues.append(f"{rel}: {reason}")

    report.dir_paths = dirs
    report.file_paths = files
    report.ext_counts = dict(ext_counter)
    return report


def export_report(text: str, out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def export_report_word(report: InspectReport, out_path: str | Path) -> Path:
    """导出 Word 报告。"""
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as exc:
        raise ImportError("需要 python-docx：pip install python-docx") from exc

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    paths = report.relative_paths()
    doc = Document()
    title = doc.add_heading("目录透视报告", level=0)
    title.runs[0].font.size = Pt(18)
    doc.add_paragraph(f"根目录：{report.root}")
    doc.add_paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_paragraph(f"子目录数：{report.dir_count} · 文件数：{report.file_count}")
    doc.add_paragraph(f"列表含目录：{'是' if report.include_dirs else '否（仅文件）'}")
    doc.add_heading(f"文件类型统计（{len(report.ext_counts)} 种）", level=1)
    stats = report.ext_stats_lines()
    if stats:
        for line in stats:
            doc.add_paragraph(line.strip(), style="List Bullet")
    else:
        doc.add_paragraph("（无文件）")
    doc.add_heading(f"相对路径（{len(paths)}）", level=1)
    if paths:
        for p in paths:
            doc.add_paragraph(p, style="List Bullet")
    else:
        doc.add_paragraph("（无）")
    doc.add_heading(f"空目录（{len(report.empty_dirs)}）", level=1)
    if report.empty_dirs:
        for p in report.empty_dirs:
            doc.add_paragraph(p, style="List Bullet")
    else:
        doc.add_paragraph("（无）")
    doc.add_heading(f"命名问题（{len(report.naming_issues)}）", level=1)
    if report.naming_issues:
        for p in report.naming_issues:
            doc.add_paragraph(p, style="List Bullet")
    else:
        doc.add_paragraph("（无）")
    doc.save(str(path))
    return path


def export_report_excel(report: InspectReport, out_path: str | Path) -> Path:
    """导出 Excel：相对路径为主表（文本格式），附类型统计 / 空目录 / 命名问题。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
        from openpyxl.cell.cell import Cell
    except ImportError as exc:
        raise ImportError("需要 openpyxl：pip install openpyxl") from exc

    def _text_cell(cell: Cell, value: object) -> None:
        """强制文本，避免 01-xxx / = 被 Excel 当数字或公式。"""
        cell.value = "" if value is None else str(value)
        cell.number_format = "@"
        cell.alignment = Alignment(wrap_text=False, vertical="center")

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    paths = report.relative_paths()
    wb = Workbook()

    # —— 主表：相对路径（打开即见）——
    ws_paths = wb.active
    ws_paths.title = "相对路径"
    ws_paths.append(["相对路径", "类型"])
    for c in ws_paths[1]:
        c.font = Font(bold=True)
        c.number_format = "@"
    if report.include_dirs:
        for p in report.dir_paths:
            ws_paths.append([p, "目录"])
    for p in report.file_paths:
        ws_paths.append([p, "文件"])
    for row in ws_paths.iter_rows(min_row=2, max_col=2):
        for cell in row:
            _text_cell(cell, cell.value)

    # —— 摘要 ——
    ws = wb.create_sheet("摘要", 1)
    ws["A1"] = "目录透视报告"
    ws["A1"].font = Font(bold=True, size=14)
    rows_meta = [
        ("根目录", report.root),
        ("子目录数", report.dir_count),
        ("文件数", report.file_count),
        ("列表含目录", "是" if report.include_dirs else "否"),
        ("列表条数", len(paths)),
        ("空目录数", len(report.empty_dirs)),
        ("命名问题数", len(report.naming_issues)),
        ("文件类型种数", len(report.ext_counts)),
    ]
    for i, (k, v) in enumerate(rows_meta, start=2):
        _text_cell(ws.cell(i, 1), k)
        cell_v = ws.cell(i, 2)
        if isinstance(v, int):
            cell_v.value = v
        else:
            _text_cell(cell_v, v)

    ws_ext = wb.create_sheet("文件类型")
    ws_ext.append(["扩展名", "数量"])
    for c in ws_ext[1]:
        c.font = Font(bold=True)
    for ext, n in sorted(report.ext_counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        r = ws_ext.max_row + 1
        _text_cell(ws_ext.cell(r, 1), ext)
        ws_ext.cell(r, 2).value = int(n)

    ws2 = wb.create_sheet("空目录")
    ws2.append(["相对路径"])
    ws2[1][0].font = Font(bold=True)
    for p in report.empty_dirs:
        r = ws2.max_row + 1
        _text_cell(ws2.cell(r, 1), p)

    ws3 = wb.create_sheet("命名问题")
    ws3.append(["说明"])
    ws3[1][0].font = Font(bold=True)
    for p in report.naming_issues:
        r = ws3.max_row + 1
        _text_cell(ws3.cell(r, 1), p)

    from services.excel_export import autofit_workbook

    autofit_workbook(wb)
    wb.save(str(path))
    return path
