# -*- coding: utf-8 -*-
"""快速记事：一源 Markdown · 编辑 / 预览。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QImage, QKeyEvent, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.app_state import AppState
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_warning
from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
from modules.clipboard_history.history_store import push_text
from modules.quick_notepad.component_blocks import BLOCKS, MIME_BLOCK, block_id_from_mime
from modules.quick_notepad.component_palette import ComponentPalette
from modules.quick_notepad.markdown_highlighter import MarkdownHighlighter
from modules.quick_notepad.md_actions import on_palette_insert, toolbar_action
from modules.quick_notepad.md_text import sanitize_md_source
from modules.quick_notepad.note_crud import (
    on_delete,
    on_edit_title,
    on_new_below,
    on_new_note,
    on_save_body,
    seed_new_editor,
)
from modules.quick_notepad.notepad_files import (
    body_html_for_export,
    export_pdf,
    import_paths_into_page,
    paths_from_mime,
)
from modules.quick_notepad.note_store import (
    add_note,
    find_note,
    indent_node,
    load_settings,
    move_node,
    normalize_view_mode,
    outdent_node,
    resolve_note_body_for_ui,
    sanitize_tree,
    save_settings,
)
from modules.quick_notepad.outline_ops import reload_tree as reload_outline_tree, select_tree_id
from modules.quick_notepad.outline_tree import OutlineKeyFilter, OutlineTree
from modules.quick_notepad.rich_body import refresh_editor_preview
from services.icon_registry import get_icon
from widgets import (
    DangerButton,
    HintLabel,
    LineEdit,
    MenuButton,
    PlainTextEdit,
    PrimaryButton,
    SecondaryButton,
    SectionTitle,
    SemanticLabel,
    TextEdit,
)
from widgets.metrics import BUTTON_MIN_HEIGHT

_VIEW_MODES = ("edit", "preview")
_VIEW_TAB_LABELS = ("编辑", "预览")


class QuickNotepadPage(BasePage):
    page_id = "quick_notepad"
    page_title = "快速记事"

    _incoming: tuple[str, str, str | None] | None = None
    _pending_reveal_id: str | None = None

    @classmethod
    def stash_incoming(
        cls,
        body: str = "",
        *,
        title: str = "来自剪贴板",
        image_path: str | None = None,
    ) -> None:
        cls._incoming = (title, body or "", image_path)

    @classmethod
    def stash_reveal(cls, note_id: str) -> None:
        nid = str(note_id or "").strip()
        cls._pending_reveal_id = nid or None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_id: str | None = None
        self._shortcuts: list[QShortcut] = []
        self._rebuilding_tree = False
        self._loading_body = False
        self._view_mode = "edit"
        self._editor_fmt = "md"
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(800)
        self._autosave_timer.timeout.connect(self._on_autosave)

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], max(4, m[1] // 2), m[2], max(4, m[3] // 2))
        outer.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        tree_box = QWidget()
        tree_box.setObjectName("NotepadOutlinePanel")
        tree_box.setMinimumWidth(280)
        tree_box.setMaximumWidth(400)
        self._tree_box = tree_box
        tree_lay = QVBoxLayout(tree_box)
        tree_lay.setContentsMargins(0, 0, 0, 0)
        tree_lay.setSpacing(4)

        self._search = LineEdit()
        self._search.setObjectName("NotepadOutlineSearch")
        self._search.setPlaceholderText("搜索记事…")
        self._search.setClearButtonEnabled(True)
        self._search.setToolTip("按标题检索左侧记事本")
        self._search.textChanged.connect(lambda _t: reload_outline_tree(self))
        tree_lay.addWidget(self._search)

        self._tree_panel = QWidget()
        self._tree_panel.setObjectName("OutlineTreePanel")
        tree_panel_lay = QVBoxLayout(self._tree_panel)
        tree_panel_lay.setContentsMargins(2, 2, 2, 2)
        tree_panel_lay.setSpacing(2)
        self._tree = OutlineTree()
        self._tree.setMinimumHeight(160)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.currentItemChanged.connect(self._on_tree_select)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self._tree.drop_resolved.connect(self._on_drop_resolved)
        self._tree.files_dropped.connect(self._on_files_dropped)
        self._tree.indent_requested.connect(self._on_indent)
        self._tree.outdent_requested.connect(self._on_outdent)
        self._tree.create_below_requested.connect(self._on_new_below)
        self._key_filter = OutlineKeyFilter(self._tree, self)
        self._tree.installEventFilter(self._key_filter)
        tree_panel_lay.addWidget(self._tree, 1)
        tree_lay.addWidget(self._tree_panel, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        btn_new = PrimaryButton("新建")
        btn_new.setToolTip("Ctrl+N / Enter")
        btn_new.setMinimumWidth(78)
        btn_new.clicked.connect(self._on_new_note)
        row1.addWidget(btn_new)
        btn_del = DangerButton("删除")
        btn_del.setMinimumWidth(78)
        btn_del.clicked.connect(self._on_delete)
        row1.addWidget(btn_del)
        row1.addStretch(1)
        row1.addWidget(self._outline_tool_btn("right", "缩进 · Tab", self._on_indent))
        row1.addWidget(self._outline_tool_btn("left", "升级 · Shift+Tab", self._on_outdent))
        tree_lay.addLayout(row1)
        splitter.addWidget(tree_box)

        editor = QWidget()
        editor.setObjectName("NotepadEditorPanel")
        editor_lay = QVBoxLayout(editor)
        editor_lay.setContentsMargins(0, 0, 0, 0)
        editor_lay.setSpacing(4)

        self._editor_chrome = QWidget()
        chrome = QHBoxLayout(self._editor_chrome)
        chrome.setContentsMargins(4, 2, 4, 2)
        chrome.setSpacing(6)

        self._title_label = SectionTitle("未选择")
        self._title_label.setToolTip("F2 或双击大纲改标题")
        self._title_label.setMinimumWidth(72)
        chrome.addWidget(self._title_label, 1)

        self._view_tabs_host = QFrame()
        self._view_tabs_host.setObjectName("EditorViewTabs")
        tabs_lay = QHBoxLayout(self._view_tabs_host)
        tabs_lay.setContentsMargins(2, 2, 2, 2)
        tabs_lay.setSpacing(0)
        self._view_tab_bar = QTabBar()
        self._view_tab_bar.setObjectName("EditorViewTabBar")
        self._view_tab_bar.setDrawBase(False)
        self._view_tab_bar.setExpanding(False)
        self._view_tab_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label in _VIEW_TAB_LABELS:
            self._view_tab_bar.addTab(label)
        self._view_tab_bar.currentChanged.connect(self._on_view_tab_changed)
        tabs_lay.addWidget(self._view_tab_bar)
        chrome.addWidget(self._view_tabs_host)

        self._save_hint = SemanticLabel("", kind="success", compact=True)
        self._save_hint.setVisible(False)
        chrome.addWidget(self._save_hint)

        more = MenuButton("更多")
        more_menu = QMenu(more)
        self._act_import = more_menu.addAction("导入文件")
        self._act_import.triggered.connect(self._on_import_md)
        more_menu.addAction("导出 PDF").triggered.connect(self._on_export_pdf)
        more_menu.addAction("复制正文").triggered.connect(self._to_clipboard)
        more.setMenu(more_menu)
        chrome.addWidget(more)
        editor_lay.addWidget(self._editor_chrome)

        self._fmt_toolbar_host = QWidget()
        self._fmt_toolbar_host.setObjectName("NotepadFmtToolbar")
        self._fmt_toolbar = QHBoxLayout(self._fmt_toolbar_host)
        self._fmt_toolbar.setContentsMargins(4, 2, 4, 2)
        self._fmt_toolbar.setSpacing(2)
        self._fmt_btns: list = []
        for spec in BLOCKS:
            if not (spec.toolbar or "").strip():
                continue  # 图表等仅组件库
            btn = SecondaryButton(spec.toolbar)
            btn.setToolTip(spec.hint or spec.title)
            btn.clicked.connect(lambda _c=False, b=spec.id: self._toolbar_action(b))
            self._fmt_toolbar.addWidget(btn)
            self._fmt_btns.append(btn)
        self._fmt_toolbar.addStretch(1)
        editor_lay.addWidget(self._fmt_toolbar_host)

        self._editor_surface = QWidget()
        surface_lay = QVBoxLayout(self._editor_surface)
        surface_lay.setContentsMargins(0, 0, 0, 0)

        self._compose_split = QSplitter(Qt.Orientation.Horizontal)
        self._compose_split.setChildrenCollapsible(False)
        self._compose_split.setHandleWidth(6)

        write_pane = QWidget()
        write_lay = QVBoxLayout(write_pane)
        write_lay.setContentsMargins(4, 4, 4, 4)
        write_lay.setSpacing(0)
        self._view_stack = QStackedWidget()
        self._view_stack.setMinimumHeight(200)
        self._view_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._md_source = PlainTextEdit()
        self._md_source.setObjectName("MarkdownSourceEdit")
        self._md_source.setPlaceholderText("编辑 · Markdown 源码…")
        self._view_stack.addWidget(self._md_source)

        self._preview_host = QStackedWidget()
        self._md_preview = TextEdit()
        self._md_preview.setObjectName("MarkdownPreviewEdit")
        self._md_preview.setReadOnly(True)
        self._preview_host.addWidget(self._md_preview)
        self._md_preview_web = None
        self._view_stack.addWidget(self._preview_host)

        self._md_highlighter = MarkdownHighlighter(
            self._md_source.document(), AppState.get().palette or {}
        )
        # 兼容旧引用
        self._plain = self._md_source
        write_lay.addWidget(self._view_stack, 1)
        self._compose_split.addWidget(write_pane)

        self._component_palette = ComponentPalette(self)
        self._component_palette.insert_requested.connect(self._on_palette_insert)
        self._compose_split.addWidget(self._component_palette)
        self._compose_split.setStretchFactor(0, 1)
        self._compose_split.setStretchFactor(1, 0)
        self._compose_split.setSizes([720, 220])
        surface_lay.addWidget(self._compose_split, 1)
        editor_lay.addWidget(self._editor_surface, 1)
        self._body = self._md_source

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)
        self._word_count = HintLabel("")
        footer.addWidget(self._word_count, 1)
        editor_lay.addLayout(footer)

        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 720])
        outer.addWidget(splitter, 1)

        self.setAcceptDrops(True)
        self._write_pane = write_pane
        for w in (
            self._md_source,
            self._md_preview,
            self._editor_surface,
            write_pane,
            self._view_stack,
        ):
            w.setAcceptDrops(True)
            w.installEventFilter(self)
        vp = self._md_source.viewport()
        if vp is not None:
            vp.setAcceptDrops(True)
            vp.installEventFilter(self)

        self._md_source.textChanged.connect(self._on_md_source_changed)
        sanitize_tree()
        reload_outline_tree(self)
        self.apply_page_focus_policy()
        self._load_mode_from_settings()

    def _fmt(self) -> str:
        return "md"

    def _set_save_badge(self, state: str) -> None:
        label = self._save_hint
        if state == "empty":
            label.setVisible(False)
            label.setText("")
            return
        label.setVisible(True)
        label.setText("编辑中…" if state == "editing" else "已保存")
        label.setProperty(
            "class", "semantic-warning" if state == "editing" else "semantic-success"
        )
        label.setProperty("compact", "true")
        st = label.style()
        if st is not None:
            st.unpolish(label)
            st.polish(label)

    def _icon_fg(self) -> str:
        pal = AppState.get().palette or {}
        return str(pal.get("text_primary") or pal.get("text") or "#1F2937")

    def _outline_tool_btn(self, icon_name: str, tip: str, slot) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("FinderToolBtn")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setFixedSize(BUTTON_MIN_HEIGHT + 4, BUTTON_MIN_HEIGHT)
        btn.setIcon(get_icon(icon_name, color=self._icon_fg(), size=16, parent=self))
        btn.setIconSize(QSize(16, 16))
        btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(slot)
        return btn

    def primary_focus_widget(self):
        try:
            return self._active_editor()
        except Exception:
            return getattr(self, "_md_source", None)

    def _active_editor(self):
        mode = normalize_view_mode(getattr(self, "_view_mode", None))
        if mode == "preview":
            return self._md_preview
        return self._md_source

    def _capture_body(self) -> str:
        return sanitize_md_source(self._md_source.toPlainText())

    def _ensure_writable(self) -> None:
        if normalize_view_mode(self._view_mode) == "preview":
            self._set_view_mode("edit")

    def _ensure_md_writable(self) -> None:
        self._ensure_writable()

    def _after_md_mutation(self, *, scroll_end: bool = False) -> None:
        if scroll_end:
            edit = self._active_editor()
            if edit is self._md_preview:
                edit = self._md_source
            cur = edit.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            edit.setTextCursor(cur)
            edit.ensureCursorVisible()
        if normalize_view_mode(self._view_mode) == "preview":
            self._refresh_current_preview()
        self._flush_autosave()
        self.schedule_primary_focus(move_cursor_end=scroll_end)

    def _toolbar_action(self, block_id: str) -> None:
        toolbar_action(self, block_id)

    def _on_palette_insert(self, block_id: str) -> None:
        on_palette_insert(self, block_id)

    def _ensure_preview_web(self):
        if self._md_preview_web is not None:
            return self._md_preview_web
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception:
            return None
        web = QWebEngineView(self._preview_host)
        web.setObjectName("MarkdownPreviewWeb")
        self._preview_host.addWidget(web)
        self._md_preview_web = web
        return web

    def _refresh_current_preview(self) -> None:
        from modules.quick_notepad.mermaid_preview import (
            build_mermaid_preview_html,
            has_mermaid,
            mermaid_js_path,
        )

        md = self._md_source.toPlainText()
        if has_mermaid(md) and mermaid_js_path().is_file():
            web = self._ensure_preview_web()
            if web is not None:
                from PySide6.QtCore import QUrl

                html = build_mermaid_preview_html(md)
                base = QUrl.fromLocalFile(str(mermaid_js_path().parent.resolve()) + "/")
                web.setHtml(html, base)
                self._preview_host.setCurrentWidget(web)
                return
        refresh_editor_preview(source=self._md_source, preview=self._md_preview)
        self._preview_host.setCurrentWidget(self._md_preview)

    def _load_mode_from_settings(self) -> None:
        st = load_settings()
        self._view_mode = normalize_view_mode(st.get("view_mode"))
        font = QFont("Microsoft YaHei UI")
        font.setPointSize(11)
        for w in (self._md_source, self._md_preview):
            w.setFont(font)
        self._apply_view_mode(self._view_mode)

    def _view_mode_index(self, mode: str) -> int:
        try:
            return _VIEW_MODES.index(normalize_view_mode(mode))
        except ValueError:
            return 0

    def _on_view_tab_changed(self, index: int) -> None:
        if 0 <= index < len(_VIEW_MODES):
            self._set_view_mode(_VIEW_MODES[index])

    def _set_view_mode(self, mode: str) -> None:
        mode = normalize_view_mode(mode)
        if mode != self._view_mode:
            self._view_mode = mode
            save_settings({"view_mode": mode})
        self._apply_view_mode(mode)
        self.schedule_primary_focus()

    def _apply_view_mode(self, mode: str) -> None:
        mode = normalize_view_mode(mode)
        self._view_mode = mode
        self._view_tab_bar.blockSignals(True)
        self._view_tab_bar.setCurrentIndex(self._view_mode_index(mode))
        self._view_tab_bar.blockSignals(False)
        if mode == "preview":
            self._refresh_current_preview()
            self._view_stack.setCurrentWidget(self._preview_host)
            self._body = self._preview_host.currentWidget() or self._md_preview
        else:
            self._view_stack.setCurrentWidget(self._md_source)
            self._body = self._md_source
        self._sync_view_chrome()

    def _on_md_source_changed(self) -> None:
        if self._loading_body:
            return
        self._on_body_changed()
        if normalize_view_mode(self._view_mode) == "preview":
            self._refresh_current_preview()

    def _load_note_body(self, body: str) -> None:
        self._loading_body = True
        try:
            raw = sanitize_md_source(body or "")
            self._md_source.blockSignals(True)
            try:
                self._md_source.setPlainText(raw)
            finally:
                self._md_source.blockSignals(False)
            self._apply_view_mode(self._view_mode)
        finally:
            self._loading_body = False

    def _open_note_record(self, n: dict) -> None:
        self._editor_fmt = "md"
        body = resolve_note_body_for_ui(n)
        self._load_note_body(body)

    def _sync_view_chrome(self) -> None:
        mode = normalize_view_mode(self._view_mode)
        self._view_tabs_host.setVisible(True)
        writable = mode == "edit"
        self._fmt_toolbar_host.setVisible(writable)
        for btn in self._fmt_btns:
            btn.setVisible(writable)
        if hasattr(self, "_component_palette"):
            self._component_palette.setVisible(writable)
            if writable:
                self._component_palette.set_surface("md")
                sizes = self._compose_split.sizes()
                if len(sizes) >= 2 and sizes[1] < 60:
                    self._compose_split.setSizes([720, 220])
            else:
                sizes = self._compose_split.sizes()
                if len(sizes) >= 2 and sizes[1] > 0:
                    self._compose_split.setSizes([sizes[0] + sizes[1], 0])

    def _active_plain_text(self) -> str:
        return self._md_source.toPlainText()

    def _on_body_changed(self) -> None:
        self._update_word_count()
        if self._loading_body or self._rebuilding_tree:
            return
        self._set_save_badge("editing")
        self._autosave_timer.start()

    def _update_word_count(self) -> None:
        text = self._active_plain_text()
        lines = 0 if not text else len(text.splitlines())
        self._word_count.setText(f"{len(text)} 字 · {lines} 行")

    def _flush_autosave(self) -> None:
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
        if self._current_id is None and not self._active_plain_text().strip():
            return
        self._on_save_body(silent=True)

    def _on_autosave(self) -> None:
        self._on_save_body(silent=True)

    def _insert_timestamp(self) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._ensure_writable()
        cur = self._md_source.textCursor()
        cur.insertText(stamp)
        self._md_source.setTextCursor(cur)
        self._after_md_mutation()

    def _ensure_shortcuts(self) -> None:
        if self._shortcuts:
            return
        win = self.window()
        if win is None:
            return
        for seq, slot in (
            ("Ctrl+S", self._on_save_body),
            ("Ctrl+N", self._on_new_note),
            ("F2", self._on_edit_title),
            ("Ctrl+]", self._on_indent),
            ("Ctrl+[", self._on_outdent),
            ("Alt+Right", self._on_indent),
            ("Alt+Left", self._on_outdent),
        ):
            sc = QShortcut(QKeySequence(seq), win)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)
            sc.setEnabled(False)
            self._shortcuts.append(sc)

    def _set_shortcuts_active(self, on: bool) -> None:
        self._ensure_shortcuts()
        for sc in self._shortcuts:
            sc.setEnabled(on)

    def _sibling_parent_id(self) -> str | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        node = find_note(str(item.data(0, Qt.ItemDataRole.UserRole) or ""))
        if not node:
            return None
        pid = node.get("parent_id")
        return str(pid) if pid else None

    def _reload_tree(self, *, keep_selection: str | None = None) -> None:
        reload_outline_tree(self, keep_selection=keep_selection)

    def _select_tree_id(self, node_id: str) -> None:
        select_tree_id(self._tree, node_id)

    def reveal_note(self, note_id: str) -> None:
        nid = str(note_id or "").strip()
        if not nid:
            return
        if QuickNotepadPage._pending_reveal_id == nid:
            QuickNotepadPage._pending_reveal_id = None
        self._autosave_timer.stop()
        self._flush_autosave()
        if self._search.text().strip():
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self._reload_tree(keep_selection=nid)
        n = find_note(nid)
        if not n:
            return
        self._current_id = nid
        self._title_label.setText(str(n.get("title") or "导入的记事"))
        self._open_note_record(n)
        self._set_save_badge("saved")
        self._update_word_count()
        self._sync_view_chrome()
        self._select_tree_id(nid)
        QTimer.singleShot(0, lambda i=nid: self._select_tree_id(i))
        self.schedule_primary_focus()
        self.report_status(
            f"已打开导入记事：{n.get('title') or nid}", level=StatusLevel.SUCCESS
        )

    def _on_drop_resolved(self, nid: str, parent_id: object, order: int) -> None:
        pid = None if parent_id in (None, "") else str(parent_id)

        def apply() -> None:
            ok = move_node(nid, pid, int(order))
            self._reload_tree(keep_selection=nid)
            self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
            if ok:
                parent = find_note(pid) if pid else None
                tip = (
                    f"已挂到「{parent.get('title') or pid}」下"
                    if parent
                    else "已更新大纲层级"
                )
                self.report_status(tip, level=StatusLevel.INFO)
            else:
                self.report_status("无法移动到该位置，已恢复列表", level=StatusLevel.WARNING)

        QTimer.singleShot(0, apply)

    def _on_indent(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        nid = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if not nid:
            return
        if indent_node(nid):
            self._reload_tree(keep_selection=nid)
            self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.report_status("已降级（成为上一条的子项）", level=StatusLevel.INFO)
        else:
            self.report_status("无法降级：需有上一条同级记事", level=StatusLevel.WARNING)

    def _on_outdent(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        nid = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if not nid:
            return
        if outdent_node(nid):
            self._reload_tree(keep_selection=nid)
            self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.report_status("已升级（提到与父级同级）", level=StatusLevel.INFO)
        else:
            self.report_status("已在顶层，无法再升级", level=StatusLevel.WARNING)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item is not None:
            self._tree.setCurrentItem(item)
            self._on_edit_title()

    def _on_tree_select(self, current: QTreeWidgetItem | None, _previous) -> None:
        if self._rebuilding_tree or current is None:
            return
        nid = str(current.data(0, Qt.ItemDataRole.UserRole) or "")
        if not nid or nid == self._current_id:
            return
        self._flush_autosave()
        n = find_note(nid)
        if n:
            self._current_id = nid
            self._title_label.setText(str(n.get("title") or ""))
            self._open_note_record(n)
            self._set_save_badge("saved")
            self._update_word_count()
            self._sync_view_chrome()

    def _consume_stash(self) -> None:
        stash = QuickNotepadPage._incoming
        if not stash:
            return
        QuickNotepadPage._incoming = None
        title, body, image_path = stash
        self._flush_autosave()
        entry = add_note(
            title or "来自投喂", body or "", parent_id=self._sibling_parent_id()
        )
        self._autosave_timer.stop()
        self._search.clear()
        self._reload_tree(keep_selection=entry["id"])
        n = find_note(entry["id"])
        if n:
            self._current_id = entry["id"]
            self._title_label.setText(str(n.get("title") or ""))
            self._open_note_record(n)
            self._set_save_badge("saved")
            self._update_word_count()
            self._sync_view_chrome()
        if image_path and Path(image_path).is_file():
            self._ensure_writable()
            from modules.quick_notepad.rich_body import markdown_image_snippet

            snippet = markdown_image_snippet(Path(image_path), kind="image")
            self._insert_text_at_cursor(snippet.rstrip("\n"))
            self._flush_autosave()
        self.report_status("已写入记事", level=StatusLevel.SUCCESS)

    def _ensure_current_note(self) -> bool:
        if self._current_id:
            return True
        entry = add_note("新记事", "", parent_id=self._sibling_parent_id())
        self._current_id = entry["id"]
        self._title_label.setText(entry["title"])
        self._reload_tree(keep_selection=self._current_id)
        return True

    def _insert_text_at_cursor(self, text: str) -> None:
        if not text:
            return
        self._ensure_writable()
        cur = self._md_source.textCursor()
        prefix = "\n" if self._md_source.toPlainText() and not text.startswith("\n") else ""
        cur.insertText(prefix + text)
        self._md_source.setTextCursor(cur)

    def _to_clipboard(self) -> None:
        text = (self._capture_body() or "").strip()
        if not text:
            show_warning(self, "正文为空。")
            return
        get_clipboard_watcher().suppress_once()
        QGuiApplication.clipboard().setText(text)
        push_text(text, source="manual")
        self.report_status("正文已复制并写入剪贴板历史", level=StatusLevel.SUCCESS)

    def _current_note_title(self) -> str:
        title = (self._title_label.text() or "").strip()
        return "未命名记事" if (not title or title == "未选择") else title

    def _on_export_pdf(self) -> None:
        self._flush_autosave()
        md = self._capture_body()
        body_html = body_html_for_export(fmt="md", plain_text=md, md_text=md)
        path = export_pdf(
            self,
            title=self._current_note_title(),
            body_html=body_html,
            plain=md,
        )
        if path is not None:
            self.report_status(f"已导出 PDF · {path.name}", level=StatusLevel.SUCCESS)

    def _is_block_drop_target(self, obj) -> bool:
        targets = [
            self._md_source,
            self._editor_surface,
            self._view_stack,
            getattr(self, "_write_pane", None),
        ]
        for t in targets:
            if t is None:
                continue
            if obj is t:
                return True
            vp = getattr(t, "viewport", None)
            if callable(vp) and obj is vp():
                return True
        return False

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            mime = event.mimeData()
            if mime is not None and mime.hasFormat(MIME_BLOCK):
                if self._is_block_drop_target(obj):
                    event.acceptProposedAction()
                    if et == QEvent.Type.Drop:
                        bid = block_id_from_mime(mime)
                        if bid:
                            self._on_palette_insert(bid)
                    return True
        if et == QEvent.Type.KeyPress and obj is self._md_source:
            assert isinstance(event, QKeyEvent)
            if event.matches(QKeySequence.StandardKey.Paste):
                cb = QGuiApplication.clipboard()
                mime = cb.mimeData() if cb else None
                if mime and mime.hasImage():
                    self._paste_clipboard_image()
                    return True
        if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if paths_from_mime(event.mimeData()):
                event.acceptProposedAction()
                return True
        if et == QEvent.Type.Drop:
            paths = paths_from_mime(event.mimeData())
            if paths:
                event.acceptProposedAction()
                import_paths_into_page(self, paths)
                return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime and mime.hasFormat(MIME_BLOCK):
            event.acceptProposedAction()
            return
        if paths_from_mime(mime):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime and mime.hasFormat(MIME_BLOCK):
            event.acceptProposedAction()
            bid = block_id_from_mime(mime)
            if bid:
                self._on_palette_insert(bid)
            return
        paths = paths_from_mime(mime)
        if paths:
            event.acceptProposedAction()
            import_paths_into_page(self, paths)
            return
        super().dropEvent(event)

    def _paste_clipboard_image(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is None:
            return
        img = QImage(cb.image())
        if img.isNull():
            show_warning(self, "剪贴板图片无法插入。")
            return
        self._ensure_current_note()
        self._ensure_writable()
        from modules.quick_notepad.component_blocks import insert_markdown_snippet
        from modules.quick_notepad.md_actions import insert_clipboard_image_snippet

        snippet = insert_clipboard_image_snippet(img, kind="image")
        if not snippet.strip():
            show_warning(self, "剪贴板图片无法保存。")
            return
        insert_markdown_snippet(self._md_source, snippet, at_end=False)
        self._after_md_mutation()
        self.report_status("已粘贴图片（默认合适宽度）", level=StatusLevel.SUCCESS)

    def _on_files_dropped(self, paths) -> None:
        import_paths_into_page(self, [Path(p) for p in (paths or [])])

    def _on_import_md(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入文件",
            "",
            "文档 (*.md *.markdown *.txt *.html *.htm);;"
            "Markdown (*.md *.markdown);;文本 (*.txt);;所有文件 (*.*)",
        )
        if paths:
            import_paths_into_page(self, [Path(p) for p in paths])

    def _seed_new_editor(self) -> None:
        seed_new_editor(self)

    def _on_new_note(self) -> None:
        on_new_note(self)

    def _on_new_below(self) -> None:
        on_new_below(self)

    def _on_edit_title(self) -> None:
        on_edit_title(self)

    def _on_save_body(self, silent: bool = False) -> None:
        on_save_body(self, silent=silent)

    def _on_delete(self) -> None:
        on_delete(self)

    def on_enter(self) -> None:
        self._set_shortcuts_active(True)
        pending = QuickNotepadPage._pending_reveal_id
        if pending:
            self.reveal_note(pending)
        self._consume_stash()
        self.schedule_primary_focus()

    def on_leave(self) -> None:
        self._flush_autosave()
        self._set_shortcuts_active(False)
