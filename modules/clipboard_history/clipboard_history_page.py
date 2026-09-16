# -*- coding: utf-8 -*-
"""剪贴板历史：热键速贴 + 常用短语 + 精简历史。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
from modules.clipboard_history.history_store import (
    clear_history,
    delete_item,
    filter_history,
    find_item,
    image_abs_path,
    list_line,
    load_history,
    notepad_handoff,
    privacy_on,
    push_clipboard_image,
    push_text,
    toggle_pin,
)
from modules.clipboard_history.phrase_store import add_phrase, delete_phrase, load_phrases
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)
from widgets.list_edit import ListPanel, confirm_delete

_SOURCE_FILTERS = (
    ("", "全部来源"),
    ("screenshot", "截图"),
    ("ocr", "OCR"),
    ("auto", "自动"),
    ("manual", "手动"),
)


class ClipboardHistoryPage(BasePage):
    page_id = "clipboard_history"
    page_title = "剪贴板历史"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._ids: list[str] = []
        self._phrase_ids: list[str] = []
        self._copy_target = "history"  # phrase | history
        self._shortcuts: list[QShortcut] = []
        self._source_key = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)
        # 侧栏已有模块名；热键说明放自动捕获 ToolTip，不占常驻顶栏
        tools = QHBoxLayout()
        self._search = LineEdit()
        self._search.setPlaceholderText("搜索历史（正文 / 来源）…")
        self._search.textChanged.connect(self._reload)
        tools.addWidget(self._search, 1)
        self._source = ComboBox()
        for key, label in _SOURCE_FILTERS:
            self._source.addItem(label, key)
        self._source.setToolTip("按来源过滤（截图同源可筛）")
        self._source.currentIndexChanged.connect(self._on_source_changed)
        tools.addWidget(self._source)
        self._auto = CheckBox("自动捕获")
        self._auto.setChecked(True)
        self._auto.setToolTip(
            "开启后复制/截图文字自动入库；钉选不会被清理。速贴 Alt+Shift+C · 双击或 Ctrl+C 复制。"
        )
        self._auto.toggled.connect(lambda on: get_clipboard_watcher().set_enabled(on))
        tools.addWidget(self._auto)
        self._privacy = CheckBox("隐私时段")
        self._privacy.setToolTip(
            "开会/投屏：暂停一切入库（含截图/OCR），列表与预览遮罩正文。"
        )
        self._privacy.toggled.connect(self._on_privacy_toggled)
        tools.addWidget(self._privacy)
        scroll.add_layout(tools)

        body = QHBoxLayout()
        box = FormSection("剪贴板历史")
        self._list = ListPanel(
            add_label="捕获",
            edit_label="复制",
            delete_label="删除",
            show_refresh=False,
            hint="★置顶 · 双击 / Ctrl+C 复制 · Delete 删除 · 隐私时段遮罩",
        )
        self._list.list_widget.setMinimumHeight(360)
        self._list.bind_add(self._capture)
        self._list.bind_edit(self._copy_selected)
        self._list.bind_delete(self._delete_selected)
        self._list.bind_refresh(self._reload)
        self._list.list_widget.itemSelectionChanged.connect(self._on_select)
        self._list.list_widget.itemClicked.connect(lambda _=None: self._set_copy_target("history"))
        self._list.list_widget.itemDoubleClicked.connect(self._copy_selected)
        self._list.list_widget.installEventFilter(self)
        box.add_widget(self._list)
        row = QHBoxLayout()
        btn_pin = SecondaryButton("置顶")
        btn_pin.clicked.connect(self._toggle_pin)
        row.addWidget(btn_pin)
        btn_to_note = SecondaryButton("送入记事")
        btn_to_note.setToolTip("把当前历史项写入快速记事（文本或图片）")
        btn_to_note.clicked.connect(self._send_to_notepad)
        row.addWidget(btn_to_note)
        btn_to_agent = SecondaryButton("送到智能体")
        btn_to_agent.setToolTip("将文本送入 Harness 编码智能体")
        btn_to_agent.clicked.connect(self._send_to_harness)
        row.addWidget(btn_to_agent)
        btn_clear = SecondaryButton("清空")
        btn_clear.setToolTip("清空未置顶的历史")
        btn_clear.clicked.connect(self._clear)
        row.addWidget(btn_clear)
        row.addStretch(1)
        box.add_layout(row)
        body.addWidget(box, 3)

        preview = FormSection("预览")
        self._stack = QStackedWidget()
        self._preview_text = ReadOnlyPlainTextEdit()
        self._preview_text.setMinimumHeight(360)
        self._preview_text.installEventFilter(self)
        self._stack.addWidget(self._preview_text)
        self._preview_img = QLabel("（图片预览）")
        self._preview_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_img.setMinimumHeight(360)
        self._stack.addWidget(self._preview_img)
        preview.add_widget(self._stack)
        preview.add_widget(HintLabel("Ctrl+C 或双击列表项复制到剪贴板。隐私时段预览亦遮罩。"))
        body.addWidget(preview, 2)
        scroll.add_layout(body)

        phrases = FormSection("常用短语（可选）")
        phrases.add_widget(HintLabel("话术模板；速贴面板 Alt+Shift+C 也可一键选。"))
        self._phrase_list = ListWidget()
        self._phrase_list.setMaximumHeight(88)
        self._phrase_list.itemClicked.connect(lambda _=None: self._set_copy_target("phrase"))
        self._phrase_list.itemDoubleClicked.connect(self._copy_phrase)
        self._phrase_list.installEventFilter(self)
        phrases.add_widget(self._phrase_list)
        prow = QHBoxLayout()
        self._phrase_edit = LineEdit()
        self._phrase_edit.setPlaceholderText("新短语，Enter 添加")
        self._phrase_edit.returnPressed.connect(self._add_phrase)
        prow.addWidget(self._phrase_edit, 1)
        btn_add_p = SecondaryButton("添加")
        btn_add_p.clicked.connect(self._add_phrase)
        prow.addWidget(btn_add_p)
        btn_del_p = SecondaryButton("删除")
        btn_del_p.clicked.connect(self._del_phrase)
        prow.addWidget(btn_del_p)
        prow.addStretch(1)
        phrases.add_layout(prow)
        scroll.add_widget(phrases)

        self._sync_privacy_ui(block_signal=True)
        self._reload_phrases()
        self._reload()
        self._bind_shortcuts()
        w = get_clipboard_watcher()
        w.captured.connect(lambda _=None: self._reload())
        w.privacy_changed.connect(lambda _on: self._on_privacy_external())

    def _bind_shortcuts(self) -> None:
        if self._shortcuts:
            return
        for seq, slot in (
            (QKeySequence.StandardKey.Copy, self._copy_smart),
            (QKeySequence("Ctrl+C"), self._copy_smart),
            (QKeySequence(Qt.Key.Key_Return), self._copy_smart),
            (QKeySequence(Qt.Key.Key_Enter), self._copy_smart),
            (QKeySequence(Qt.Key.Key_Delete), self._delete_selected),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            sc.setEnabled(False)
            self._shortcuts.append(sc)

    def _set_shortcuts_active(self, on: bool) -> None:
        for sc in self._shortcuts:
            sc.setEnabled(on)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Copy):
                if obj is self._phrase_list:
                    self._set_copy_target("phrase")
                    self._copy_smart()
                    return True
                if obj is self._list.list_widget:
                    self._set_copy_target("history")
                    self._copy_smart()
                    return True
                if obj is self._preview_text:
                    self._copy_smart()
                    return True
            if event.key() == Qt.Key.Key_Delete and obj is self._list.list_widget:
                self._delete_selected()
                return True
        return super().eventFilter(obj, event)

    def _set_copy_target(self, target: str) -> None:
        self._copy_target = "phrase" if target == "phrase" else "history"

    def _on_source_changed(self, _index: int = 0) -> None:
        data = self._source.currentData()
        self._source_key = str(data or "")
        self._reload()

    def _sync_privacy_ui(self, *, block_signal: bool = False) -> None:
        on = privacy_on()
        if block_signal:
            self._privacy.blockSignals(True)
        self._privacy.setChecked(on)
        if block_signal:
            self._privacy.blockSignals(False)
        get_clipboard_watcher().set_privacy(on)

    def _on_privacy_toggled(self, on: bool) -> None:
        get_clipboard_watcher().set_privacy(bool(on))
        self._reload()
        if on:
            self.report_status("隐私时段已开 · 暂停入库并遮罩", level=StatusLevel.WARNING)
        else:
            self.report_status("隐私时段已关 · 恢复捕获", level=StatusLevel.SUCCESS)

    def _on_privacy_external(self) -> None:
        self._sync_privacy_ui(block_signal=True)
        self._reload()

    def _copy_smart(self) -> None:
        """Ctrl+C：短语列表焦点/最近点选 → 复制短语；否则复制历史。输入框交给原控件。"""
        from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)) and fw not in (
            self._preview_text,
        ):
            # 搜索框 / 新短语输入：走原生复制选区
            if hasattr(fw, "copy"):
                fw.copy()
            return
        if fw is self._phrase_list or self._copy_target == "phrase":
            if self._phrase_list.currentRow() >= 0:
                self._copy_phrase()
                return
        self._copy_selected()

    def _reload_phrases(self) -> None:
        items = load_phrases()
        self._phrase_ids = [str(x.get("id") or "") for x in items]
        self._phrase_list.clear()
        for x in items:
            self._phrase_list.addItem(str(x.get("text") or "")[:80])

    def _add_phrase(self) -> None:
        text = self._phrase_edit.text().strip()
        if not text:
            show_warning(self, "请输入短语内容。")
            return
        add_phrase(text)
        self._phrase_edit.clear()
        self._reload_phrases()
        self.report_status("已添加常用短语", level=StatusLevel.SUCCESS)

    def _del_phrase(self) -> None:
        row = self._phrase_list.currentRow()
        if row < 0 or row >= len(self._phrase_ids):
            return
        delete_phrase(self._phrase_ids[row])
        self._reload_phrases()

    def _copy_phrase(self) -> None:
        row = self._phrase_list.currentRow()
        if row < 0 or row >= len(self._phrase_ids):
            show_warning(self, "请先选中一条常用短语。")
            return
        text = self._phrase_list.item(row).text()
        get_clipboard_watcher().suppress_once()
        QGuiApplication.clipboard().setText(text)
        self.report_status("短语已复制", level=StatusLevel.SUCCESS)

    def _filtered(self) -> list[dict]:
        return filter_history(
            load_history(),
            query=self._search.text() or "",
            source=self._source_key,
        )

    def _reload(self) -> None:
        items = self._filtered()
        priv = privacy_on()
        self._ids = [str(x.get("id") or "") for x in items]
        lines = [list_line(x, privacy=priv) for x in items]
        self._list.set_items(lines)
        tag = " · 隐私" if priv else ""
        self.report_status(f"历史 {len(items)} · 短语 {len(self._phrase_ids)}{tag}")
        # 刷新当前预览遮罩态
        self._on_select()

    def _current_id(self) -> str | None:
        row = self._list.current_row()
        if 0 <= row < len(self._ids):
            return self._ids[row]
        return None

    def _on_select(self) -> None:
        iid = self._current_id()
        item = find_item(iid) if iid else None
        if not item:
            self._preview_text.clear()
            self._stack.setCurrentIndex(0)
            return
        if privacy_on():
            self._preview_text.setPlainText("••••（隐私时段 · 内容已遮罩）")
            self._preview_img.setPixmap(QPixmap())
            self._preview_img.setText("••••（隐私时段）")
            self._stack.setCurrentIndex(0)
            return
        if item.get("kind") == "image":
            path = image_abs_path(item)
            if path is not None:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    from services.icon_registry import device_pixel_ratio

                    dpr = max(device_pixel_ratio(self), 1.0)
                    lw, lh = 480, 320
                    pw = max(1, int(round(lw * dpr)))
                    ph = max(1, int(round(lh * dpr)))
                    scaled = pix.scaled(
                        pw,
                        ph,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    scaled.setDevicePixelRatio(dpr)
                    self._preview_img.setMinimumSize(lw, lh)
                    self._preview_img.setPixmap(scaled)
                    self._preview_img.setText("")
                    self._stack.setCurrentIndex(1)
                    return
            self._preview_text.setPlainText(str(item.get("text") or "[图片丢失]"))
            self._stack.setCurrentIndex(0)
        else:
            self._preview_text.setPlainText(str(item.get("text") or ""))
            self._stack.setCurrentIndex(0)

    def _capture(self) -> None:
        if privacy_on():
            show_warning(self, "隐私时段中，无法捕获入库。请先关闭隐私时段。")
            return
        cb = QGuiApplication.clipboard()
        if cb is None:
            return
        text = (cb.text() or "").strip()
        if text:
            push_text(text, source="manual")
        else:
            entry = push_clipboard_image(cb, source="manual")
            if entry is None:
                self.report_status("剪贴板为空", level=StatusLevel.WARNING)
                return
        self._reload()
        self.report_status("已捕获", level=StatusLevel.SUCCESS)

    def _copy_selected(self) -> None:
        iid = self._current_id()
        item = find_item(iid) if iid else None
        if not item:
            return
        get_clipboard_watcher().suppress_once()
        cb = QGuiApplication.clipboard()
        if cb is None:
            return
        if item.get("kind") == "image":
            path = image_abs_path(item)
            if path is None:
                return
            from PySide6.QtCore import QByteArray, QMimeData

            mime = QMimeData()
            data = path.read_bytes()
            suf = path.suffix.lower()
            if suf in (".jpg", ".jpeg"):
                mime.setData("image/jpeg", QByteArray(data))
            elif suf == ".bmp":
                mime.setData("image/bmp", QByteArray(data))
            elif suf == ".webp":
                mime.setData("image/webp", QByteArray(data))
            else:
                mime.setData("image/png", QByteArray(data))
            pix = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull():
                mime.setImageData(pix.toImage())
            cb.setMimeData(mime)
        else:
            cb.setText(str(item.get("text") or ""))
        self.report_status("已复制到剪贴板", level=StatusLevel.SUCCESS)

    def _toggle_pin(self) -> None:
        iid = self._current_id()
        if not iid:
            return
        toggle_pin(iid)
        self._reload()

    def _send_to_notepad(self) -> None:
        iid = self._current_id()
        item = find_item(iid) if iid else None
        payload = notepad_handoff(item)
        if not payload:
            if not item:
                show_warning(self, "请先选择一条历史。")
            elif item.get("kind") == "image":
                show_warning(self, "图片文件已丢失。")
            else:
                show_warning(self, "该条没有可写入的文本。")
            return
        from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

        QuickNotepadPage.stash_incoming(
            str(payload.get("body") or ""),
            title=str(payload.get("title") or "来自剪贴板历史"),
            image_path=payload.get("image_path"),
        )
        win = self.window()
        if win is not None and hasattr(win, "navigate"):
            win.navigate("quick_notepad")
        self.report_status("已送入记事", level=StatusLevel.SUCCESS)

    def _send_to_harness(self) -> None:
        iid = self._current_id()
        item = find_item(iid) if iid else None
        if not item:
            show_warning(self, "请先选择一条历史。")
            return
        if item.get("kind") == "image":
            show_warning(self, "图片条目请先用 OCR 或复制说明文字后再送智能体。")
            return
        text = str(item.get("text") or "").strip()
        if not text:
            show_warning(self, "该条没有可发送的文本。")
            return
        from services.harness_feed import navigate_to_harness

        win = self.window()
        if win is not None:
            navigate_to_harness(win, text, title="来自剪贴板历史", source="clipboard_history")
        self.report_status("已送入编码智能体", level=StatusLevel.SUCCESS)

    def _delete_selected(self) -> None:
        iid = self._current_id()
        if not iid:
            return
        delete_item(iid)
        self._preview_text.clear()
        self._reload()

    def _clear(self) -> None:
        if not confirm_delete(self, "未置顶的剪贴板历史"):
            return
        clear_history(keep_pinned=True)
        self._preview_text.clear()
        self._reload()

    def on_enter(self) -> None:
        get_clipboard_watcher().set_enabled(self._auto.isChecked())
        # 恢复持久化隐私态，禁止进页强关
        self._sync_privacy_ui(block_signal=True)
        self._reload_phrases()
        self._reload()
        self._set_shortcuts_active(True)
        priv = " · 隐私时段" if privacy_on() else ""
        self.report_status(f"剪贴板 · Alt+Shift+C 速贴{priv}")

    def on_leave(self) -> None:
        self._set_shortcuts_active(False)
