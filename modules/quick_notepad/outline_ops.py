# -*- coding: utf-8 -*-
"""大纲树装载 / 过滤 / 选中（页面委托）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QTreeWidgetItem

from modules.quick_notepad.note_store import children_of, load_nodes
from services.icon_registry import get_icon


def node_matches_filter(node: dict, q: str, by_id: dict[str, dict]) -> bool:
    if not q:
        return True
    if q in f"{node.get('title') or ''} {node.get('body') or ''}".lower():
        return True
    for child in by_id.values():
        if str(child.get("parent_id") or "") == str(node.get("id")):
            if node_matches_filter(child, q, by_id):
                return True
    return False


def filtered_nodes(search_text: str) -> list[dict]:
    q = (search_text or "").strip().lower()
    nodes = load_nodes()
    if not q:
        return nodes
    by_id = {str(n.get("id")): n for n in nodes}
    return [n for n in nodes if node_matches_filter(n, q, by_id)]


def make_tree_item(page, node: dict, *, has_children: bool = False) -> QTreeWidgetItem:
    title = str(node.get("title") or "无标题")
    item = QTreeWidgetItem([title])
    item.setData(0, Qt.ItemDataRole.UserRole, str(node.get("id")))
    item.setToolTip(0, f"{node.get('updated', '')} · {title}\n双击改标题")
    item.setIcon(
        0,
        get_icon(
            "folder" if has_children else "file-text",
            color=page._icon_fg(),
            size=16,
            parent=page,
        ),
    )
    item.setFlags(
        (
            item.flags()
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
        )
        & ~Qt.ItemFlag.ItemIsEditable
    )
    item.setExpanded(True)
    return item


def populate_tree(
    page,
    parent_item: QTreeWidgetItem | None,
    parent_id: str | None,
    visible_ids: set[str],
) -> None:
    tree = page._tree
    for node in children_of(parent_id):
        nid = str(node.get("id"))
        if nid not in visible_ids:
            continue
        kids = [c for c in children_of(nid) if str(c.get("id")) in visible_ids]
        item = make_tree_item(page, node, has_children=bool(kids))
        if parent_item is None:
            tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        populate_tree(page, item, nid, visible_ids)


def find_tree_item(tree, node_id: str) -> QTreeWidgetItem | None:
    target = str(node_id)

    def walk(item: QTreeWidgetItem | None) -> QTreeWidgetItem | None:
        if item is None:
            for i in range(tree.topLevelItemCount()):
                found = walk(tree.topLevelItem(i))
                if found is not None:
                    return found
            return None
        if str(item.data(0, Qt.ItemDataRole.UserRole)) == target:
            return item
        for i in range(item.childCount()):
            found = walk(item.child(i))
            if found is not None:
                return found
        return None

    return walk(None)


def select_tree_id(tree, node_id: str) -> None:
    item = find_tree_item(tree, node_id)
    if item is None:
        return
    p = item.parent()
    while p is not None:
        p.setExpanded(True)
        p = p.parent()
    tree.setCurrentItem(item)
    tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)


def reload_tree(page, *, keep_selection: str | None = None) -> None:
    sel = keep_selection or page._current_id
    page._rebuilding_tree = True
    page._tree.clear()
    nodes = filtered_nodes(page._search.text())
    visible_ids = {str(n.get("id")) for n in nodes}
    by_id = {str(n.get("id")): n for n in load_nodes()}
    for nid in list(visible_ids):
        cur = by_id.get(nid)
        while cur is not None:
            pid = cur.get("parent_id")
            if not pid:
                break
            pid_s = str(pid)
            visible_ids.add(pid_s)
            cur = by_id.get(pid_s)
    populate_tree(page, None, None, visible_ids)
    page._tree.expandAll()
    page._rebuilding_tree = False
    page.report_status(f"共 {len(nodes)} 条记事")
    page._tree.setToolTip(f"大纲 · {len(nodes)} 条" if nodes else "大纲（空）")
    if sel:
        select_tree_id(page._tree, sel)
    elif page._tree.topLevelItemCount() > 0:
        page._tree.setCurrentItem(page._tree.topLevelItem(0))
