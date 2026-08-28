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
from core.user_messages import ask_confirm, show_info, show_warning
from services.config_service import (
    get_all_menu_items,
    get_group_labels,
    load_config,
    reset_user_menu,
    save_menu_items,
    user_menu_path,
)
from services.menu_registry import GROUP_ORDER, MIGRATED_MODULES, group_label
from services.migration_manifest import status_label
from services.access_control import is_admin_session
from services.notify_bus import request_nav_rebuild
from services.toa_catalog_client import publish_menu_catalog_to_cloud
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
            self._group.addItem(group_label(gid), gid)
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
        self._group_labels: dict[str, str] = {}
        self._last_module_id: str | None = None
        self._last_group_id: str | None = None
        self._suppress = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        box = FormSection("菜单配置")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        box.add_widget(
            HintLabel(
                "在此调整侧栏显示、分组与排序，点「保存菜单」立即生效。\n"
                "「同步目录到运营台」仅上传 module 池供运营台组包；侧栏 IA 不在运营台修改。\n"
                "点选左侧子模块行可改顶栏名；点选具体功能可改功能名。"
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
        self._group_title = LineEdit()
        self._group_title.setPlaceholderText("顶栏子模块名称，如 办公、编码智能体")
        self._name = LineEdit()
        self._id = LineEdit()
        self._id.setReadOnly(True)
        self._desc = LineEdit()
        self._icon = LineEdit()
        self._group = ComboBox()
        for gid in GROUP_ORDER:
            self._group.addItem(group_label(gid), gid)
        self._show = CheckBox("在菜单中显示")
        self._show.setChecked(True)
        self._show_hidden = CheckBox("显示已隐藏项")
        self._show_hidden.setChecked(False)

        form = QFormLayout()
        form.addRow("子模块名", self._group_title)
        form.addRow("功能名", self._name)
        form.addRow("模块 ID", self._id)
        form.addRow("说明", self._desc)
        form.addRow("图标", self._icon)
        form.addRow("分组", self._group)
        form.addRow("", self._show)
        edit.add_layout(form)

        for w in (self._name, self._desc, self._icon, self._group_title):
            w.textChanged.connect(self._apply_fields)
        self._group.currentIndexChanged.connect(self._apply_fields)
        self._show.toggled.connect(self._apply_fields)

        mid.addWidget(edit, 1)
        box.add_widget(mid_host, 1)

        self._show_hidden.toggled.connect(lambda _=False: self._refresh_tree())
        box.add_widget(self._show_hidden)

        row = QHBoxLayout()
        btn_add = PrimaryButton("新增")
        btn_add.clicked.connect(self._add_item)
        row.addWidget(btn_add)
        btn_del = SecondaryButton("从菜单移除")
        btn_del.clicked.connect(self._remove_item)
        row.addWidget(btn_del)
        btn_up = SecondaryButton("上移")
        btn_up.setAutoDefault(False)
        btn_up.setDefault(False)
        btn_up.clicked.connect(lambda: self._move(-1))
        row.addWidget(btn_up)
        btn_down = SecondaryButton("下移")
        btn_down.setAutoDefault(False)
        btn_down.setDefault(False)
        btn_down.clicked.connect(lambda: self._move(1))
        row.addWidget(btn_down)
        btn_save = PrimaryButton("保存菜单")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        self._btn_sync_cloud = SecondaryButton("同步目录到运营台")
        self._btn_sync_cloud.setAutoDefault(False)
        self._btn_sync_cloud.setDefault(False)
        self._btn_sync_cloud.clicked.connect(self._sync_catalog_to_cloud)
        row.addWidget(self._btn_sync_cloud)
        btn_reload = SecondaryButton("重新加载")
        btn_reload.setAutoDefault(False)
        btn_reload.setDefault(False)
        btn_reload.clicked.connect(self._reload_from_disk)
        row.addWidget(btn_reload)
        btn_reset = SecondaryButton("恢复默认")
        btn_reset.setAutoDefault(False)
        btn_reset.setDefault(False)
        btn_reset.clicked.connect(self._reset)
        row.addWidget(btn_reset)
        row.addStretch(1)
        box.add_layout(row)

        lay.addWidget(box, 1)
        self._btn_sync_cloud.setVisible(is_admin_session())
        self.reload(quiet=True)

    def _sync_catalog_to_cloud(self) -> None:
        if not is_admin_session():
            show_warning(self._page, "仅终端管理员（admin 授权）可同步菜单目录。")
            return
        self._flush_edits()
        if not ask_confirm(
            self._page,
            "将当前菜单 module 目录上传至 TOA 云服务？\n"
            "运营台将据此组功能包；建议先点「保存菜单」。",
        ):
            return
        ok, msg = publish_menu_catalog_to_cloud()
        if ok:
            show_info(self._page, msg)
            self._page.report_status(msg)
        else:
            show_warning(self._page, msg)
            self._page.report_status(msg)

    def _sync_form_from_selection(self) -> None:
        """强制右侧表单与内存菜单同步（重选同一行时 Qt 不触发 currentItemChanged）。"""
        self._on_select(self._tree.currentItem(), None)

    def reload(self, *, quiet: bool = False) -> None:
        keep_id = self._current_item_id() or self._last_module_id
        keep_group = self._current_group_id() or self._last_group_id
        self._items = deepcopy(get_all_menu_items())
        self._group_labels = dict(get_group_labels())
        self._rebuild_group_combo()
        self._refresh_tree(keep_id=keep_id, keep_group=keep_group)
        self._sync_form_from_selection()
        if not quiet:
            self._page.report_status("已重新加载菜单（未保存的编辑已丢弃）")
            show_info(self._page, "已从磁盘重新加载菜单，未保存的编辑已丢弃。")

    def _reload_from_disk(self) -> None:
        self.reload()

    def _rebuild_group_combo(self) -> None:
        self._group.blockSignals(True)
        cur_gid = self._group.currentData(Qt.ItemDataRole.UserRole)
        self._group.clear()
        for gid in GROUP_ORDER:
            label = self._group_labels.get(gid) or group_label(gid)
            self._group.addItem(label, gid)
        if cur_gid:
            idx = self._group.findData(cur_gid, Qt.ItemDataRole.UserRole)
            if idx >= 0:
                self._group.setCurrentIndex(idx)
        self._group.blockSignals(False)

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

    def _resolve_item_index(self) -> int | None:
        """按模块 id 定位行，避免点按钮时树失去选中。"""
        mid = self._current_item_id() or self._last_module_id
        if not mid:
            return None
        for i, it in enumerate(self._items):
            if str(it.get("id") or "") == mid:
                return i
        return None

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

    def _current_group_id(self) -> str | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, str) and data.startswith("group:"):
            return data.split(":", 1)[1]
        return None

    def _make_group_node(self, label: str, count: int, gid: str) -> QTreeWidgetItem:
        node = QTreeWidgetItem([f"▾ {label}  ({count})"])
        node.setData(0, Qt.ItemDataRole.UserRole, f"group:{gid}")
        node.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
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

    def _refresh_tree(self, *, keep_id: str | None = None, keep_group: str | None = None) -> None:
        keep_id = keep_id or self._current_item_id()
        keep_group = keep_group or self._current_group_id()
        self._tree.clear()

        buckets: dict[str, list[tuple[int, dict]]] = {g: [] for g in GROUP_ORDER}
        other: list[tuple[int, dict]] = []
        for idx, it in enumerate(self._items):
            if not it.get("show", True) and not self._show_hidden.isChecked():
                continue
            gid = str(it.get("group") or "business").lower()
            if gid in buckets:
                buckets[gid].append((idx, it))
            else:
                other.append((idx, it))

        for gid in GROUP_ORDER:
            entries = buckets[gid]
            if not entries:
                continue
            entries.sort(key=lambda pair: int(pair[1].get("order") or 0))
            glab = self._group_labels.get(gid) or group_label(gid)
            root = self._make_group_node(glab, len(entries), gid)
            self._tree.addTopLevelItem(root)
            for idx, it in entries:
                root.addChild(self._make_leaf(idx, it))
            root.setExpanded(True)

        if other:
            other.sort(key=lambda pair: int(pair[1].get("order") or 0))
            root = self._make_group_node("其它", len(other), "other")
            self._tree.addTopLevelItem(root)
            for idx, it in other:
                root.addChild(self._make_leaf(idx, it))
            root.setExpanded(True)

        if keep_id:
            self._select_by_id(keep_id)
        elif keep_group:
            self._select_group(keep_group)
        elif self._items:
            first = self._tree.topLevelItem(0)
            if first is not None and first.childCount() > 0:
                self._tree.setCurrentItem(first.child(0))

    def _select_group(self, group_id: str) -> None:
        token = f"group:{group_id}"
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is not None and item.data(0, Qt.ItemDataRole.UserRole) == token:
                self._tree.setCurrentItem(item)
                item.setExpanded(True)
                return

    def _on_select(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        gid = self._current_group_id()
        if gid:
            self._last_module_id = None
            self._last_group_id = gid if gid != "other" else None
            self._suppress = True
            self._group_title.setText(self._group_labels.get(gid) or group_label(gid))
            self._name.clear()
            self._id.setText(f"子模块 · {gid}")
            self._desc.clear()
            self._icon.clear()
            self._group.setCurrentIndex(0)
            self._show.setChecked(False)
            self._group_title.setEnabled(True)
            self._name.setEnabled(False)
            self._desc.setEnabled(False)
            self._icon.setEnabled(False)
            self._group.setEnabled(False)
            self._show.setEnabled(False)
            self._suppress = False
            self._page.report_status(f"编辑子模块名：{gid}")
            return
        idx = self._current_item_index()
        if idx is None:
            self._suppress = True
            self._group_title.clear()
            self._name.clear()
            self._id.clear()
            self._desc.clear()
            self._icon.clear()
            self._group.setCurrentIndex(0)
            self._show.setChecked(False)
            self._group_title.setEnabled(False)
            self._name.setEnabled(False)
            self._desc.setEnabled(False)
            self._icon.setEnabled(False)
            self._group.setEnabled(False)
            self._show.setEnabled(False)
            self._suppress = False
            return
        self._suppress = True
        it = self._items[idx]
        mid = str(it.get("id") or "")
        self._last_module_id = mid
        self._last_group_id = None
        item_gid = str(it.get("group") or "business")
        self._group_title.setText(self._group_labels.get(item_gid) or group_label(item_gid))
        self._group_title.setEnabled(False)
        self._name.setEnabled(True)
        self._desc.setEnabled(True)
        self._icon.setEnabled(True)
        self._name.setText(str(it.get("name") or ""))
        self._id.setText(mid)
        self._desc.setText(str(it.get("desc") or ""))
        self._icon.setText(str(it.get("icon") or ""))
        gid = str(it.get("group") or "business")
        gidx = self._group.findData(gid, Qt.ItemDataRole.UserRole)
        if gidx < 0:
            gidx = self._group.findText(group_label(gid))
        self._group.setCurrentIndex(gidx if gidx >= 0 else 0)
        self._show.setChecked(bool(it.get("show", True)))
        locked = mid in ("home", "system_settings", "theme_preview")
        self._group.setEnabled(not locked)
        self._show.setEnabled(mid != "home")
        self._suppress = False

    def _flush_edits(self) -> None:
        """把右侧表单写入内存（不依赖树仍保持选中）。"""
        if self._last_group_id and self._group_title.isEnabled():
            title = self._group_title.text().strip()
            if title:
                self._group_labels[self._last_group_id] = title
            return
        row = self._resolve_item_index()
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
        if str(it.get("group") or "business") != old_group:
            self._refresh_tree(keep_id=str(it.get("id") or ""))

    def _apply_fields(self, *_args) -> None:
        if self._suppress:
            return
        gid = self._current_group_id()
        if gid:
            title = self._group_title.text().strip()
            if title and gid != "other":
                self._group_labels[gid] = title
                self._last_group_id = gid
            current = self._tree.currentItem()
            if current is not None:
                count = current.childCount()
                current.setText(0, f"▾ {title or group_label(gid)}  ({count})")
            self._page.report_status("已改子模块名 · 记得点保存菜单")
            return
        row = self._resolve_item_index()
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
            glab = group_label(new_group)
            self._page.report_status(f"已改到「{glab}」分组 · 记得点保存菜单")
            self._refresh_tree(keep_id=keep_id)
            return
        current = self._tree.currentItem()
        if current is not None:
            current.setText(0, self._item_label(it))

    def _normalize_orders(self) -> None:
        """按顶栏分组顺序 + 组内顺序写入 order（与侧栏一致）。"""
        order = 1
        for gid in GROUP_ORDER:
            group_items = [
                it
                for it in self._items
                if str(it.get("group") or "business").lower() == gid
            ]
            group_items.sort(key=lambda x: int(x.get("order") or 0))
            for it in group_items:
                it["order"] = order
                order += 1
        other = [
            it
            for it in self._items
            if str(it.get("group") or "business").lower() not in GROUP_ORDER
        ]
        other.sort(key=lambda x: int(x.get("order") or 0))
        for it in other:
            it["order"] = order
            order += 1

    def _visible_group_member_indices(self, gid: str) -> list[int]:
        """与树列表一致：未勾选「显示已隐藏项」时不含隐藏模块。"""
        pairs = [
            (i, it)
            for i, it in enumerate(self._items)
            if str(it.get("group") or "business").lower() == gid
            and (it.get("show", True) or self._show_hidden.isChecked())
        ]
        pairs.sort(key=lambda p: int(p[1].get("order") or 0))
        return [i for i, _ in pairs]

    def _group_member_indices(self, gid: str) -> list[int]:
        pairs = [
            (i, it)
            for i, it in enumerate(self._items)
            if str(it.get("group") or "business").lower() == gid
        ]
        pairs.sort(key=lambda p: int(p[1].get("order") or 0))
        return [i for i, _ in pairs]

    def _move(self, delta: int) -> None:
        if self._current_group_id():
            show_warning(self._page, "上移/下移请点选具体功能模块，不是子模块行。")
            return
        row = self._resolve_item_index()
        if row is None:
            show_warning(self._page, "请先点选一个功能模块。")
            return
        gid = str(self._items[row].get("group") or "business").lower()
        if self._show_hidden.isChecked():
            indices = self._group_member_indices(gid)
        else:
            indices = self._visible_group_member_indices(gid)
        if row not in indices:
            show_warning(self._page, "当前项不在可排序列表中，可勾选「显示已隐藏项」后再试。")
            return
        pos = indices.index(row)
        new_pos = pos + delta
        if new_pos < 0:
            self._page.report_status("已在本组顶部")
            return
        if new_pos >= len(indices):
            self._page.report_status("已在本组底部")
            return
        other_row = indices[new_pos]
        keep_id = str(self._items[row].get("id") or "")
        self._last_module_id = keep_id
        # 须改 order 字段；仅交换 _items 下标无效，刷新树仍按 order 排序
        indices[pos], indices[new_pos] = indices[new_pos], indices[pos]
        orders_sorted = sorted(int(self._items[i].get("order") or 0) for i in indices)
        for rank, idx in enumerate(indices):
            self._items[idx]["order"] = orders_sorted[rank]
        self._normalize_orders()
        self._refresh_tree(keep_id=keep_id)
        self._page.report_status("已调整组内顺序 · 记得点保存菜单")

    def _remove_item(self) -> None:
        row = self._resolve_item_index()
        if row is None:
            show_warning(self._page, "请先点选要从侧栏移除的功能模块。")
            return
        it = self._items[row]
        mid = str(it.get("id") or "")
        if mid == "home":
            show_warning(self._page, "「首页」不可移除。")
            return
        if mid in ("theme_preview", "system_settings"):
            show_warning(self._page, "系统入口请用「在菜单中显示」关闭，勿删除。")
            return
        base_ids = {str(i.get("id") or "") for i in _default_menu_templates()}
        if mid in base_ids:
            it["show"] = False
            self._refresh_tree(keep_id=mid)
            self._page.report_status(f"已隐藏 {mid} · 记得点保存菜单")
            return
        name = str(it.get("name") or mid)
        self._items.pop(row)
        self._last_module_id = None
        self._normalize_orders()
        self._refresh_tree()
        self._page.report_status(f"已移除自定义项 {name} · 记得点保存菜单")

    def _save(self) -> None:
        self._flush_edits()
        if not self._items:
            show_warning(self._page, "菜单为空，无法保存。")
            return
        self._normalize_orders()
        save_menu_items(self._items, group_labels=self._group_labels)
        request_nav_rebuild()
        self._page.report_status("菜单已保存")
        show_info(self._page, "菜单已保存，侧栏已刷新。")

    def _reset(self) -> None:
        if not ask_confirm(
            self._page,
            "将删除本机菜单配置文件并恢复出厂菜单与顶栏名称。\n"
            "当前页未保存的编辑也会丢失，确定继续？",
            title="恢复默认菜单",
        ):
            return
        had_file = user_menu_path().is_file()
        reset_user_menu()
        self._last_module_id = None
        self._last_group_id = None
        self.reload(quiet=True)
        request_nav_rebuild()
        if had_file:
            self._page.report_status("已恢复默认菜单")
            show_info(self._page, "已恢复出厂菜单，侧栏已刷新。")
        else:
            self._page.report_status("当前已是出厂菜单")
            show_info(self._page, "本机没有菜单覆盖文件，当前已是出厂菜单。")
