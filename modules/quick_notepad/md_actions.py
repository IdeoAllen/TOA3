# -*- coding: utf-8 -*-
"""Markdown 工具栏 / 组件插入：只写入编辑区源码。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.quick_notepad.component_blocks import (
    get_block,
    insert_markdown_snippet,
    markdown_for_block,
)
from modules.quick_notepad.image_attrs import (
    DEFAULT_ICON_SIZE,
    DEFAULT_IMAGE_SIZE,
    SIZE_ORDER,
    SIZE_PRESETS,
    build_image_markdown,
    normalize_size_key,
    size_label,
    suggest_size_key,
)
from modules.quick_notepad.media_store import path_as_uri, store_qimage
from modules.quick_notepad.note_store import load_settings, save_settings
from modules.quick_notepad.rich_body import markdown_image_snippet
from widgets import ComboBox, HintLabel, LineEdit
from widgets.dialog_actions import DialogButtonRow
from widgets.list_edit import FormEditDialog

MD_WRAP = {
    "bold": ("**", "**"),
    "italic": ("*", "*"),
    "strike": ("~~", "~~"),
    "highlight": ("==", "=="),
    "inline_code": ("`", "`"),
}


def _after(page, *, scroll_end: bool = False) -> None:
    page._after_md_mutation(scroll_end=scroll_end)


def insert_md_block_at_cursor(page, block: str) -> None:
    page._ensure_writable()
    cur = page._md_source.textCursor()
    piece = block if block.endswith("\n") else block + "\n"
    if cur.position() > 0 and not cur.atBlockStart():
        cur.insertText("\n")
    if piece.lstrip().startswith("```"):
        cur.insertText(piece)
    elif hasattr(cur, "insertMarkdown"):
        try:
            cur.insertMarkdown(piece)
        except Exception:
            cur.insertText(piece)
    else:
        cur.insertText(piece)
    page._md_source.setTextCursor(cur)
    _after(page)


def fmt_link_md(page) -> None:
    from modules.quick_notepad.edit_ops import apply_link

    page._ensure_writable()
    cur = page._md_source.textCursor()
    selected = cur.selectedText().replace("\u2029", " ") or "链接文字"
    dlg = FormEditDialog(
        page, title="插入链接", fields=[("显示文字", "text"), ("网址", "url")]
    )
    dlg.set_values({"text": selected, "url": "https://"})
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    vals = dlg.values()
    text = (vals.get("text") or "链接").strip()
    url = (vals.get("url") or "").strip() or "https://"
    apply_link(page, text, url)


class _ImageInsertDialog(BaseDialog):
    """插图/图标：说明 + 显示大小（默认已按像素估好，直接确定即可）。"""

    dialog_kind = "medium"

    def __init__(
        self,
        parent=None,
        *,
        kind: str = "image",
        default_alt: str = "",
        default_size: str = DEFAULT_IMAGE_SIZE,
        hint: str = "",
    ) -> None:
        super().__init__(parent)
        self._kind = "icon" if kind == "icon" else "image"
        self.setWindowTitle("插入图标" if self._kind == "icon" else "插入图片")
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        if hint:
            lay.addWidget(HintLabel(hint))

        row1 = QHBoxLayout()
        row1.addWidget(HintLabel("说明"))
        self._alt = LineEdit()
        self._alt.setText(default_alt)
        self._alt.setPlaceholderText("图片说明（可改）")
        row1.addWidget(self._alt, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(HintLabel("显示大小"))
        self._size = ComboBox()
        for key in SIZE_ORDER:
            self._size.addItem(SIZE_PRESETS[key][0], key)
        want = normalize_size_key(
            default_size,
            fallback=DEFAULT_ICON_SIZE if self._kind == "icon" else DEFAULT_IMAGE_SIZE,
        )
        idx = self._size.findData(want)
        self._size.setCurrentIndex(idx if idx >= 0 else 0)
        row2.addWidget(self._size, 1)
        lay.addLayout(row2)
        lay.addWidget(
            HintLabel("默认已按图片像素选好 · 多数情况直接点确定即可")
        )

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("插入", self.accept)
        lay.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {
            "alt": self._alt.text().strip(),
            "size": str(self._size.currentData() or DEFAULT_IMAGE_SIZE),
        }


def _remember_size(kind: str, size_key: str) -> None:
    cur = load_settings()
    key = "icon_size" if kind == "icon" else "image_size"
    cur[key] = normalize_size_key(size_key)
    save_settings(cur)


def _default_size_for(kind: str, img: QImage) -> str:
    settings = load_settings()
    remembered = settings.get("icon_size" if kind == "icon" else "image_size")
    if remembered:
        return normalize_size_key(
            str(remembered),
            fallback=suggest_size_key(img, kind=kind),
        )
    return suggest_size_key(img, kind=kind)


def insert_image_at_end(page, *, kind: str = "image") -> bool:
    kind = "icon" if str(kind or "").strip().lower() == "icon" else "image"
    path, _ = QFileDialog.getOpenFileName(
        page,
        "选择图标" if kind == "icon" else "选择图片",
        "",
        "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.ico *.svg);;所有文件 (*.*)",
    )
    if not path:
        return False
    src = Path(path)
    probe = QImage(str(src))
    settings = load_settings()
    # 记忆优先；若无记忆则按像素建议（更省事）
    remembered = settings.get("icon_size" if kind == "icon" else "image_size")
    default_size = (
        normalize_size_key(str(remembered))
        if remembered
        else suggest_size_key(probe, kind=kind)
    )
    dlg = _ImageInsertDialog(
        page,
        kind=kind,
        default_alt=src.stem,
        default_size=default_size,
        hint=(
            "图标默认偏小，适合徽标/状态标记"
            if kind == "icon"
            else "图片默认中等宽度，正文里好读不撑版"
        ),
    )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    vals = dlg.values()
    size_key = normalize_size_key(vals.get("size"), fallback=default_size)
    alt = (vals.get("alt") or src.stem).strip() or src.stem
    page._ensure_writable()
    snippet = markdown_image_snippet(src, alt=alt, size_key=size_key, kind=kind)
    if not snippet.strip():
        return False
    if not insert_markdown_snippet(page._md_source, snippet, at_end=True):
        return False
    _remember_size(kind, size_key)
    _after(page, scroll_end=True)
    page.report_status(
        f"已插入「{alt}」· {size_label(size_key)} · 文末",
        level=StatusLevel.SUCCESS,
    )
    return True


def insert_clipboard_image_snippet(img: QImage, *, kind: str = "image") -> str:
    """粘贴：不弹窗，按记忆/建议尺寸直接插入（走媒体库）。"""
    if img is None or img.isNull():
        return ""
    kind = "icon" if kind == "icon" else "image"
    path = store_qimage(img, max_width=960)
    if path is None:
        return ""
    size_key = _default_size_for(kind, img)
    return build_image_markdown(
        path_as_uri(path), alt="粘贴图片", size_key=size_key
    )


def toolbar_action(page, block_id: str) -> None:
    from modules.quick_notepad.edit_ops import (
        apply_heading,
        apply_list,
        apply_quote,
        toggle_inline,
    )

    bid = str(block_id or "").strip()
    if bid in ("h1", "h2", "h3", "h4", "h5", "h6"):
        apply_heading(page, int(bid[1]))
    elif bid == "bullets":
        apply_list(page, ordered=False)
    elif bid == "steps":
        apply_list(page, ordered=True)
    elif bid == "quote":
        apply_quote(page)
    elif bid in MD_WRAP:
        toggle_inline(page, bid)
    elif bid in ("code_block", "table", "checklist", "hr"):
        md = markdown_for_block(bid)
        if md.strip():
            insert_md_block_at_cursor(page, md)
    elif bid == "link":
        fmt_link_md(page)
    elif bid == "image":
        insert_image_at_end(page, kind="image")
    elif bid == "icon":
        insert_image_at_end(page, kind="icon")
    elif bid == "time":
        page._insert_timestamp()
    else:
        on_palette_insert(page, bid)


def insert_native_markdown_block(page, block_id: str) -> bool:
    bid = str(block_id or "").strip()
    if bid == "image":
        return insert_image_at_end(page, kind="image")
    if bid == "icon":
        return insert_image_at_end(page, kind="icon")
    if bid == "highlight":
        from modules.quick_notepad.rich_body import apply_highlight_to_selection

        page._ensure_writable()
        apply_highlight_to_selection(page._md_source)
        _after(page, scroll_end=True)
        page.report_status("已插入「高亮」· 文末", level=StatusLevel.SUCCESS)
        return True
    md = markdown_for_block(bid)
    if not md.strip():
        return False
    page._ensure_writable()
    if not insert_markdown_snippet(page._md_source, md, at_end=True):
        return False
    _after(page, scroll_end=True)
    spec = get_block(bid)
    page.report_status(
        f"已插入「{spec.title if spec else bid}」· 文末",
        level=StatusLevel.SUCCESS,
    )
    return True


def on_palette_insert(page, block_id: str) -> None:
    if not insert_native_markdown_block(page, block_id):
        show_warning(page, "无法插入该组件。")
