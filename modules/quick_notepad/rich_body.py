# -*- coding: utf-8 -*-
"""记事正文：Markdown 一源；设计/预览渲染；本地插图。"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QTextEdit

from services.storage_paths import module_data_dir

_HTML_HINT = re.compile(
    r"<!DOCTYPE\s+html|<html[\s>]|<body[\s>]|<p[\s>]|<div[\s>]|<img[\s>]|<h[1-6][\s>]",
    re.IGNORECASE,
)
_TOA_MARK = "<!--toa-html-->"


def looks_like_html(text: str) -> bool:
    s = (text or "").lstrip()
    if not s:
        return False
    if s.startswith(_TOA_MARK):
        return True
    return bool(_HTML_HINT.search(s[:800]))


def is_toa_rich_html(text: str) -> bool:
    return (text or "").lstrip().startswith(_TOA_MARK)


def is_qt_rich_html(text: str) -> bool:
    head = (text or "")[:4000].lower()
    return (
        "qrichtext" in head
        or 'meta name="qrichtext"' in head
        or "-qt-block-indent" in head
        or "-qt-paragraph-type" in head
    )


def is_full_html_document(text: str) -> bool:
    s = (text or "").lstrip()
    if not s or is_qt_rich_html(s) or is_toa_rich_html(s):
        return False
    body = strip_toa_html_marker(s).lstrip()
    return bool(re.search(r"<!DOCTYPE\s+html|<html[\s>]", body[:1200], re.IGNORECASE))


def strip_toa_html_marker(text: str) -> str:
    raw = text or ""
    if raw.lstrip().startswith(_TOA_MARK):
        if raw.startswith(_TOA_MARK):
            return raw[len(_TOA_MARK) :].lstrip("\n")
        idx = raw.find(_TOA_MARK)
        if idx >= 0:
            return raw[idx + len(_TOA_MARK) :].lstrip("\n")
    return raw


def html_for_web_preview(text: str) -> str:
    raw = strip_toa_html_marker(text or "").strip()
    if not raw:
        return "<html><body></body></html>"
    if looks_like_html(raw):
        return raw
    import html as html_lib

    esc = html_lib.escape(raw).replace("\n", "<br/>")
    return (
        f"<html><body><pre style='white-space:pre-wrap;font:12pt sans-serif;'>"
        f"{esc}</pre></body></html>"
    )


def images_dir() -> Path:
    d = module_data_dir("quick_notepad", create=True) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_image_file(src: Path, *, max_width: int = 960) -> Path:
    src = Path(src)
    suffix = src.suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
        suffix = ".png"
    dest = images_dir() / f"{uuid.uuid4().hex}{suffix}"
    img = QImage(str(src))
    if img.isNull():
        shutil.copy2(src, dest)
        return dest
    if img.width() > max_width:
        img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    if not img.save(str(dest)):
        shutil.copy2(src, dest)
    return dest


def _html_to_markdown(html: str) -> str:
    doc = QTextDocument()
    doc.setHtml(strip_toa_html_marker(html or ""))
    try:
        return doc.toMarkdown()
    except Exception:
        return doc.toPlainText()


def coerce_to_markdown(text: str) -> str:
    """任意遗留正文 → Markdown 一源。"""
    from modules.quick_notepad.md_text import sanitize_md_source

    raw = text or ""
    if not raw.strip():
        return ""
    if looks_like_html(raw) or is_qt_rich_html(raw) or is_toa_rich_html(raw):
        return sanitize_md_source(_html_to_markdown(raw))
    return sanitize_md_source(raw)


def load_body_into(edit: QTextEdit, body: str) -> None:
    """载入设计区：Markdown 优先；遗留 HTML 仍可打开。"""
    text = body or ""
    edit.blockSignals(True)
    try:
        if not text.strip():
            edit.clear()
        elif looks_like_html(text) or is_qt_rich_html(text) or is_toa_rich_html(text):
            edit.setHtml(strip_toa_html_marker(text))
        else:
            try:
                from modules.quick_notepad.md_text import prepare_markdown_for_preview

                edit.setMarkdown(prepare_markdown_for_preview(text))
            except Exception:
                edit.setPlainText(text)
        # 菜鸟教程式阅读感：略增页边距
        doc = edit.document()
        if doc is not None:
            doc.setDocumentMargin(16)
    finally:
        edit.blockSignals(False)


def export_markdown_from(edit: QTextEdit) -> str:
    """设计区 → Markdown（一源落盘）。"""
    from modules.quick_notepad.md_text import sanitize_md_source

    if not (edit.toPlainText() or "").strip():
        return ""
    try:
        text = edit.toMarkdown()
    except Exception:
        text = edit.toPlainText()
    return sanitize_md_source(text or "")


def refresh_markdown_preview(source: QTextEdit, preview: QTextEdit) -> None:
    """源码 → 预览：手写 MD 与组件插入同一路径（Qt setMarkdown）。"""
    from modules.quick_notepad.image_attrs import clamp_preview_images
    from modules.quick_notepad.md_text import prepare_markdown_for_preview

    text = prepare_markdown_for_preview(
        source.toPlainText() if hasattr(source, "toPlainText") else str(source or "")
    )
    preview.blockSignals(True)
    try:
        if not text.strip():
            preview.clear()
        else:
            preview.setMarkdown(text)
        doc = preview.document()
        if doc is not None:
            doc.setDocumentMargin(16)
        clamp_preview_images(preview)
    finally:
        preview.blockSignals(False)


def render_markdown_string(md: str, preview: QTextEdit) -> None:
    """无编辑器时：任意 Markdown 字符串 → 预览控件（手写验真用）。"""
    from modules.quick_notepad.image_attrs import clamp_preview_images
    from modules.quick_notepad.md_text import prepare_markdown_for_preview

    text = prepare_markdown_for_preview(md)
    preview.blockSignals(True)
    try:
        if not text.strip():
            preview.clear()
        else:
            preview.setMarkdown(text)
        doc = preview.document()
        if doc is not None:
            doc.setDocumentMargin(16)
        clamp_preview_images(preview)
    finally:
        preview.blockSignals(False)


def refresh_editor_preview(
    *,
    source: QTextEdit,
    preview: QTextEdit,
    design: QTextEdit | None = None,
    prefer_design: bool = False,
) -> None:
    del design, prefer_design
    refresh_markdown_preview(source, preview)


def _insert_stored_image(edit: QTextEdit, dest: Path) -> bool:
    dest = Path(dest)
    if not dest.is_file():
        return False
    img = QImage(str(dest))
    if img.isNull():
        return False
    url = QUrl.fromLocalFile(str(dest.resolve()))
    name = url.toString()
    doc = edit.document()
    if doc is None:
        return False
    doc.addResource(QTextDocument.ResourceType.ImageResource, url, img)
    fmt = QTextImageFormat()
    fmt.setName(name)
    w = min(img.width(), 640)
    if img.width() > 0:
        h = int(img.height() * (w / img.width()))
    else:
        h = img.height()
    fmt.setWidth(w)
    fmt.setHeight(max(h, 1))
    cur = edit.textCursor()
    if not cur.atBlockStart() and cur.position() > 0:
        cur.insertBlock()
    cur.insertImage(fmt)
    cur.insertBlock()
    edit.setTextCursor(cur)
    return True


def insert_image(edit: QTextEdit, image_path: Path) -> bool:
    dest = store_image_file(Path(image_path))
    return _insert_stored_image(edit, dest)


def insert_qimage(edit: QTextEdit, qimg: QImage, *, max_width: int = 960) -> bool:
    if qimg is None or qimg.isNull():
        return False
    img = qimg
    if img.width() > max_width:
        img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    dest = images_dir() / f"{uuid.uuid4().hex}.png"
    if not img.save(str(dest)):
        return False
    return _insert_stored_image(edit, dest)


def markdown_image_snippet(
    image_path: Path,
    *,
    alt: str | None = None,
    size_key: str | None = None,
    kind: str = "image",
) -> str:
    from modules.quick_notepad.image_attrs import (
        DEFAULT_IMAGE_SIZE,
        normalize_size_key,
        store_and_snippet,
        suggest_size_key,
    )

    img = QImage(str(image_path))
    if size_key is None:
        key = suggest_size_key(img, kind=kind)
    else:
        key = normalize_size_key(
            size_key,
            fallback=DEFAULT_IMAGE_SIZE if kind != "icon" else "icon",
        )
    return store_and_snippet(Path(image_path), alt=alt, size_key=key, kind=kind)
