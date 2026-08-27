# -*- coding: utf-8 -*-
"""标准 List + Edit 增删改查套件（控件库）。"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_dialog import BaseDialog
from widgets.buttons import DangerButton, PrimaryButton, SecondaryButton
from widgets.displays import ListWidget
from widgets.inputs import LineEdit
from widgets.themed_labels import HintLabel


class ListPanel(QWidget):
    """列表 + 标准操作栏：新增 / 编辑 / 删除 / 刷新。"""

    def __init__(
        self,
        parent=None,
        *,
        add_label: str = "新增",
        edit_label: str = "编辑",
        delete_label: str = "删除",
        refresh_label: str = "刷新",
        hint: str = "",
        show_refresh: bool = True,
    ) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        if hint:
            root.addWidget(HintLabel(hint))

        self._list = ListWidget()
        root.addWidget(self._list, 1)

        row = QHBoxLayout()
        self._btn_add = PrimaryButton(add_label)
        self._btn_edit = SecondaryButton(edit_label)
        self._btn_del = DangerButton(delete_label)
        self._btn_refresh = SecondaryButton(refresh_label)
        for b in (self._btn_add, self._btn_edit, self._btn_del, self._btn_refresh):
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        row.addWidget(self._btn_add)
        row.addWidget(self._btn_edit)
        row.addWidget(self._btn_del)
        if show_refresh and refresh_label:
            row.addWidget(self._btn_refresh)
        else:
            self._btn_refresh.hide()
        row.addStretch(1)
        root.addLayout(row)

        self._on_add: Callable | None = None
        self._on_edit: Callable | None = None
        self._on_delete: Callable | None = None
        self._on_refresh: Callable | None = None

        self._btn_add.clicked.connect(self._handle_add)
        self._btn_edit.clicked.connect(self._handle_edit)
        self._btn_del.clicked.connect(self._handle_delete)
        self._btn_refresh.clicked.connect(self._handle_refresh)

    @property
    def list_widget(self) -> ListWidget:
        return self._list

    def bind_add(self, fn: Callable) -> None:
        self._on_add = fn

    def bind_edit(self, fn: Callable) -> None:
        self._on_edit = fn

    def bind_delete(self, fn: Callable) -> None:
        self._on_delete = fn

    def bind_refresh(self, fn: Callable) -> None:
        self._on_refresh = fn

    def set_items(self, items: list[str]) -> None:
        self._list.clear()
        for text in items:
            self._list.addItem(text)

    def current_row(self) -> int:
        return self._list.currentRow()

    def current_text(self) -> str:
        item = self._list.currentItem()
        return item.text() if item else ""

    def _handle_add(self) -> None:
        if self._on_add:
            self._on_add()

    def _handle_edit(self) -> None:
        if self._on_edit:
            self._on_edit()

    def _handle_delete(self) -> None:
        if self._on_delete:
            self._on_delete()

    def _handle_refresh(self) -> None:
        if self._on_refresh:
            self._on_refresh()


class FormEditDialog(BaseDialog):
    """通用表单编辑对话框。"""

    dialog_kind = "medium"

    def __init__(
        self,
        parent=None,
        *,
        title: str = "编辑",
        fields: list[tuple[str, str]] | None = None,
        ok_text: str = "确定",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._fields = list(fields or [])
        self._edits: dict[str, LineEdit] = {}

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        form_host = QWidget()
        form = QVBoxLayout(form_host)
        form.setSpacing(10)
        for label, key in self._fields:
            row = QHBoxLayout()
            row.addWidget(HintLabel(label))
            edit = LineEdit()
            # 回车等同点确定（保存/确认）
            edit.returnPressed.connect(self.accept)
            self._edits[key] = edit
            row.addWidget(edit, 1)
            form.addLayout(row)
        lay.addWidget(form_host)

        from widgets.dialog_actions import DialogButtonRow

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary(ok_text, self.accept)
        lay.addWidget(buttons)

    def set_values(self, data: dict[str, Any]) -> None:
        for key, edit in self._edits.items():
            edit.setText(str(data.get(key) or ""))

    def values(self) -> dict[str, str]:
        return {key: edit.text().strip() for key, edit in self._edits.items()}


def confirm_delete(parent, what: str = "选中项") -> bool:
    from core.error_handler import confirm

    return confirm(parent, f"确定删除{what}？此操作不可恢复。")
