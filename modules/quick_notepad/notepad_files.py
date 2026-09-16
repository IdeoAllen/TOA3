# -*- coding: utf-8 -*-
"""记事导入 / 导出 / 文件投放（供页面调用）。"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.quick_notepad.export_pdf import (
    export_html_to_pdf,
    markdown_to_html,
    plain_to_html,
    safe_pdf_stem,
    wrap_export_html,
)
from modules.quick_notepad.note_store import (
    add_note,
    find_note,
    normalize_editor_mode,
    save_settings,
)
from modules.quick_notepad.rich_body import (
    html_for_web_preview,
    is_full_html_document,
    is_qt_rich_html,
    looks_like_html,
    strip_toa_html_marker,
)
from services.storage_paths import module_output_dir

IMPORT_SUFFIXES = frozenset(
    {".md", ".markdown", ".mdown", ".mkd", ".txt", ".text", ".html", ".htm"}
)


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def title_from_md(path: Path, body: str) -> str:
    for line in body.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if m:
            return m.group(1).strip()[:80] or path.stem
    return (path.stem.strip() or "导入的记事")[:80]


def is_importable_path(path: Path) -> bool:
    if not path.is_file():
        return False
    suf = path.suffix.lower()
    return suf in IMPORT_SUFFIXES or suf == ""


def paths_from_mime(mime) -> list[Path]:
    if mime is None or not mime.hasUrls():
        return []
    out: list[Path] = []
    for u in mime.urls():
        if not u.isLocalFile():
            continue
        p = Path(u.toLocalFile())
        if is_importable_path(p):
            out.append(p)
    return out


def body_html_for_export(*, fmt: str, plain_text: str, md_text: str) -> str:
    if normalize_editor_mode(fmt) == "txt":
        return plain_to_html(plain_text)
    if looks_like_html(md_text) and not is_qt_rich_html(md_text):
        return html_for_web_preview(md_text)
    return markdown_to_html(md_text)


def export_pdf(parent, *, title: str, body_html: str, plain: str) -> Path | None:
    if not (plain or "").strip() and "<img" not in (body_html or "").lower():
        show_warning(parent, "正文为空，无法导出 PDF。")
        return None
    out_dir = module_output_dir("quick_notepad", create=True)
    default = out_dir / f"{safe_pdf_stem(title)}.pdf"
    path_str, _ = QFileDialog.getSaveFileName(
        parent, "导出 PDF", str(default), "PDF (*.pdf)"
    )
    if not path_str:
        return None
    dest = Path(path_str)
    if dest.suffix.lower() != ".pdf":
        dest = dest.with_suffix(".pdf")
    try:
        html = (
            body_html
            if is_full_html_document(body_html)
            else wrap_export_html(title=title, body_html=body_html)
        )
        path = export_html_to_pdf(html, dest)
    except Exception as exc:
        show_warning(parent, f"导出 PDF 失败：{exc}")
        return None
    show_saved(parent, f"已导出 PDF：\n{path.name}", path)
    return path


def import_paths_into_page(page, paths: list[Path]) -> None:
    """导入文件到大纲；依赖 page 的 flush / open API。"""
    from modules.quick_notepad.rich_body import coerce_to_markdown

    files = [p for p in paths if is_importable_path(p)]
    if not files:
        show_warning(page, "请拖入 Markdown / 文本（.md / .txt）。")
        return
    page._flush_autosave()

    last_id = ""
    ok = 0
    parent_id = page._sibling_parent_id()
    for path in files:
        try:
            body = read_text_file(path)
        except OSError as exc:
            show_warning(page, f"无法读取：\n{path.name}\n{exc}")
            continue
        title = title_from_md(path, body)
        body = coerce_to_markdown(body)
        entry = add_note(title, body, parent_id=parent_id)
        last_id = entry["id"]
        ok += 1
    if not ok:
        show_warning(page, "没有成功导入的文件。")
        return
    save_settings({"view_mode": "edit"})
    page._reload_tree(keep_selection=last_id)
    if last_id:
        page.reveal_note(last_id)
    page.report_status(f"已导入 {ok} 个文件", level=StatusLevel.SUCCESS)
