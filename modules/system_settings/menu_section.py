# -*- coding: utf-8 -*-
"""系统设置 · 菜单配置（用户可维护，写入 data/user/menu.yml）。"""
from __future__ import annotations

import re
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QSizePolicy,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.base_dialog import BaseDialog
from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.config_service import (
    get_all_menu_items,
    load_config,
    reset_user_menu,
    save_menu_items,
    user_menu_path,
)
from services.menu_registry import GROUP_LABELS, GROUP_ORDER, MIGRATED_MODULES
from services.migration_manifest import status_label
from services.notify_bus import request_nav_rebuild
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PrimaryButton,
    SecondaryButton,
    TreeWidget,
)
from widgets.dialog_actions import DialogButtonRow

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def _default_menu_templates() -> list[dict]:
    cfg = load_config()
    menu = cfg.get("menu") or {}
    return [i for i in (menu.get("menu_items") or []) if isinstance(i, dict)]


class _AddMenuItemDialog(BaseDialog):
    """新增菜单项：可从 app.yml 默认项快捷填入，或手动指定模块 ID。"""

    dialog_kind = "medium"

    def __init__(
        self,
        parent: BasePage,
        *,
        existing_ids: set[str],
        templates: list[dict],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("新增菜单项")
        self._existing_ids = existing_ids
        self._templates = templates

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            HintLabel(
                "模块 ID 须小写英文/数字/下划线，且不与现有项重复。\n"
                "可从下方快捷选择尚未加入菜单的默认模块，再微调名称与分组。"
            )
        )

        form = QFormLayout()
        self._preset = ComboBox()
        self._preset.addItem("（手动填写）", None)
        for tpl in templates:
            mid = str(tpl.get("id") or "")
            if not mid or mid in existing_ids:
                continue
            name = str(tpl.get("name") or mid)
            self._preset.addItem(f"{name}  [{mid}]", tpl)
        self._preset.currentIndexChanged.connect(self._on_preset)
        form.addRow("快捷填入", self._preset)

        self._mid = LineEdit()
        self._mid.setPlaceholderText("例如 my_module")
        form.addRow("模块 ID", self._mid)
        self._name = LineEdit()
        self._name.setPlaceholderText("侧栏显示名称")
        form.addRow("名称", self._name)
        self._desc = LineEdit()
        self._desc.setPlaceholderText("可选说明")
        form.addRow("说明", self._desc)
        self._icon = LineEdit()
        self._icon.setPlaceholderText("图标键，默认同模块 ID")
        form.addRow("图标", self._icon)
        self._group = ComboBox()
        for gid in GROUP_ORDER:
            self._group.addItem(GROUP_LABELS.get(gid, gid), gid)
        form.addRow("分组", self._group)
        self._show = CheckBox("在菜单中显示")
        self._show.setChecked(True)
        form.addRow("", self._show)
        lay.addLayout(form)

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("添加", self._accept)
        lay.addWidget(buttons)

        for edit in (self._mid, self._name, self._desc, self._icon):
            edit.returnPressed.connect(self._accept)

    def _on_preset(self, _idx: int) -> None:
        tpl = self._preset.currentData()
        if not isinstance(tpl, dict):
            return
        mid = str(tpl.get("id") or "")
        self._mid.setText(mid)
        self._name.setText(str(tpl.get("name") or mid))
        self._desc.setText(str(tpl.get("desc") or ""))
        self._icon.setText(str(tpl.get("icon") or mid))
        gid = str(tpl.get("group") or "business")
        gidx = self._group.findData(gid)
        self._group.setCurrentIndex(gidx if gidx >= 0 else 0)
        self._show.setChecked(bool(tpl.get("show", True)))

    def _accept(self) -> None:
        mid = self._mid.text().strip().lower()
        name = self._name.text().strip()
        if not mid:
            show_warning(self, "请填写模块 ID。")
            return
        if not _ID_RE.match(mid):
            show_warning(self, "模块 ID 格式无效：小写字母开头，仅含 a-z、0-9、下划线。")
            return
        if mid in self._existing_ids:
            show_warning(self, f"模块 ID「{mid}」已存在于菜单中。")
            return
        if not name:
            show_warning(self, "请填写显示名称。")
            return
        if mid not in MIGRATED_MODULES and mid not in ("__about__",):
            show_warning(
                self,
                f"模块「{mid}」尚未在 TOA3 注册页面，添加后侧栏可能无法打开。\n"
                "仍可使用占位菜单，待模块开发完成后再启用。",
            )
        self.accept()

    def build_item(self) -> dict:
        mid = self._mid.text().strip().lower()
        tpl = self._preset.currentData()
        if isinstance(tpl, dict) and str(tpl.get("id") or "") == mid:
            item = deepcopy(tpl)
        else:
            item = {
                "id": mid,
                "feature_id": mid,
                "requires_license": True,
                "show": True,
            }
        item["id"] = mid
        item["name"] = self._name.text().strip() or mid
        item["desc"] = self._desc.text().strip()
        item["icon"] = self._icon.text().strip() or mid
        item["group"] = self._group.currentData() or "business"
        item["show"] = self._show.isChecked()
        return item


