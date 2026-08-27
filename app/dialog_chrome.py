# -*- coding: utf-8 -*-
"""顶栏弹窗共用骨架：关于 / 用户信息等统一风格。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from widgets import FormSection, HintLabel, PageTitle


def apply_dialog_root(layout: QVBoxLayout) -> None:
    layout.setSpacing(14)
    layout.setContentsMargins(20, 18, 20, 16)


def add_dialog_hero(
    root: QVBoxLayout,
    *,
    pixmap: QPixmap | None,
    title: str,
    subtitle: str,
    icon_size: int = 56,
) -> None:
    """首行：品牌图/头像 + 标题 + 副标题。"""
    row = QHBoxLayout()
    row.setSpacing(14)
    if pixmap is not None and not pixmap.isNull():
        mark = QLabel()
        mark.setFixedSize(icon_size, icon_size)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(pixmap)
        row.addWidget(mark)
    col = QVBoxLayout()
    col.setSpacing(4)
    title_lbl = PageTitle(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    col.addWidget(title_lbl)
    if subtitle:
        col.addWidget(HintLabel(subtitle))
    row.addLayout(col, 1)
    root.addLayout(row)


def make_info_form() -> QFormLayout:
    form = QFormLayout()
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(8)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return form


def add_form_section(root: QVBoxLayout, title: str, form: QFormLayout) -> FormSection:
    sec = FormSection(title)
    wrap = QWidget()
    wrap.setLayout(form)
    sec.add_widget(wrap)
    root.addWidget(sec)
    return sec


def value_label(text: str, *, selectable: bool = False) -> QLabel:
    lbl = QLabel(text or "—")
    lbl.setWordWrap(True)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl
