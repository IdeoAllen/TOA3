# -*- coding: utf-8 -*-
"""所见即所得里的实际编辑：开关格式、套当前段、链接、查找替换。"""
from __future__ import annotations

import re

from PySide6.QtGui import (
    QColor,
    QFont,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextListFormat,
)
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from modules.quick_notepad.rich_body import _HL_PROP, highlight_char_format
from widgets import HintLabel, LineEdit, SecondaryButton
from widgets.dialog_actions import DialogButtonRow

_MONO = ("cascadia", "consolas", "courier", "monospace")
_HEADING_RE = re.compile(r"^#{1,6}$")
_OL_RE = re.compile(r"^\d+\.$")


def _edit(page):
    page._ensure_writable()
    return page._md_source


def _cursor_char_format(edit) -> QTextCharFormat:
    cur = edit.textCursor()
    if cur.hasSelection():
        probe = QTextCursor(edit.document())
        probe.setPosition(cur.selectionStart())
        probe.movePosition(
            QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
        )
        return probe.charFormat()
    return cur.charFormat()


def _merge(edit, fmt: QTextCharFormat) -> None:
    cur = edit.textCursor()
    cur.mergeCharFormat(fmt)
    edit.mergeCurrentCharFormat(fmt)
    edit.setTextCursor(cur)


def _is_mono(fmt: QTextCharFormat) -> bool:
    fam = " ".join(fmt.fontFamilies()).lower()
    return any(name in fam for name in _MONO)


def _is_highlight(fmt: QTextCharFormat) -> bool:
    if str(fmt.property(_HL_PROP) or "") == "1":
        return True
    bg = fmt.background().color()
    if not bg.isValid():
        return False
    return (
        abs(bg.red() - 0xFE) < 20
        and abs(bg.green() - 0xF0) < 25
        and abs(bg.blue() - 0x8A) < 30
    )


def toggle_inline(page, kind: str) -> None:
    """加粗 / 斜体 / 删除线 / 行内代码 / 高亮：再按一次取消。"""
    edit = _edit(page)
    fmt_now = _cursor_char_format(edit)
    fmt = QTextCharFormat()
    if kind == "bold":
        fmt.setFontWeight(
            QFont.Weight.Normal
            if fmt_now.fontWeight() >= QFont.Weight.Bold
            else QFont.Weight.Bold
        )
    elif kind == "italic":
        fmt.setFontItalic(not fmt_now.fontItalic())
    elif kind == "strike":
        fmt.setFontStrikeOut(not fmt_now.fontStrikeOut())
    elif kind == "inline_code":
        if _is_mono(fmt_now):
            fmt.setFontFamilies([edit.font().family() or "Microsoft YaHei UI"])
        else:
            fmt.setFontFamilies(["Cascadia Code", "Consolas", "Courier New", "monospace"])
    elif kind == "highlight":
        if _is_highlight(fmt_now):
            fmt.setProperty(_HL_PROP, "0")
            fmt.setBackground(QColor("#FFFFFF"))
        else:
            fmt = highlight_char_format()
            if not edit.textCursor().hasSelection():
                cur = edit.textCursor()
                cur.insertText("高亮重点", fmt)
                edit.setTextCursor(cur)
                page._after_md_mutation()
                return
    else:
        return
    if not edit.textCursor().hasSelection() and kind in (
        "bold",
        "italic",
        "strike",
        "inline_code",
    ):
        edit.mergeCurrentCharFormat(fmt)
        page._after_md_mutation()
        return
    _merge(edit, fmt)
    page._after_md_mutation()


def _is_quote_block(cur: QTextCursor) -> bool:
    bf = cur.blockFormat()
    return bf.leftMargin() >= 30 and bf.rightMargin() >= 30