class MenuSection(QWidget):
    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._items: list[dict] = []
        self._suppress = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        box = FormSection("菜单配置")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        box.add_widget(
            HintLabel(
                "顶栏子模块（子系统）名称固定（首页 / 办公 / 图片…）；要改功能模块归属，请展开后选中具体模块，"
                "在右侧改「分组（子模块）」并点「保存菜单」。\n"
                "侧栏是否显示由「在菜单中显示」决定，与 done/mvp 状态无关；隐藏项也会出现在本列表中。\n"
                f"保存到 {user_menu_path()}；「恢复默认」删除用户覆盖后用 app.yml。"
            )
        )

        mid_host = QWidget()
        mid_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        mid = QHBoxLayout(mid_host)
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(12)

        self._tree = TreeWidget()
        self._tree.setMinimumHeight(200)
        self._tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tree.currentItemChanged.connect(self._on_select)
        mid.addWidget(self._tree, 2)

        edit = FormSection("编辑选中项")
        edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._name = LineEdit()
        self._id = LineEdit()
        self._id.setReadOnly(True)
        self._desc = LineEdit()
        self._icon = LineEdit()
        self._group = ComboBox()
        for gid in GROUP_ORDER:
            self._group.addItem(GROUP_LABELS.get(gid, gid), gid)
        self._show = CheckBox("在菜单中显示")
        self._show.setChecked(True)

        form = QFormLayout()
        form.addRow("名称", self._name)
        form.addRow("模块 ID", self._id)
        form.addRow("说明", self._desc)
        form.addRow("图标", self._icon)
        form.addRow("分组", self._group)
        form.addRow("", self._show)
        edit.add_layout(form)

        for w in (self._name, self._desc, self._icon):
            w.textChanged.connect(self._apply_fields)
        self._group.currentIndexChanged.connect(self._apply_fields)
        self._show.toggled.connect(self._apply_fields)

        mid.addWidget(edit, 1)
        box.add_widget(mid_host, 1)

        row = QHBoxLayout()
        btn_add = PrimaryButton("新增")
        btn_add.clicked.connect(self._add_item)
        row.addWidget(btn_add)
        btn_up = SecondaryButton("上移")
        btn_up.clicked.connect(lambda: self._move(-1))
        row.addWidget(btn_up)
        btn_down = SecondaryButton("下移")
        btn_down.clicked.connect(lambda: self._move(1))
        row.addWidget(btn_down)
        btn_save = PrimaryButton("保存菜单")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        btn_reload = SecondaryButton("重新加载")
        btn_reload.clicked.connect(self.reload)
        row.addWidget(btn_reload)
        btn_reset = SecondaryButton("恢复默认")
        btn_reset.clicked.connect(self._reset)
        row.addWidget(btn_reset)
        row.addStretch(1)
        box.add_layout(row)

        lay.addWidget(box, 1)
        self.reload()

    def reload(self) -> None:
        keep_id = self._current_item_id()
        self._items = deepcopy(get_all_menu_items())
        self._refresh_tree(keep_id=keep_id)

    def _existing_ids(self) -> set[str]:
        return {str(it.get("id") or "") for it in self._items if str(it.get("id") or "")}

    def _add_item(self) -> None:
        dlg = _AddMenuItemDialog(
            self._page,
            existing_ids=self._existing_ids(),
            templates=_default_menu_templates(),
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        item = dlg.build_item()
        mid = str(item.get("id") or "")
        item["order"] = len(self._items) + 1
        self._items.append(item)
        self._refresh_tree(keep_id=mid)
        self._page.report_status(f"已添加菜单项：{item.get('name') or mid}（记得点保存菜单）")

    def _current_item_id(self) -> str | None:
        idx = self._current_item_index()
        if idx is None or idx < 0 or idx >= len(self._items):
            return None
        return str(self._items[idx].get("id") or "")

    def _current_item_index(self) -> int | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return None
        try:
            return int(data)
        except (TypeError, ValueError):
            return None

    def _item_label(self, it: dict) -> str:
        mid = str(it.get("id") or "")
        name = str(it.get("name") or mid)
        show = "显示" if it.get("show", True) else "隐藏"
        st = status_label(mid) if mid else ""
        return f"{name}  [{mid}]  · {show} · {st}"

    def _make_group_node(self, label: str, count: int) -> QTreeWidgetItem:
        node = QTreeWidgetItem([f"▾ {label}  ({count})"])
        node.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = node.font(0)
        font.setBold(True)
        node.setFont(0, font)
        return node

    def _make_leaf(self, idx: int, it: dict) -> QTreeWidgetItem:
        leaf = QTreeWidgetItem([self._item_label(it)])
        leaf.setData(0, Qt.ItemDataRole.UserRole, idx)
        return leaf

    def _select_by_id(self, module_id: str) -> None:
        if not module_id:
            return
        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            if group is None:
                continue
            for j in range(group.childCount()):
                child = group.child(j)
                if child is None:
                    continue
                idx = child.data(0, Qt.ItemDataRole.UserRole)
                if idx is None or idx < 0 or idx >= len(self._items):
                    continue
                if str(self._items[idx].get("id") or "") == module_id:
                    self._tree.setCurrentItem(child)
                    group.setExpanded(True)
                    return

    def _refresh_tree(self, *, keep_id: str | None = None) -> None:
        keep_id = keep_id or self._current_item_id()
        self._tree.clear()

        buckets: dict[str, list[tuple[int, dict]]] = {g: [] for g in GROUP_ORDER}
        other: list[tuple[int, dict]] = []
        for idx, it in enumerate(self._items):
            gid = str(it.get("group") or "business").lower()
            if gid in buckets:
                buckets[gid].append((idx, it))
            else:
                other.append((idx, it))

        for gid in GROUP_ORDER:
            entries = buckets[gid]
            if not entries:
                continue
            root = self._make_group_node(GROUP_LABELS.get(gid, gid), len(entries))
            self._tree.addTopLevelItem(root)
            for idx, it in entries:
                root.addChild(self._make_leaf(idx, it))
            root.setExpanded(True)

        if other:
            root = self._make_group_node("其它", len(other))
            self._tree.addTopLevelItem(root)
            for idx, it in other:
                root.addChild(self._make_leaf(idx, it))
            root.setExpanded(True)

        if keep_id:
            self._select_by_id(keep_id)
        elif self._items:
            first = self._tree.topLevelItem(0)
            if first is not None and first.childCount() > 0:
                self._tree.setCurrentItem(first.child(0))

    def _on_select(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        idx = self._current_item_index()
        if idx is None:
            self._suppress = True
            self._name.clear()
            self._id.clear()
            self._desc.clear()
            self._icon.clear()
            self._group.setCurrentIndex(0)
            self._show.setChecked(False)
            self._group.setEnabled(False)
            self._show.setEnabled(False)
            self._suppress = False
            self._page.report_status("选中一级分组无效：请点选下方具体模块再编辑")
            return
        self._suppress = True
        it = self._items[idx]
        mid = str(it.get("id") or "")
        self._name.setText(str(it.get("name") or ""))
        self._id.setText(mid)
        self._desc.setText(str(it.get("desc") or ""))
        self._icon.setText(str(it.get("icon") or ""))
        gid = str(it.get("group") or "business")
        gidx = self._group.findData(gid, Qt.ItemDataRole.UserRole)
        if gidx < 0:
            gidx = self._group.findText(GROUP_LABELS.get(gid, gid))
        self._group.setCurrentIndex(gidx if gidx >= 0 else 0)
        self._show.setChecked(bool(it.get("show", True)))
        locked = mid in ("home", "system_settings", "theme_preview")
        self._group.setEnabled(not locked)
        self._show.setEnabled(mid != "home")
        self._suppress = False

    def _apply_fields(self, *_args) -> None:
        if self._suppress:
            return
        row = self._current_item_index()
        if row is None or row < 0 or row >= len(self._items):
            return
        it = self._items[row]
        old_group = str(it.get("group") or "business")
        it["name"] = self._name.text().strip() or str(it.get("id") or "")
        it["desc"] = self._desc.text().strip()
        it["icon"] = self._icon.text().strip() or str(it.get("id") or "")
        raw_gid = self._group.currentData(Qt.ItemDataRole.UserRole)
        if raw_gid is None and 0 <= self._group.currentIndex() < len(GROUP_ORDER):
            raw_gid = GROUP_ORDER[self._group.currentIndex()]
        it["group"] = str(raw_gid or "business")
        it["show"] = self._show.isChecked()
        new_group = str(it.get("group") or "business")
        keep_id = str(it.get("id") or "")
        if new_group != old_group:
            glab = GROUP_LABELS.get(new_group, new_group)
            self._page.report_status(f"已改到「{glab}」分组 · 记得点保存菜单")
            self._refresh_tree(keep_id=keep_id)
            return
        current = self._tree.currentItem()
        if current is not None:
            current.setText(0, self._item_label(it))

    def _move(self, delta: int) -> None:
        row = self._current_item_index()
        if row is None:
            return
        new_row = row + delta
        if row < 0 or new_row < 0 or new_row >= len(self._items):
            return
        keep_id = str(self._items[row].get("id") or "")
        self._items[row], self._items[new_row] = self._items[new_row], self._items[row]
        for i, it in enumerate(self._items):
            it["order"] = i + 1
        self._refresh_tree(keep_id=keep_id)

    def _save(self) -> None:
        self._apply_fields()
        if not self._items:
            show_warning(self._page, "菜单为空，无法保存。")
            return
        for i, it in enumerate(self._items):
            it["order"] = i + 1
        path = save_menu_items(self._items)
        request_nav_rebuild()
        self._page.report_status("菜单已保存")
        show_info(self._page, f"已保存用户菜单：\n{path}\n侧栏将立即刷新。")

    def _reset(self) -> None:
        reset_user_menu()
        self.reload()
        request_nav_rebuild()
        self._page.report_status("已恢复默认菜单")
        show_info(self._page, "已删除用户菜单覆盖，恢复 app.yml 默认项。")
