# -*- coding: utf-8 -*-
"""Office 文档预览：结构化 Word/Excel/PPT + 纯文本回退。"""
from __future__ import annotations

import html
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_PREVIEW_MAX_CHARS = 48_000
_EXCEL_MAX_ROWS = 80
_EXCEL_MAX_COLS = 24
_PPT_MAX_SLIDES = 20
_WORD_MAX_BLOCKS = 400
_RTF_MAX_BYTES = 512_000

OFFICE_EXTENSIONS = frozenset(
    {
        ".docx",
        ".doc",
        ".xlsx",
        ".xlsm",
        ".xltx",
        ".xltm",
        ".xls",
        ".pptx",
        ".ppsx",
        ".ppt",
        ".pps",
        ".rtf",
    }
)

_EXT_KIND = {
    ".docx": "Word 文档",
    ".doc": "Word 97-2003",
    ".xlsx": "Excel 工作簿",
    ".xlsm": "Excel 宏工作簿",
    ".xltx": "Excel 模板",
    ".xltm": "Excel 宏模板",
    ".xls": "Excel 97-2003",
    ".pptx": "PowerPoint",
    ".ppsx": "PowerPoint 放映",
    ".ppt": "PowerPoint 97-2003",
    ".pps": "PowerPoint 放映 97-2003",
    ".rtf": "RTF 文档",
}

_WORD_EXT = frozenset({".docx", ".doc", ".rtf"})
_EXCEL_EXT = frozenset({".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"})
_PPT_EXT = frozenset({".pptx", ".ppsx", ".ppt", ".pps"})


@dataclass
class OfficeSheet:
    name: str
    rows: list[list[str]] = field(default_factory=list)
    truncated: bool = False


@dataclass
class OfficeSlide:
    index: int
    title: str = ""
    lines: list[str] = field(default_factory=list)


@dataclass
class OfficePreview:
    """family: word | excel | ppt | text。"""

    kind_label: str
    family: str
    plain: str = ""
    html_body: str = ""
    sheets: list[OfficeSheet] = field(default_factory=list)
    slides: list[OfficeSlide] = field(default_factory=list)
    note: str = ""


def is_office_preview_path(path: Path) -> bool:
    return path.suffix.lower() in OFFICE_EXTENSIONS


def office_kind_label(path: Path) -> str:
    return _EXT_KIND.get(path.suffix.lower(), "Office 文档")