def apply_heading(page, level: int) -> None:
    edit = _edit(page)
    cur = edit.textCursor()
    current = int(cur.blockFormat().headingLevel() or 0)
    bf = QTextBlockFormat(cur.blockFormat())
    bf.setHeadingLevel(0 if current == level else level)
    cur.mergeBlockFormat(bf)
    edit.setTextCursor(cur)
    page._after_md_mutation()


def apply_list(page, ordered: bool) -> None:
    edit = _edit(page)
    cur = edit.textCursor()
    want = (
        QTextListFormat.Style.ListDecimal if ordered else QTextListFormat.Style.ListDisc
    )
    lst = cur.currentList()
    if lst is not None and lst.format().style() == want:
        lst.remove(cur.block())
        edit.setTextCursor(cur)
        page._after_md_mutation()
        return
    if lst is not None:
        lst.remove(cur.block())
    lf = QTextListFormat()
    lf.setStyle(want)
    cur.createList(lf)
    edit.setTextCursor(cur)
    page._after_md_mutation()


def apply_quote(page) -> None:
    edit = _edit(page)
    cur = edit.textCursor()
    if _is_quote_block(cur):
        bf = QTextBlockFormat(cur.blockFormat())
        bf.setLeftMargin(0)
        bf.setRightMargin(0)
        bf.setTopMargin(0)
        bf.setBottomMargin(0)
        cur.setBlockFormat(bf)
        edit.setTextCursor(cur)
        page._after_md_mutation()
        return
    text = cur.block().text()
    cur.select(QTextCursor.SelectionType.BlockUnderCursor)
    sample = f"> {text}\n" if text else "> 引用\n"
    cur.insertMarkdown(sample)
    edit.setTextCursor(cur)
    page._after_md_mutation()


def apply_link(page, text: str, url: str) -> None:
    edit = _edit(page)
    cur = edit.textCursor()
    href = (url or "").strip() or "https://"
    label = (text or "").strip() or "链接"
    fmt = QTextCharFormat()
    fmt.setAnchor(True)
    fmt.setAnchorHref(href)
    fmt.setFontUnderline(True)
    fmt.setForeground(QColor("#2563EB"))
    if cur.hasSelection():
        cur.mergeCharFormat(fmt)
    else:
        cur.insertText(label, fmt)
    edit.setTextCursor(cur)
    page._after_md_mutation()


def clear_format(page) -> None:
    """去掉当前选区字样，以及当前段的标题、列表、引用。"""
    edit = _edit(page)
    cur = edit.textCursor()
    if not cur.hasSelection():
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
    plain = QTextCharFormat()
    plain.setFontWeight(QFont.Weight.Normal)
    plain.setFontItalic(False)
    plain.setFontStrikeOut(False)
    plain.setFontUnderline(False)
    plain.setAnchor(False)
    plain.setAnchorHref("")
    plain.setProperty(_HL_PROP, "0")
    plain.setBackground(QColor("#FFFFFF"))
    plain.setFontFamilies([edit.font().family() or "Microsoft YaHei UI"])
    cur.setCharFormat(plain)
    lst = cur.currentList()
    if lst is not None:
        lst.remove(cur.block())
    bf = QTextBlockFormat()
    bf.setHeadingLevel(0)
    cur.setBlockFormat(bf)
    edit.mergeCurrentCharFormat(QTextCharFormat())
    edit.setTextCursor(cur)
    page._after_md_mutation()


