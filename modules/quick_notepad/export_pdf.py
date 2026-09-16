# -*- coding: utf-8 -*-
"""快速记事 → PDF（Qt QTextDocument 打印，无额外依赖）。"""
from __future__ import annotations

import html as html_lib
import re
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_BODY_INNER = re.compile(
    r"<body\b[^>]*>(.*)</body>",
    re.IGNORECASE | re.DOTALL,
)


def safe_pdf_stem(title: str, *, fallback: str = "记事") -> str:
    raw = (title or "").strip() or fallback
    cleaned = _UNSAFE.sub("_", raw).strip(" ._") or fallback
    return cleaned[:80]


def plain_to_html(text: str) -> str:
    """纯文本 → 简单 HTML（保留换行）。"""
    body = html_lib.escape(text or "")
    if not body.strip():
        return "<p></p>"
    paras = [f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in body.split("\n\n")]
    return "\n".join(paras) if paras else f"<p>{body.replace(chr(10), '<br/>')}</p>"


def markdown_to_html(md: str) -> str:
    """Markdown → HTML（Qt 内置渲染）。"""
    doc = QTextDocument()
    doc.setMarkdown(md or "")
    return doc.toHtml()


def html_body_fragment(html: str) -> str:
    """完整 HTML → body 内片段，避免导出时 DOCTYPE/html 套娃。"""
    raw = (html or "").strip()
    if not raw:
        return "<p></p>"
    m = _BODY_INNER.search(raw)
    if m:
        inner = (m.group(1) or "").strip()
        return inner or "<p></p>"
    return raw


def wrap_export_html(*, title: str, body_html: str) -> str:
    """导出用整页 HTML：标题 + 正文。"""
    t = html_lib.escape((title or "").strip() or "未命名记事")
    body = html_body_fragment(body_html)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        f"<title>{t}</title></head><body>"
        f"<h1 style='font-size:18pt;margin:0 0 12pt 0;'>{t}</h1>"
        f"<div>{body}</div></body></html>"
    )


def export_html_to_pdf(html: str, dest: Path | str) -> Path:
    """将 HTML 写入 PDF；成功返回绝对路径。"""
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)

    doc = QTextDocument()
    doc.setHtml(html or "<p></p>")
    doc.setDocumentMargin(8)
    doc.print_(printer)
    if not path.is_file() or path.stat().st_size <= 0:
        raise OSError(f"PDF 未生成：{path}")
    return path.resolve()