def office_family(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _WORD_EXT:
        return "word"
    if ext in _EXCEL_EXT:
        return "excel"
    if ext in _PPT_EXT:
        return "ppt"
    return "text"


def read_office_preview(path: Path) -> tuple[str, str]:
    """兼容旧调用：返回 (类型标签, 纯文本)。"""
    preview = read_office_structured(path)
    return preview.kind_label, preview.plain or "（文档无可见文本）"


def read_office_structured(path: Path) -> OfficePreview:
    """结构化预览：Word→HTML，Excel→表，PPT→幻灯片卡片，失败回退纯文本。"""
    ext = path.suffix.lower()
    kind = office_kind_label(path)
    if ext == ".docx":
        return _structured_docx(path, kind)
    if ext == ".doc":
        return _structured_doc_legacy(path, kind)
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return _structured_xlsx(path, kind)
    if ext == ".xls":
        return _structured_xls(path, kind)
    if ext in {".pptx", ".ppsx"}:
        return _structured_pptx(path, kind)
    if ext in {".ppt", ".pps"}:
        return _structured_ppt_legacy(path, kind)
    if ext == ".rtf":
        return _structured_rtf(path, kind)
    raise ValueError(f"不支持的 Office 格式：{ext}")


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= _PREVIEW_MAX_CHARS:
        return text or "（文档无可见文本）"
    return text[:_PREVIEW_MAX_CHARS] + "\n\n…（已截断预览）"


def _cell_str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _wrap_word_html(body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        "<body style='font-family:Segoe UI,Microsoft YaHei,sans-serif;"
        "font-size:13px;line-height:1.55;margin:8px 10px;color:#1d1d1f;'>"
        f"{body}</body></html>"
    )


def _heading_level(style_name: str) -> int | None:
    s = style_name or ""
    m = re.search(r"(?:Heading|标题)\s*(\d)", s, re.I)
    if m:
        return max(1, min(3, int(m.group(1))))
    if "Heading" in s or "标题" in s:
        return 1
    if "Title" in s or s in {"标题", "文档标题"}:
        return 1
    return None


def _para_html_from_runs(para) -> str:
    parts: list[str] = []
    for run in para.runs:
        t = run.text or ""
        if not t:
            continue
        esc = html.escape(t).replace("\n", "<br/>")
        if getattr(run, "bold", False):
            esc = f"<b>{esc}</b>"
        if getattr(run, "italic", False):
            esc = f"<i>{esc}</i>"
        if getattr(run, "underline", False):
            esc = f"<u>{esc}</u>"
        parts.append(esc)
    if parts:
        return "".join(parts)
    return html.escape(para.text or "")


def _table_html(table, *, max_rows: int = 40) -> str:
    rows_html: list[str] = []
    for ri, row in enumerate(table.rows):
        if ri >= max_rows:
            rows_html.append(
                "<tr><td colspan='99' style='color:#888;'>…（表格行已省略）</td></tr>"
            )
            break
        cells = []
        for cell in row.cells:
            cells.append(
                f"<td style='border:1px solid #d0d5dd;padding:4px 6px;'>"
                f"{html.escape(cell.text.strip())}</td>"
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table style='border-collapse:collapse;margin:8px 0;width:100%;'>"
        + "".join(rows_html)
        + "</table>"
    )


def _structured_docx(path: Path, kind: str) -> OfficePreview:
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise RuntimeError("需要 python-docx：pip install python-docx") from exc

    doc = Document(str(path))
    body_parts: list[str] = []
    plain_lines: list[str] = []
    block_n = 0
    truncated = False

    for child in doc.element.body.iterchildren():
        if block_n >= _WORD_MAX_BLOCKS:
            truncated = True
            break
        tag = child.tag
        if tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = (para.text or "").strip()
            if not text:
                continue
            block_n += 1
            style = str(getattr(para.style, "name", "") or "")
            level = _heading_level(style)
            inner = _para_html_from_runs(para)
            if level:
                plain_lines.append(f"{'#' * level} {text}")
                body_parts.append(f"<h{level} style='margin:12px 0 6px;'>{inner}</h{level}>")
            else:
                plain_lines.append(text)
                body_parts.append(f"<p style='margin:4px 0;'>{inner}</p>")
        elif tag == qn("w:tbl"):
            table = Table(child, doc)
            block_n += 1
            plain_lines.append("[表格]")
            for row in table.rows[:40]:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    plain_lines.append("\t".join(cells))
            body_parts.append(_table_html(table))

    note = "正文过长，已截断预览" if truncated else ""
    if truncated:
        body_parts.append("<p style='color:#888;'>…（已截断预览）</p>")
        plain_lines.append("…（已截断预览）")
    plain = _truncate("\n".join(plain_lines))
    html_body = _wrap_word_html("".join(body_parts) or "<p>（文档无可见文本）</p>")
    return OfficePreview(
        kind_label=kind,
        family="word",
        plain=plain,
        html_body=html_body,
        note=note,
    )


def _structured_doc_legacy(path: Path, kind: str) -> OfficePreview:
    text = _preview_word_com(path)
    if not text:
        raise RuntimeError("旧版 .doc 需本机安装 Word，或另存为 .docx 后预览")
    esc = html.escape(text).replace("\n", "<br/>")
    return OfficePreview(
        kind_label=kind,
        family="word",
        plain=text,
        html_body=_wrap_word_html(f"<p>{esc}</p>"),
        note="旧版 .doc · 纯文本预览",
    )


def _structured_rtf(path: Path, kind: str) -> OfficePreview:
    text = _preview_rtf(path)
    esc = html.escape(text).replace("\n", "<br/>")
    return OfficePreview(
        kind_label=kind,
        family="word",
        plain=text,
        html_body=_wrap_word_html(f"<p>{esc}</p>"),
        note="RTF · 纯文本预览",
    )


def _structured_xlsx(path: Path, kind: str) -> OfficePreview:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("需要 openpyxl：pip install openpyxl") from exc
    wb = load_workbook(str(path), read_only=True, data_only=True)
    sheets: list[OfficeSheet] = []
    plain_lines: list[str] = []
    try:
        for si, name in enumerate(wb.sheetnames[:8]):
            ws = wb[name]
            rows: list[list[str]] = []
            truncated = False
            for ri, row in enumerate(ws.iter_rows(values_only=True)):
                if ri >= _EXCEL_MAX_ROWS:
                    truncated = True
                    break
                vals = [_cell_str(v) for ci, v in enumerate(row) if ci < _EXCEL_MAX_COLS]
                # 跳过整行空
                if not any(vals):
                    continue
                # 补齐列宽
                while len(vals) < min(len(row), _EXCEL_MAX_COLS) and len(vals) < _EXCEL_MAX_COLS:
                    vals.append("")
                rows.append(vals)
            sheets.append(OfficeSheet(name=name, rows=rows, truncated=truncated))
            if si:
                plain_lines.append(f"\n--- 工作表: {name} ---")
            else:
                plain_lines.append(f"工作表: {name}")
            for r in rows:
                plain_lines.append("\t".join(r))
            if truncated:
                plain_lines.append("…（更多行已省略）")
    finally:
        wb.close()
    note = ""
    if any(s.truncated for s in sheets):
        note = f"每表最多 {_EXCEL_MAX_ROWS} 行 · {_EXCEL_MAX_COLS} 列"
    return OfficePreview(
        kind_label=kind,
        family="excel",
        plain=_truncate("\n".join(plain_lines)),
        sheets=sheets,
        note=note,
    )


def _structured_xls(path: Path, kind: str) -> OfficePreview:
    try:
        import xlrd
    except ImportError:
        com = _preview_excel_com(path)
        if com:
            return OfficePreview(
                kind_label=kind,
                family="text",
                plain=com,
                note="旧版 .xls · 纯文本预览",
            )
        raise RuntimeError("预览 .xls 需要 xlrd（pip install xlrd）或本机安装 Excel")
    book = xlrd.open_workbook(str(path))
    sheets: list[OfficeSheet] = []
    plain_lines: list[str] = []
    for si in range(min(8, book.nsheets)):
        sh = book.sheet_by_index(si)
        max_row = min(sh.nrows, _EXCEL_MAX_ROWS)
        max_col = min(sh.ncols, _EXCEL_MAX_COLS)
        rows: list[list[str]] = []
        for ri in range(max_row):
            vals = [_cell_str(sh.cell_value(ri, ci)) for ci in range(max_col)]
            if any(vals):
                rows.append(vals)
        truncated = sh.nrows > _EXCEL_MAX_ROWS
        sheets.append(OfficeSheet(name=sh.name, rows=rows, truncated=truncated))
        if si:
            plain_lines.append(f"\n--- 工作表: {sh.name} ---")
        else:
            plain_lines.append(f"工作表: {sh.name}")
        for r in rows:
            plain_lines.append("\t".join(r))
        if truncated:
            plain_lines.append("…（更多行已省略）")
    return OfficePreview(
        kind_label=kind,
        family="excel",
        plain=_truncate("\n".join(plain_lines)),
        sheets=sheets,
        note=f"每表最多 {_EXCEL_MAX_ROWS} 行" if any(s.truncated for s in sheets) else "",
    )


def _slide_title_and_lines(shape_texts: list[str]) -> tuple[str, list[str]]:
    cleaned = [t.strip() for t in shape_texts if t and t.strip()]
    if not cleaned:
        return "", []
    title = cleaned[0]
    rest: list[str] = []
    for t in cleaned[1:]:
        for line in t.splitlines():
            s = line.strip()
            if s:
                rest.append(s)
    return title, rest


def _structured_pptx(path: Path, kind: str) -> OfficePreview:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError("需要 python-pptx：pip install python-pptx") from exc
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE as _MSO_TABLE_ENUM
    except Exception:
        _MSO_TABLE_ENUM = None

    prs = Presentation(str(path))
    total = len(prs.slides)
    slides: list[OfficeSlide] = []
    plain_lines = [f"共 {total} 页"]
    for i, slide in enumerate(prs.slides):
        if i >= _PPT_MAX_SLIDES:
            break
        texts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                t = (shape.text or "").strip()
                if t:
                    texts.append(t)
            elif _MSO_TABLE_ENUM is not None:
                try:
                    if shape.shape_type == _MSO_TABLE_ENUM.TABLE:
                        table = shape.table
                        for row in table.rows:
                            cells = [c.text.strip() for c in row.cells]
                            if any(cells):
                                texts.append(" | ".join(cells))
                except Exception:
                    pass
        title, lines = _slide_title_and_lines(texts)
        slides.append(OfficeSlide(index=i + 1, title=title or f"第 {i + 1} 页", lines=lines))
        plain_lines.append(f"\n--- 第 {i + 1} 页 ---")
        if title:
            plain_lines.append(title)
        plain_lines.extend(lines)
    note = ""
    if total > _PPT_MAX_SLIDES:
        note = f"共 {total} 页，预览前 {_PPT_MAX_SLIDES} 页"
        plain_lines.append(f"\n…（另有 {total - _PPT_MAX_SLIDES} 页未展示）")
    return OfficePreview(
        kind_label=kind,
        family="ppt",
        plain=_truncate("\n".join(plain_lines)),
        slides=slides,
        note=note or (f"共 {total} 页" if total else ""),
    )


def _structured_ppt_legacy(path: Path, kind: str) -> OfficePreview:
    text = _preview_powerpoint_com(path)
    if not text:
        raise RuntimeError("旧版 .ppt 需本机安装 PowerPoint，或另存为 .pptx 后预览")
    # 尝试从 COM 文本拆成卡片
    slides: list[OfficeSlide] = []
    cur: OfficeSlide | None = None
    for line in text.splitlines():
        m = re.match(r"^---\s*第\s*(\d+)\s*页\s*---$", line.strip())
        if m:
            cur = OfficeSlide(index=int(m.group(1)), title=f"第 {m.group(1)} 页")
            slides.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if not s or s.startswith("共 "):
            continue
        if not cur.lines and (not cur.title or cur.title.startswith("第 ")):
            cur.title = s
        else:
            cur.lines.append(s)
    return OfficePreview(
        kind_label=kind,
        family="ppt" if slides else "text",
        plain=text,
        slides=slides,
        note="旧版 .ppt · 文本卡片预览",
    )


def _preview_rtf(path: Path) -> str:
    data = path.read_bytes()
    truncated = len(data) > _RTF_MAX_BYTES
    raw = data[:_RTF_MAX_BYTES]
    text = ""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = ""
    if not text:
        text = raw.decode("latin-1", errors="ignore")
    text = re.sub(r"\\[a-z]+-?\d* ?", " ", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if truncated:
        text += "\n\n…（已截断预览）"
    return _truncate(text)


def _preview_word_com(path: Path) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return None
    word = None
    doc = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(path.resolve()), ReadOnly=True)
        text = str(doc.Content.Text or "")
        return _truncate(text.replace("\r", "\n"))
    except Exception as exc:
        logger.debug("Word COM preview failed: %s", exc)
        return None
    finally:
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass


def _preview_powerpoint_com(path: Path) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return None
    app = None
    pres = None
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        pres = app.Presentations.Open(str(path.resolve()), WithWindow=False)
        total = int(pres.Slides.Count)
        lines = [f"共 {total} 页"]
        for i in range(1, min(total, _PPT_MAX_SLIDES) + 1):
            slide = pres.Slides(i)
            lines.append(f"\n--- 第 {i} 页 ---")
            for si in range(1, slide.Shapes.Count + 1):
                shape = slide.Shapes(si)
                if shape.HasTextFrame:
                    try:
                        t = str(shape.TextFrame.TextRange.Text or "").strip()
                    except Exception:
                        t = ""
                    if t:
                        lines.append(t)
        if total > _PPT_MAX_SLIDES:
            lines.append(f"\n…（另有 {total - _PPT_MAX_SLIDES} 页未展示）")
        return _truncate("\n".join(lines))
    except Exception as exc:
        logger.debug("PowerPoint COM preview failed: %s", exc)
        return None
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass


def _preview_excel_com(path: Path) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return None
    excel = None
    wb = None
    try:
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        wb = excel.Workbooks.Open(str(path.resolve()), ReadOnly=True)
        lines: list[str] = []
        for si in range(1, min(int(wb.Worksheets.Count), 3) + 1):
            ws = wb.Worksheets(si)
            name = str(ws.Name)
            if si > 1:
                lines.append(f"\n--- 工作表: {name} ---")
            else:
                lines.append(f"工作表: {name}")
            used = ws.UsedRange
            rows = min(int(used.Rows.Count), _EXCEL_MAX_ROWS)
            cols = min(int(used.Columns.Count), _EXCEL_MAX_COLS)
            for ri in range(1, rows + 1):
                vals: list[str] = []
                for ci in range(1, cols + 1):
                    v = ws.Cells(ri, ci).Text
                    vals.append(str(v).strip() if v is not None else "")
                if any(vals):
                    lines.append("\t".join(vals))
            if int(used.Rows.Count) > _EXCEL_MAX_ROWS:
                lines.append("…（更多行已省略）")
        return _truncate("\n".join(lines))
    except Exception as exc:
        logger.debug("Excel COM preview failed: %s", exc)
        return None
    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
