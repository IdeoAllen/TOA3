# -*- coding: utf-8 -*-
"""从桌面拖入路径创建记事草稿（供 MACOS 桌面「导入记事本」调用）。

支持：Office、图片、文本(txt 等)、视频、音频。
"""
from __future__ import annotations

import html
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import QUrl

from modules.quick_notepad.note_store import add_note
from modules.quick_notepad.rich_body import store_image_file
from services.office_preview import OFFICE_EXTENSIONS, office_kind_label, read_office_preview
from services.storage_paths import module_data_dir
from services.xmind_preview import is_xmind_path, read_xmind_outline

IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"})
TEXT_EXT = frozenset(
    {
        ".txt",
        ".text",
        ".md",
        ".markdown",
        ".mdown",
        ".mkd",
        ".log",
        ".csv",
        ".json",
        ".yml",
        ".yaml",
        ".xml",
        ".html",
        ".htm",
        ".css",
        ".js",
        ".ts",
        ".py",
        ".ini",
        ".cfg",
        ".conf",
        ".bat",
        ".ps1",
        ".sql",
    }
)
VIDEO_EXT = frozenset(
    {".mp4", ".webm", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".mpeg", ".mpg", ".flv"}
)
AUDIO_EXT = frozenset(
    {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".opus", ".aiff", ".aif"}
)

_KIND_IMAGE = "image"
_KIND_TEXT = "text"
_KIND_OFFICE = "office"
_KIND_XMIND = "xmind"
_KIND_VIDEO = "video"
_KIND_AUDIO = "audio"


def attachments_dir() -> Path:
    d = module_data_dir("quick_notepad", create=True) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_attachment(src: Path) -> Path:
    src = Path(src)
    suffix = src.suffix.lower() or ".bin"
    dest = attachments_dir() / f"{uuid.uuid4().hex}{suffix}"
    shutil.copy2(src, dest)
    return dest


def handoff_kind(path: Path) -> str | None:
    """返回 image|text|office|video|audio；不支持则 None。无扩展名按文本尝试。"""
    if not path.is_file():
        return None
    suf = path.suffix.lower()
    if suf in IMAGE_EXT:
        return _KIND_IMAGE
    if suf in VIDEO_EXT:
        return _KIND_VIDEO
    if suf in AUDIO_EXT:
        return _KIND_AUDIO
    if is_xmind_path(path):
        return _KIND_XMIND
    if suf in OFFICE_EXTENSIONS:
        return _KIND_OFFICE
    if suf in TEXT_EXT or suf == "":
        return _KIND_TEXT
    return None


def is_handoff_importable(path: Path) -> bool:
    return handoff_kind(path) is not None


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raw = raw[:2_000_000]
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _file_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path.resolve())).toString()


def _html_media_note(
    *,
    kind_label: str,
    name: str,
    stored: Path,
    source: Path,
    extra_block: str = "",
) -> str:
    att = _file_url(stored)
    src = _file_url(source)
    safe_name = html.escape(name)
    safe_src = html.escape(str(source))
    return (
        "<!--toa-html-->\n"
        "<html><body>"
        f"<p><b>{html.escape(kind_label)}</b> · {safe_name}</p>"
        f'<p><a href="{att}">打开记事附件</a></p>'
        f'<p><a href="{src}">打开原文件</a></p>'
        f'<p style="color:#64748B;font-size:9pt;">{safe_src}</p>'
        f"{extra_block}"
        "</body></html>"
    )


def _office_extra_html(path: Path) -> str:
    try:
        _kind, text = read_office_preview(path)
    except Exception as exc:
        return f"<p style=\"color:#B45309;\">正文提取失败：{html.escape(str(exc))}</p>"
    snippet = (text or "").strip()
    if len(snippet) > 12_000:
        snippet = snippet[:12_000] + "\n\n…（已截断）"
    if not snippet:
        return ""
    return (
        "<hr/>"
        "<p><b>文档摘录</b></p>"
        f"<pre style=\"white-space:pre-wrap;font-size:10pt;\">{html.escape(snippet)}</pre>"
    )


def import_path_as_note(path: Path) -> tuple[str | None, str]:
    """
    将单个文件导入为记事。
    返回 (note_id, error)；成功时 error 为空。
    """
    path = Path(path)
    if not path.is_file():
        return None, "不是文件"
    kind = handoff_kind(path)
    if kind is None:
        return None, f"暂不支持导入：{path.suffix or path.name}"

    title = (path.stem.strip() or "导入的记事")[:80]
    try:
        if kind == _KIND_IMAGE:
            dest = store_image_file(path)
            url = _file_url(dest)
            body = (
                "<!--toa-html-->\n"
                "<html><body>"
                f'<p><img src="{url}" /></p>'
                f'<p style="color:#64748B;font-size:9pt;">{html.escape(path.name)}</p>'
                "</body></html>"
            )
        elif kind == _KIND_TEXT:
            body = _read_text(path)
            entry = add_note(title, body)
            suf = path.suffix.lower()
            if suf in {".html", ".htm"}:
                try:
                    from modules.quick_notepad.note_store import set_note_html_source
                    from modules.quick_notepad.rich_body import is_full_html_document

                    if is_full_html_document(body):
                        set_note_html_source(str(entry["id"]), str(path.resolve()))
                except Exception:
                    pass
            return str(entry["id"]), ""
        elif kind == _KIND_OFFICE:
            stored = store_attachment(path)
            body = _html_media_note(
                kind_label=office_kind_label(path),
                name=path.name,
                stored=stored,
                source=path,
                extra_block=_office_extra_html(path),
            )
        elif kind == _KIND_XMIND:
            stored = store_attachment(path)
            try:
                outline = read_xmind_outline(path)
            except Exception as exc:
                outline = f"（大纲提取失败：{exc}）"
            snippet = outline.strip()
            if len(snippet) > 12_000:
                snippet = snippet[:12_000] + "\n\n…（已截断）"
            extra = (
                "<hr/><p><b>导图大纲</b></p>"
                f'<pre style="white-space:pre-wrap;font-size:10pt;">{html.escape(snippet)}</pre>'
            )
            body = _html_media_note(
                kind_label="XMind 思维导图",
                name=path.name,
                stored=stored,
                source=path,
                extra_block=extra,
            )
        elif kind == _KIND_VIDEO:
            stored = store_attachment(path)
            body = _html_media_note(
                kind_label="视频",
                name=path.name,
                stored=stored,
                source=path,
            )
        else:  # audio
            stored = store_attachment(path)
            body = _html_media_note(
                kind_label="音频",
                name=path.name,
                stored=stored,
                source=path,
            )
        entry = add_note(title, body)
        return str(entry["id"]), ""
    except OSError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, str(exc)
