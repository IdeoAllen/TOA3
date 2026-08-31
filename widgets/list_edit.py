# -*- coding: utf-8 -*-
"""标准 List + Edit / 管理功能套件（控件库）。

- ``ListPanel``：简单列表 + 新增/编辑/删除
- ``ManageTablePanel``：筛选 + 新增 + 表格 + 行操作（编辑/删除/详情）
  —— 后续「管理功能」或按表字段搭页，优先用本模式
- ``FormEditDialog``：字段表单弹窗
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_dialog import BaseDialog
from widgets.buttons import DangerButton, PrimaryButton, SecondaryButton
from widgets.containers import FormSection
from widgets.displays import DataTable, ListWidget
from widgets.inputs import ComboBox, LineEdit
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


class ManageTablePanel(QWidget):
    """
    管理功能标准壳（List+Edit 表格版）。

    布局：筛选区 → 工具栏（新增 + 行操作）→ DataTable。
    按表字段搭管理页时，优先组合本控件 + ``FormEditDialog``。
    """

    filter_changed = Signal()
    selection_changed = Signal(int)

    def __init__(
        self,
        parent=None,
        *,
        title: str = "数据列表",
        hint: str = "",
        search_placeholder: str = "搜索关键字…",
        add_label: str = "新增",
        edit_label: str = "编辑",
        delete_label: str = "删除",
        detail_label: str = "详情",
        show_detail: bool = True,
        filter_options: list[tuple[str, list[str]]] | None = None,
        filter_keys: list[str] | None = None,
    ) -> None:
        """
        filter_options: [("状态", ["全部", "启用", "停用"]), ...]
        filter_keys: 与 filter_options 一一对应的行字段名，默认猜测 status / 第 i 列。
        """
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._columns: list[str] = []
        self._keys: list[str] = []
        self._filter_keys = list(filter_keys or [])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        section = FormSection(title)
        if hint:
            section.add_widget(HintLabel(hint))

        # 筛选行
        filt = QHBoxLayout()
        self._search = LineEdit()
        self._search.setPlaceholderText(search_placeholder)
        self._search.setMinimumHeight(32)
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda *_: self.filter_changed.emit())
        self._search.returnPressed.connect(lambda: self.filter_changed.emit())
        filt.addWidget(self._search, 1)

        self._filter_combos: list[ComboBox] = []
        opts = list(filter_options or [])
        for i, (label, options) in enumerate(opts):
            filt.addWidget(HintLabel(label))
            cb = ComboBox()
            cb.addItems([str(o) for o in options])
            cb.currentIndexChanged.connect(lambda *_: self.filter_changed.emit())
            self._filter_combos.append(cb)
            filt.addWidget(cb)
            if i >= len(self._filter_keys):
                # 默认：状态 → status
                guess = "status" if "状态" in label else f"_filter_{i}"
                self._filter_keys.append(guess)
        section.add_layout(filt)

        # 工具栏：新增 + 行操作
        tools = QHBoxLayout()
        self._btn_add = PrimaryButton(add_label)
        self._btn_edit = SecondaryButton(edit_label)
        self._btn_detail = SecondaryButton(detail_label)
        self._btn_del = DangerButton(delete_label)
        for b in (self._btn_add, self._btn_edit, self._btn_detail, self._btn_del):
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        tools.addWidget(self._btn_add)
        tools.addWidget(self._btn_edit)
        if show_detail:
            tools.addWidget(self._btn_detail)
        else:
            self._btn_detail.hide()
        tools.addWidget(self._btn_del)
        tools.addStretch(1)
        section.add_layout(tools)

        self._table = DataTable(0, 0)
        self._table.setMinimumHeight(220)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.itemSelectionChanged.connect(self._on_sel)
        self._table.itemDoubleClicked.connect(lambda *_: self._handle_edit())
        section.add_widget(self._table, 1)
        root.addWidget(section, 1)

        self._on_add: Callable | None = None
        self._on_edit: Callable[[dict[str, Any]], None] | None = None
        self._on_delete: Callable[[dict[str, Any]], None] | None = None
        self._on_detail: Callable[[dict[str, Any]], None] | None = None

        self._btn_add.clicked.connect(self._handle_add)
        self._btn_edit.clicked.connect(self._handle_edit)
        self._btn_del.clicked.connect(self._handle_delete)
        self._btn_detail.clicked.connect(self._handle_detail)
        self.filter_changed.connect(self.refresh_view)
        self._set_row_actions(False)

    @property
    def table(self) -> DataTable:
        return self._table

    @property
    def search_text(self) -> str:
        return self._search.text().strip()

    def filter_values(self) -> list[str]:
        return [cb.currentText().strip() for cb in self._filter_combos]

    def bind_add(self, fn: Callable) -> None:
        self._on_add = fn

    def bind_edit(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._on_edit = fn

    def bind_delete(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._on_delete = fn

    def bind_detail(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._on_detail = fn

    def bind_filter(self, fn: Callable) -> None:
        self.filter_changed.connect(fn)

    def set_columns(self, columns: list[tuple[str, str]]) -> None:
        """columns: [(表头显示名, 字段 key), ...]"""
        self._columns = [c[0] for c in columns]
        self._keys = [c[1] for c in columns]
        self._table.setColumnCount(len(self._columns))
        self._table.set_headers(self._columns)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """设置全量行；内部按当前筛选刷新显示。"""
        self._rows = list(rows or [])
        self.refresh_view()

    def refresh_view(self) -> None:
        from PySide6.QtWidgets import QTableWidgetItem

        q = self.search_text.lower()
        filters = self.filter_values()
        shown: list[dict[str, Any]] = []
        for row in self._rows:
            if q:
                blob = " ".join(str(row.get(k) or "") for k in self._keys).lower()
                if q not in blob:
                    continue
            skip = False
            for i, fv in enumerate(filters):
                if not fv or fv in ("全部", "所有", "*"):
                    continue
                if i < len(self._filter_keys):
                    key = self._filter_keys[i]
                elif i < len(self._keys):
                    key = self._keys[i]
                else:
                    key = f"_filter_{i}"
                cell = str(row.get(key) or "")
                if cell != fv and fv not in cell:
                    skip = True
                    break
            if skip:
                continue
            shown.append(row)

        self._table.setRowCount(0)
        for i, row in enumerate(shown):
            self._table.insertRow(i)
            for c, key in enumerate(self._keys):
                item = QTableWidgetItem(str(row.get(key) or ""))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._table.setItem(i, c, item)
        self._set_row_actions(False)

    def current_row_data(self) -> dict[str, Any] | None:
        r = self._table.currentRow()
        if r < 0:
            return None
        item = self._table.item(r, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_sel(self) -> None:
        data = self.current_row_data()
        self._set_row_actions(data is not None)
        self.selection_changed.emit(self._table.currentRow())

    def _set_row_actions(self, on: bool) -> None:
        self._btn_edit.setEnabled(on)
        self._btn_del.setEnabled(on)
        self._btn_detail.setEnabled(on)

    def _handle_add(self) -> None:
        if self._on_add:
            self._on_add()

    def _handle_edit(self) -> None:
        data = self.current_row_data()
        if data is not None and self._on_edit:
            self._on_edit(data)

    def _handle_delete(self) -> None:
        data = self.current_row_data()
        if data is not None and self._on_delete:
            self._on_delete(data)

    def _handle_detail(self) -> None:
        data = self.current_row_data()
        if data is not None and self._on_detail:
            self._on_detail(data)


def manage_panel_from_fields(
    fields: list[tuple[str, str]],
    *,
    title: str = "数据列表",
    hint: str = "",
    parent=None,
) -> ManageTablePanel:
    """
    按表字段快速搭管理壳。

    fields: [("名称", "name"), ("状态", "status"), ...]
    返回已设好列的 ManageTablePanel，业务侧 set_rows + bind_* 即可。
    """
    has_status = any(k == "status" or h == "状态" for h, k in fields)
    panel = ManageTablePanel(
        parent,
        title=title,
        hint=hint or "筛选 → 新增 → 选中行后编辑 / 删除 / 详情",
        filter_options=[("状态", ["全部", "启用", "停用"])] if has_status else None,
        filter_keys=["status"] if has_status else None,
    )
    panel.set_columns(fields)
    return panel


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
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._fields = list(fields or [])
        self._edits: dict[str, LineEdit] = {}
        self._read_only = bool(read_only)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        form_host = QWidget()
        form = QVBoxLayout(form_host)
        form.setSpacing(10)
        for label, key in self._fields:
            row = QHBoxLayout()
            row.addWidget(HintLabel(label))
            edit = LineEdit()
            if not self._read_only:
                edit.returnPressed.connect(self.accept)
            else:
                edit.setReadOnly(True)
            self._edits[key] = edit
            row.addWidget(edit, 1)
            form.addLayout(row)
        lay.addWidget(form_host)

        from widgets.dialog_actions import DialogButtonRow

        buttons = DialogButtonRow()
        if self._read_only:
            buttons.add_primary("关闭", self.accept)
        else:
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
