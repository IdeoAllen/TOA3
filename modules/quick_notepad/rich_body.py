# -*- coding: utf-8 -*-
"""记事正文：Markdown 一源；设计/预览渲染；本地插图。"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QImage,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextImageFormat,
)
from PySide6.QtWidgets import QTextEdit

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
    from modules.quick_notepad.media_store import images_dir as _images_dir

    return _images_dir()


def store_image_file(src: Path, *, max_width: int = 960) -> Path:
    from modules.quick_notepad.media_store import store_image_file as _store

    return _store(Path(src), max_width=max_width, prefer_move=True)


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


_HL_PROP = int(QTextFormat.Property.UserProperty) + 17  # toa-highlight
_HL_BG = QColor("#FEF08A")
_HL_FG = QColor("#334155")
_HL_PARK = re.compile(r"==([^=\n]+)==")
_IMG_TAG = re.compile(
    r'<img\b[^>]*?\bsrc=["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE,
)
_IMG_WIDTH = re.compile(r'\bwidth=["\']?(\d+)', re.IGNORECASE)
_IMG_ALT = re.compile(r'\balt=["\']([^"\']*)["\']', re.IGNORECASE)
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def highlight_char_format() -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setBackground(_HL_BG)
    fmt.setForeground(_HL_FG)
    fmt.setProperty(_HL_PROP, "1")
    return fmt


def apply_highlight_to_selection(edit: QTextEdit) -> bool:
    """工具栏高亮：所见即所得底色，落盘时收成 ==…==。"""
    if edit is None or edit.isReadOnly():
        return False
    cur = edit.textCursor()
    if not cur.hasSelection():
        cur.insertText("高亮重点", highlight_char_format())
        edit.setTextCursor(cur)
        return True
    fmt = highlight_char_format()
    cur.mergeCharFormat(fmt)
    edit.setTextCursor(cur)
    return True


def _park_highlights(md: str) -> tuple[str, list[str]]:
    slots: list[str] = []

    def _park(m: re.Match[str]) -> str:
        slots.append(m.group(1))
        return f"\u2060HL{len(slots) - 1}\u2060"

    return _HL_PARK.sub(_park, md or ""), slots


def _unpark_highlights(edit: QTextEdit, slots: list[str]) -> None:
    doc = edit.document()
    if doc is None or not slots:
        return
    fmt = highlight_char_format()
    for i, text in enumerate(slots):
        needle = f"\u2060HL{i}\u2060"
        found = doc.find(needle)
        if found.isNull():
            continue
        found.insertText(text, fmt)


def _collect_img_widths(md: str) -> dict[str, tuple[int | None, str]]:
    """src → (width, alt) from HTML img tags in source."""
    out: dict[str, tuple[int | None, str]] = {}
    for m in _IMG_TAG.finditer(md or ""):
        tag = m.group(0)
        src = (m.group(1) or "").strip()
        if not src:
            continue
        wm = _IMG_WIDTH.search(tag)
        am = _IMG_ALT.search(tag)
        width = int(wm.group(1)) if wm else None
        alt = (am.group(1) if am else "") or "图片"
        out[src] = (width, alt)
    return out


def _apply_img_widths(edit: QTextEdit, widths: dict[str, tuple[int | None, str]]) -> None:
    if not widths:
        return
    doc = edit.document()
    if doc is None:
        return
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                fmt = QTextImageFormat(frag.charFormat().toImageFormat())
                name = str(fmt.name() or "")
                meta = widths.get(name)
                if meta is None:
                    # file:/// vs path variants
                    for src, data in widths.items():
                        if src in name or name in src:
                            meta = data
                            break
                if meta and meta[0] and meta[0] > 0:
                    w = float(meta[0])
                    if abs(fmt.width() - w) > 0.5:
                        fmt.setWidth(w)
                        cur = QTextCursor(doc)
                        cur.setPosition(frag.position())
                        cur.setPosition(
                            frag.position() + frag.length(),
                            QTextCursor.MoveMode.KeepAnchor,
                        )
                        cur.setCharFormat(fmt)
            it += 1
        block = block.next()


def apply_document_chrome(edit: QTextEdit) -> None:
    """编辑面：像打开一篇文档（边距 + 正文字号），不另做主题包。"""
    if edit is None:
        return
    doc = edit.document()
    if doc is not None:
        doc.setDocumentMargin(28)
    font = edit.font()
    if font.pointSize() < 12:
        font.setFamily("Microsoft YaHei UI")
        font.setPointSize(12)
        edit.setFont(font)


def load_body_into(edit: QTextEdit, body: str) -> None:
    """载入所见即所得编辑面；落盘真源仍是 Markdown。"""
    from modules.quick_notepad.md_text import sanitize_md_source

    text = sanitize_md_source(body or "")
    edit.blockSignals(True)
    try:
        if not text.strip():
            edit.clear()
        elif looks_like_html(text) or is_qt_rich_html(text) or is_toa_rich_html(text):
            edit.setHtml(strip_toa_html_marker(text))
        else:
            parked, slots = _park_highlights(text)
            img_meta = _collect_img_widths(text)
            try:
                edit.setMarkdown(parked)
            except Exception:
                edit.setPlainText(text)
                apply_document_chrome(edit)
                return
            _unpark_highlights(edit, slots)
            _apply_img_widths(edit, img_meta)
        apply_document_chrome(edit)
    finally:
        edit.blockSignals(False)


def _fragment_is_highlight(fmt: QTextCharFormat) -> bool:
    if str(fmt.property(_HL_PROP) or "") == "1":
        return True
    bg = fmt.background().color()
    if not bg.isValid():
        return False
    # 近似 FEF08A
    return abs(bg.red() - 0xFE) < 20 and abs(bg.green() - 0xF0) < 25 and abs(bg.blue() - 0x8A) < 30


def _image_markdown_from_fmt(fmt: QTextImageFormat) -> str:
    from modules.quick_notepad.image_attrs import build_image_markdown, normalize_size_key

    src = str(fmt.name() or "").strip()
    if not src:
        return ""
    alt = "图片"
    w = int(fmt.width()) if fmt.width() > 0 else None
    if w is None:
        return f"![{alt}]({src})\n"
    # map width to nearest preset key for stable source
    from modules.quick_notepad.image_attrs import SIZE_PRESETS

    best = "md"
    best_diff = 10**9
    for key, (_label, pw) in SIZE_PRESETS.items():
        if pw is None:
            continue
        d = abs(int(pw) - w)
        if d < best_diff:
            best_diff = d
            best = key
    if best_diff > 40:
        return f'<img src="{src}" width="{w}" alt="{alt}" />\n'
    return build_image_markdown(src, alt=alt, size_key=normalize_size_key(best))


def export_markdown_from(edit: QTextEdit) -> str:
    """所见即所得 → Markdown 一源（保留高亮 == 与插图 width）。"""
    from modules.quick_notepad.md_text import sanitize_md_source

    if edit is None or not (edit.toPlainText() or "").strip():
        return ""
    src_doc = edit.document()
    if src_doc is None:
        return sanitize_md_source(edit.toPlainText())

    # 克隆后再改，避免污染正在编辑的文档
    clone = QTextDocument()
    clone.setHtml(src_doc.toHtml())

    marked_ranges: list[tuple[int, int]] = []
    block = clone.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and not frag.charFormat().isImageFormat():
                if _fragment_is_highlight(frag.charFormat()):
                    marked_ranges.append((frag.position(), frag.length()))
            it += 1
        block = block.next()
    for pos, length in sorted(marked_ranges, key=lambda x: x[0], reverse=True):
        cur = QTextCursor(clone)
        cur.setPosition(pos + length)
        cur.insertText("==")
        cur.setPosition(pos)
        cur.insertText("==")

    quote_at: list[int] = []
    block = clone.begin()
    while block.isValid():
        bf = block.blockFormat()
        if bf.leftMargin() >= 30 and bf.rightMargin() >= 30:
            if not (block.text() or "").lstrip().startswith(">"):
                quote_at.append(block.position())
        block = block.next()
    for pos in reversed(quote_at):
        cur = QTextCursor(clone)
        cur.setPosition(pos)
        cur.insertText("> ")

    try:
        text = clone.toMarkdown()
    except Exception:
        text = clone.toPlainText()

    img_map: dict[str, str] = {}
    block = src_doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                fmt = QTextImageFormat(frag.charFormat().toImageFormat())
                piece = _image_markdown_from_fmt(fmt).rstrip("\n")
                name = str(fmt.name() or "")
                if name and piece:
                    img_map[name] = piece
            it += 1
        block = block.next()

    def _repl_img(m: re.Match[str]) -> str:
        url = (m.group(2) or "").strip()
        for name, piece in img_map.items():
            if url == name or url in name or name in url:
                return piece
        return m.group(0)

    if img_map:
        text = _MD_IMAGE.sub(_repl_img, text or "")
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
    from modules.quick_notepad.media_store import store_qimage

    dest = store_qimage(qimg, max_width=max_width)
    if dest is None:
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
