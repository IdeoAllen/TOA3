# -*- coding: utf-8 -*-
"""Office 文档预览文本提取（MACOS 桌面右侧预览区等）。"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PREVIEW_MAX_CHARS = 48_000
_EXCEL_MAX_ROWS = 60
_EXCEL_MAX_COLS = 16
_PPT_MAX_SLIDES = 8
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


def is_office_preview_path(path: Path) -> bool:
    return path.suffix.lower() in OFFICE_EXTENSIONS


def office_kind_label(path: Path) -> str:
    return _EXT_KIND.get(path.suffix.lower(), "Office 文档")


def read_office_preview(path: Path) -> tuple[str, str]:
    """读取 Office 类文件的可预览纯文本。返回 (类型标签, 正文)。"""
    ext = path.suffix.lower()
    if ext == ".docx":
        return office_kind_label(path), _preview_docx(path)
    if ext == ".doc":
        return office_kind_label(path), _preview_doc_legacy(path)
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return office_kind_label(path), _preview_xlsx(path)
    if ext == ".xls":
        return office_kind_label(path), _preview_xls(path)
    if ext in {".pptx", ".ppsx"}:
        return office_kind_label(path), _preview_pptx(path)
    if ext in {".ppt", ".pps"}:
        return office_kind_label(path), _preview_ppt_legacy(path)
    if ext == ".rtf":
        return office_kind_label(path), _preview_rtf(path)
    raise ValueError(f"不支持的 Office 格式：{ext}")


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= _PREVIEW_MAX_CHARS:
        return text or "（文档无可见文本）"
    return text[:_PREVIEW_MAX_CHARS] + "\n\n…（已截断预览）"


def _preview_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("需要 python-docx：pip install python-docx") from exc
    doc = Document(str(path))
    lines: list[str] = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if not t:
            continue
        style = str(getattr(para.style, "name", "") or "")
        if "Heading" in style or "标题" in style:
            lines.append(f"\n## {t}")
        else:
            lines.append(t)
    for table in doc.tables:
        lines.append("\n[表格]")
        for row in table.rows[:40]:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            if any(cells):
                lines.append("\t".join(cells))
    return _truncate("\n".join(lines))


def _preview_xlsx(path: Path) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("需要 openpyxl：pip install openpyxl") from exc
    wb = load_workbook(str(path), read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for si, name in enumerate(wb.sheetnames[:3]):
            ws = wb[name]
            if si:
                lines.append(f"\n--- 工作表: {name} ---")
            else:
                lines.append(f"工作表: {name}")
            for ri, row in enumerate(ws.iter_rows(values_only=True)):
                if ri >= _EXCEL_MAX_ROWS:
                    lines.append("…（更多行已省略）")
                    break
                vals: list[str] = []
                for ci, v in enumerate(row):
                    if ci >= _EXCEL_MAX_COLS:
                        break
                    vals.append("" if v is None else str(v).strip())
                if any(vals):
                    lines.append("\t".join(vals))
    finally:
        wb.close()
    return _truncate("\n".join(lines))


def _preview_xls(path: Path) -> str:
    try:
        import xlrd
    except ImportError:
        com = _preview_excel_com(path)
        if com:
            return com
        raise RuntimeError("预览 .xls 需要 xlrd（pip install xlrd）或本机安装 Excel")
    book = xlrd.open_workbook(str(path))
    lines: list[str] = []
    for si in range(min(3, book.nsheets)):
        sh = book.sheet_by_index(si)
        if si:
            lines.append(f"\n--- 工作表: {sh.name} ---")
        else:
            lines.append(f"工作表: {sh.name}")
        max_row = min(sh.nrows, _EXCEL_MAX_ROWS)
        max_col = min(sh.ncols, _EXCEL_MAX_COLS)
        for ri in range(max_row):
            vals = [str(sh.cell_value(ri, ci)).strip() for ci in range(max_col)]
            if any(vals):
                lines.append("\t".join(vals))
        if sh.nrows > _EXCEL_MAX_ROWS:
            lines.append("…（更多行已省略）")
    return _truncate("\n".join(lines))


def _preview_pptx(path: Path) -> str:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError("需要 python-pptx：pip install python-pptx") from exc
    prs = Presentation(str(path))
    total = len(prs.slides)
    lines = [f"共 {total} 页"]
    for i, slide in enumerate(prs.slides):
        if i >= _PPT_MAX_SLIDES:
            break
        lines.append(f"\n--- 第 {i + 1} 页 ---")
        for shape in slide.shapes:
            text = getattr(shape, "text", "") or ""
            text = text.strip()
            if text:
                lines.append(text)
    if total > _PPT_MAX_SLIDES:
        lines.append(f"\n…（另有 {total - _PPT_MAX_SLIDES} 页未展示）")
    return _truncate("\n".join(lines))


def _preview_rtf(path: Path) -> str:
    data = path.read_bytes()
    truncated = len(data) > _RTF_MAX_BYTES
    raw = data[:_RTF_MAX_BYTES]
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


def _preview_doc_legacy(path: Path) -> str:
    com = _preview_word_com(path)
    if com:
        return com
    raise RuntimeError("旧版 .doc 需本机安装 Word，或另存为 .docx 后预览")


def _preview_ppt_legacy(path: Path) -> str:
    com = _preview_powerpoint_com(path)
    if com:
        return com
    raise RuntimeError("旧版 .ppt 需本机安装 PowerPoint，或另存为 .pptx 后预览")


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
