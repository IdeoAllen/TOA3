# -*- coding: utf-8 -*-
"""记事新建 / 保存 / 删除 / 改标题。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.quick_notepad.note_store import (
    add_note,
    delete_node,
    descendant_ids,
    find_note,
    insert_note_after,
    save_settings,
    update_note,
)
from modules.quick_notepad.outline_ops import find_tree_item
from widgets.list_edit import FormEditDialog, confirm_delete


def seed_new_editor(page) -> None:
    page._loading_body = True
    try:
        page._md_source.clear()
        page._md_preview.clear()
        page._view_mode = "edit"
        save_settings({"view_mode": "edit"})
        page._apply_view_mode("edit")
        if page._current_id:
            title = page._title_label.text().strip() or "新记事"
            update_note(page._current_id, title, "", clear_html_source=True)
    finally:
        page._loading_body = False
    page._sync_view_chrome()
    page._set_save_badge("saved")
    page._update_word_count()


def on_new_note(page) -> None:
    page._flush_autosave()
    entry = add_note("新记事", "", parent_id=page._sibling_parent_id())
    page._current_id = entry["id"]
    page._reload_tree(keep_selection=page._current_id)
    page._title_label.setText(entry["title"])
    seed_new_editor(page)
    page.schedule_primary_focus()
    page.report_status("已新建 · 编辑面写 Markdown，或拖右侧组件", level=StatusLevel.SUCCESS)


def on_new_below(page) -> None:
    page._flush_autosave()
    entry = insert_note_after(page._current_id, title="新记事", body="")
    page._current_id = entry["id"]
    page._reload_tree(keep_selection=page._current_id)
    page._title_label.setText(entry["title"])
    seed_new_editor(page)
    page._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
    page.report_status("已在下方新建", level=StatusLevel.SUCCESS)


def on_edit_title(page) -> None:
    item = page._tree.currentItem()
    if item is None:
        show_warning(page, "请先选择记事。")
        return
    nid = str(item.data(0, Qt.ItemDataRole.UserRole))
    node = find_note(nid)
    if not node:
        return
    dlg = FormEditDialog(page, title="修改标题", fields=[("标题", "title")])
    dlg.set_values({"title": node.get("title") or ""})
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    title = (dlg.values().get("title") or "").strip() or "无标题"
    update_note(nid, title, str(node.get("body") or ""))
    page._title_label.setText(title)
    page._reload_tree(keep_selection=nid)
    page.schedule_primary_focus()


def update_tree_item_label(page, node_id: str) -> None:
    node = find_note(node_id)
    if node is None:
        return
    item = find_tree_item(page._tree, node_id)
    if item is not None:
        title = str(node.get("title") or "无标题")
        item.setText(0, title)
        item.setToolTip(0, f"{node.get('updated', '')} · {title}")


def on_save_body(page, silent: bool = False) -> None:
    body = page._capture_body()
    edit = page._active_editor()
    cursor_pos = edit.textCursor().position()
    plain_len = len(edit.toPlainText())
    if not page._current_id:
        if silent and not (body or "").strip():
            return
        title = page._title_label.text().strip()
        if not title or title == "未选择":
            title = "新记事"
        entry = add_note(title, body, parent_id=page._sibling_parent_id())
        page._current_id = entry["id"]
        page._title_label.setText(entry["title"])
        update_note(page._current_id, entry["title"], body, editor_mode="md")
        page._reload_tree(keep_selection=page._current_id)
    else:
        n = find_note(page._current_id)
        if not n:
            if not silent:
                show_warning(page, "当前记事不存在，请重新选择。")
            return
        title = str(n.get("title") or page._title_label.text() or "无标题")
        update_note(page._current_id, title, body, editor_mode="md")
        page._title_label.setText(title)
        update_tree_item_label(page, page._current_id)
    if not silent:
        cur = edit.textCursor()
        cur.setPosition(min(cursor_pos, plain_len))
        edit.setTextCursor(cur)
        page.schedule_primary_focus(move_cursor_end=False)
        page.report_status("已保存 · 可继续编辑", level=StatusLevel.SUCCESS)
    page._set_save_badge("saved")


def on_delete(page) -> None:
    item = page._tree.currentItem()
    if item is None:
        return
    page._flush_autosave()
    nid = str(item.data(0, Qt.ItemDataRole.UserRole))
    n = find_note(nid) or {}
    kids = descendant_ids(nid)
    label = f"「{n.get('title') or nid}」"
    if kids:
        label += f"（将同时删除其下 {len(kids)} 条子记事，不可恢复）"
    if not confirm_delete(page, label):
        return
    deleted = {nid, *kids}
    delete_node(nid)
    if page._current_id in deleted:
        page._current_id = None
        page._loading_body = True
        try:
            page._md_source.clear()
            page._md_preview.clear()
        finally:
            page._loading_body = False
        page._title_label.setText("未选择")
        page._set_save_badge("empty")
    page._reload_tree()
