# -*- coding: utf-8 -*-
"""记事插图/图标：实用尺寸预设与源码片段。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QTextEdit

# key → (界面名, 显示宽度 px；None=不写 width，跟文件像素走)
SIZE_PRESETS: dict[str, tuple[str, int | None]] = {
    "icon": ("小图标 · 48", 48),
    "sm": ("小图 · 160", 160),
    "md": ("中图 · 360（常用）", 360),
    "lg": ("大图 · 560", 560),
    "wide": ("宽图 · 720", 720),
    "orig": ("原图宽度", None),
}

SIZE_ORDER = ("icon", "sm", "md", "lg", "wide", "orig")
DEFAULT_IMAGE_SIZE = "md"
DEFAULT_ICON_SIZE = "icon"
# 预览里无显式宽度时，过大图钳到此值，避免撑破版面
PREVIEW_CLAMP_WIDTH = 560


def normalize_size_key(key: str | None, *, fallback: str = DEFAULT_IMAGE_SIZE) -> str:
    k = str(key or "").strip().lower()
    if k in SIZE_PRESETS:
        return k
    # 中文别名
    aliases = {
        "小图标": "icon",
        "图标": "icon",
        "小图": "sm",
        "中图": "md",
        "大图": "lg",
        "宽图": "wide",
        "原图": "orig",
        "原图宽度": "orig",
    }
    if k in aliases:
        return aliases[k]
    return fallback if fallback in SIZE_PRESETS else DEFAULT_IMAGE_SIZE


def size_label(key: str) -> str:
    k = normalize_size_key(key)
    return SIZE_PRESETS[k][0]


def size_width(key: str) -> int | None:
    k = normalize_size_key(key)
    return SIZE_PRESETS[k][1]


def suggest_size_key(img: QImage | None, *, kind: str = "image") -> str:
    """按像素给默认：小图走图标档，大图走中/大，方便一键确定。"""
    kind = "icon" if str(kind or "").strip().lower() == "icon" else "image"
    if img is None or img.isNull():
        return DEFAULT_ICON_SIZE if kind == "icon" else DEFAULT_IMAGE_SIZE
    w = int(img.width())
    h = int(img.height())
    if kind == "icon":
        if w <= 128 and h <= 128:
            return "icon"
        if w <= 240:
            return "sm"
        return "sm"
    # 图片：正方形小图当图标；超宽截图用宽图档的宽度但仍默认中图更易读
    if w <= 96 and h <= 96:
        return "icon"
    if w <= 220:
        return "sm"
    if w <= 900:
        return "md"
    return "lg"


def build_image_markdown(
    uri: str,
    *,
    alt: str = "图片",
    size_key: str = DEFAULT_IMAGE_SIZE,
) -> str:
    """落源码：带 width 的 <img>，预览/导出都能控大小。"""
    alt_s = (alt or "图片").replace('"', "'").strip() or "图片"
    src = (uri or "").strip()
    if not src:
        return ""
    w = size_width(size_key)
    if w is None:
        return f'<img src="{src}" alt="{alt_s}" />\n'
    return f'<img src="{src}" width="{int(w)}" alt="{alt_s}" />\n'


def clamp_preview_images(preview: QTextEdit, *, max_width: int = PREVIEW_CLAMP_WIDTH) -> None:
    """无显式宽度或过大时钳制，保持版面可读。已有较小 width 不放大。"""
    if preview is None or max_width <= 0:
        return
    doc = preview.document()
    if doc is None:
        return
    from PySide6.QtCore import QUrl

    jobs: list[tuple[int, int, QTextImageFormat]] = []
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                fmt = QTextImageFormat(frag.charFormat().toImageFormat())
                cur_w = float(fmt.width())
                name = fmt.name()
                img = QImage()
                if name:
                    url = QUrl(name) if not isinstance(name, QUrl) else name
                    res = doc.resource(QTextDocument.ResourceType.ImageResource, url)
                    if isinstance(res, QImage) and not res.isNull():
                        img = res
                    else:
                        local = url.toLocalFile() if url.isValid() else ""
                        if not local and str(name).startswith("file:"):
                            local = QUrl(str(name)).toLocalFile()
                        if local:
                            img = QImage(local)
                natural_w = int(img.width()) if not img.isNull() else 0
                target = cur_w
                if target <= 0 and natural_w > 0:
                    target = float(min(natural_w, max_width))
                elif target > max_width:
                    target = float(max_width)
                if target > 0 and abs(target - cur_w) > 0.5:
                    if natural_w > 0 and not img.isNull():
                        h = max(1.0, img.height() * (target / natural_w))
                    elif cur_w > 0 and fmt.height() > 0:
                        h = float(fmt.height()) * (target / cur_w)
                    else:
                        h = float(fmt.height() or target)
                    fmt.setWidth(target)
                    fmt.setHeight(h)
                    jobs.append((frag.position(), frag.length(), fmt))
            it += 1
        block = block.next()
    for pos, length, fmt in jobs:
        cur = QTextCursor(doc)
        cur.setPosition(pos)
        cur.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        cur.setCharFormat(fmt)


def store_and_snippet(
    src: Path,
    *,
    alt: str | None = None,
    size_key: str = DEFAULT_IMAGE_SIZE,
    kind: str = "image",
    max_store_width: int = 960,
) -> str:
    """复制入库并生成可控大小的插图源码。"""
    from modules.quick_notepad.rich_body import store_image_file

    path = store_image_file(Path(src), max_width=max_store_width)
    img = QImage(str(path))
    key = normalize_size_key(size_key, fallback=suggest_size_key(img, kind=kind))
    name = (alt or path.name).strip() or path.name
    return build_image_markdown(path.resolve().as_uri(), alt=name, size_key=key)