def try_marker_shortcut(edit) -> bool:
    """行首写完标记再按空格，直接套成标题 / 列表 / 引用。"""
    if edit is None or edit.isReadOnly():
        return False
    cur = edit.textCursor()
    if cur.hasSelection():
        return False
    block = cur.block()
    if block is None:
        return False
    col = cur.positionInBlock()
    head = block.text()[:col]
    level = 0
    kind = ""
    if _HEADING_RE.fullmatch(head):
        level = len(head)
        kind = "h"
    elif head in ("-", "*"):
        kind = "ul"
    elif head == ">":
        kind = "quote"
    elif _OL_RE.fullmatch(head):
        kind = "ol"
    else:
        return False
    cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
    cur.movePosition(
        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, col
    )
    cur.removeSelectedText()
    if kind == "h":
        bf = QTextBlockFormat(cur.blockFormat())
        bf.setHeadingLevel(level)
        cur.mergeBlockFormat(bf)
    elif kind == "quote":
        text = cur.block().text()
        cur.select(QTextCursor.SelectionType.BlockUnderCursor)
        cur.insertMarkdown(f"> {text}\n" if text else "> \n")
    else:
        lf = QTextListFormat()
        lf.setStyle(
            QTextListFormat.Style.ListDecimal
            if kind == "ol"
            else QTextListFormat.Style.ListDisc
        )
        existing = cur.currentList()
        if existing is not None:
            existing.remove(cur.block())
        cur.createList(lf)
    edit.setTextCursor(cur)
    return True


class _FindReplaceDialog(BaseDialog):
    dialog_kind = "small"

    def __init__(self, parent, edit) -> None:
        super().__init__(parent)
        self._edit = edit
        self.setWindowTitle("查找替换")
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        row_f = QHBoxLayout()
        row_f.addWidget(HintLabel("查找"))
        self._find = LineEdit()
        self._find.setPlaceholderText("要查找的文字")
        row_f.addWidget(self._find, 1)
        lay.addLayout(row_f)
        row_r = QHBoxLayout()
        row_r.addWidget(HintLabel("替换"))
        self._replace = LineEdit()
        self._replace.setPlaceholderText("留空则只查找")
        row_r.addWidget(self._replace, 1)
        lay.addLayout(row_r)
        actions = QHBoxLayout()
        nxt = SecondaryButton("下一个")
        one = SecondaryButton("替换")
        all_btn = SecondaryButton("全部替换")
        nxt.clicked.connect(self._next)
        one.clicked.connect(self._one)
        all_btn.clicked.connect(self._all)
        actions.addWidget(nxt)
        actions.addWidget(one)
        actions.addWidget(all_btn)
        actions.addStretch(1)
        lay.addLayout(actions)
        row = DialogButtonRow(self)
        row.add_primary("关闭", self.accept)
        lay.addWidget(row)

    def _needle(self) -> str:
        return self._find.text()

    def _next(self) -> None:
        needle = self._needle()
        if not needle:
            return
        if not self._edit.find(needle):
            cur = self._edit.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.Start)
            self._edit.setTextCursor(cur)
            self._edit.find(needle)

    def _one(self) -> None:
        cur = self._edit.textCursor()
        if cur.hasSelection() and cur.selectedText() == self._needle():
            cur.insertText(self._replace.text())
            self._edit.setTextCursor(cur)
            return
        self._next()

    def _all(self) -> None:
        needle = self._needle()
        if not needle:
            return
        cur = self._edit.textCursor()
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.Start)
        self._edit.setTextCursor(cur)
        n = 0
        while self._edit.find(needle):
            sel = self._edit.textCursor()
            sel.insertText(self._replace.text())
            n += 1
            if n > 5000:
                break
        cur.endEditBlock()


def open_find_replace(page) -> None:
    from modules.quick_notepad.note_store import normalize_view_mode

    mode = normalize_view_mode(getattr(page, "_view_mode", "edit"))
    edit = page._md_raw if mode == "source" else page._md_source
    dlg = _FindReplaceDialog(page, edit)
    dlg.exec()


def replace_all(edit, needle: str, repl: str) -> int:
    if not needle:
        return 0
    cur = edit.textCursor()
    cur.beginEditBlock()
    cur.movePosition(QTextCursor.MoveOperation.Start)
    edit.setTextCursor(cur)
    n = 0
    while edit.find(needle):
        sel = edit.textCursor()
        sel.insertText(repl)
        n += 1
        if n > 5000:
            break
    cur.endEditBlock()
    return n
