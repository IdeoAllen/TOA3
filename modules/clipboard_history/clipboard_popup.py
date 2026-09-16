# -*- coding: utf-8 -*-
"""剪贴板快速面板（对标 Win+V：短语/历史分组 · 1–9 选贴 · 写回原窗口）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeyEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from core.base_dialog import BaseDialog
from core.ui_spec import finalize_dialog_geometry
from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
from modules.clipboard_history.history_store import (
    filter_history,
    find_item,
    image_abs_path,
    load_history,
    notepad_handoff,
    privacy_on,
    source_label,
)
from modules.clipboard_history.phrase_store import load_phrases
from services.icon_registry import device_pixel_ratio
from services.win_paste import get_foreground_hwnd, paste_to_window
from widgets import FormSection, HintLabel, LineEdit, ListWidget, PrimaryButton, SecondaryButton


class ClipboardQuickPopup(BaseDialog):
    """短语一组、历史一组；全局编号 1–9；数字键在对话框内直接粘贴。"""

    dialog_kind = "large"

    def __init__(
        self,
        parent=None,
        *,
        on_open_full=None,
        restore_hwnd: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("剪贴板快速面板")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._on_open_full = on_open_full
        self._restore_hwnd = restore_hwnd
        self._slots: list[dict] = []

        lay = QVBoxLayout(self)
        hint = "历史优先 · 1–9 粘贴到原窗口 · Enter 粘贴选中 · Esc 关闭"
        if privacy_on():
            hint = "隐私时段已开 · 列表遮罩 · 仍可粘贴选中项 · Esc 关闭"
        lay.addWidget(HintLabel(hint))

        self._search = LineEdit()
        self._search.setPlaceholderText("过滤历史（字母搜索；数字键留给 1–9）…")
        self._search.textChanged.connect(self._reload)
        lay.addWidget(self._search)

        body = QHBoxLayout()
        lists = QVBoxLayout()

        phrase_box = FormSection("常用短语")
        self._phrase_list = ListWidget()
        self._phrase_list.setMinimumHeight(96)
        self._phrase_list.setMaximumHeight(140)
        self._phrase_list.itemClicked.connect(lambda _=None: self._sync_from_phrase())
        self._phrase_list.itemDoubleClicked.connect(self._accept_paste)
        phrase_box.add_widget(self._phrase_list)
        lists.addWidget(phrase_box, 1)

        hist_box = FormSection("剪贴板历史")
        self._hist_list = ListWidget()
        self._hist_list.setMinimumHeight(220)
        self._hist_list.itemClicked.connect(lambda _=None: self._sync_from_hist())
        self._hist_list.itemDoubleClicked.connect(self._accept_paste)
        hist_box.add_widget(self._hist_list)
        lists.addWidget(hist_box, 3)
        body.addLayout(lists, 3)

        self._preview_label = QLabel("选中条目预览")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumSize(300, 320)
        self._preview_label.setWordWrap(True)
        body.addWidget(self._preview_label, 2)
        lay.addLayout(body, 1)

        row = QHBoxLayout()
        btn_copy = PrimaryButton("粘贴并关闭")
        btn_copy.clicked.connect(self._accept_paste)
        row.addWidget(btn_copy)
        btn_note = SecondaryButton("送入记事")
        btn_note.setToolTip("将选中历史项送入快速记事（文本或图片）")
        btn_note.clicked.connect(self._send_to_notepad)
        row.addWidget(btn_note)
        btn_agent = SecondaryButton("送到智能体")
        btn_agent.clicked.connect(self._send_to_harness)
        row.addWidget(btn_agent)
        if on_open_full:
            btn_full = SecondaryButton("打开完整页")
            btn_full.clicked.connect(self._open_full)
            row.addWidget(btn_full)
        btn_cancel = SecondaryButton("关闭")
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)
        row.addStretch(1)
        lay.addLayout(row)

        self._active_list = self._phrase_list
        # WidgetWithChildren：焦点在列表/搜索框时 1–9 仍可用
        for n in range(1, 10):
            sc = QShortcut(QKeySequence(str(n)), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda i=n - 1: self._paste_slot(i))
        for seq, slot in (
            (Qt.Key.Key_Return, self._accept_paste),
            (Qt.Key.Key_Enter, self._accept_paste),
            (Qt.Key.Key_Escape, self.reject),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        self._reload()
        if self._hist_list.count() > 0:
            self._hist_list.setFocus()
        else:
            self._phrase_list.setFocus()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._reload()
        if self._hist_list.count() > 0:
            self._hist_list.setFocus()
        else:
            self._phrase_list.setFocus()
        # 内容刷新后尺寸可能变化，再定一次并居中
        finalize_dialog_geometry(self, self.dialog_kind)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        # 1–9：不依赖 QShortcut（搜索框焦点时也能用）
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            self._paste_slot(int(key) - int(Qt.Key.Key_1))
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept_paste()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def _reload(self) -> None:
        q = (self._search.text() or "").strip()
        priv = privacy_on()
        self._slots = []
        self._phrase_list.clear()
        self._hist_list.clear()

        # 短语占前若干号
        for x in load_phrases():
            if len(self._slots) >= 9:
                break
            text = str(x.get("text") or "").strip()
            if not text:
                continue
            if q and q.lower() not in text.lower():
                continue
            self._slots.append({"kind": "phrase", "text": text, "group": "phrase"})

        phrase_n = len(self._slots)
        for i, slot in enumerate(self._slots):
            preview = slot["text"].replace("\n", " ")
            if priv:
                preview = "••••"
            elif len(preview) > 40:
                preview = preview[:39] + "…"
            self._phrase_list.addItem(f"{i + 1}. {preview}")

        # 历史补足到 9；搜索时可多列（共用 filter_history）
        hist_start = len(self._slots)
        limit = 9 if not q else 80
        for x in filter_history(load_history(), query=q):
            if len(self._slots) >= limit:
                break
            iid = str(x.get("id") or "")
            if not iid:
                continue
            self._slots.append({"kind": "history", "id": iid, "item": x, "group": "history"})

        for i, slot in enumerate(self._slots[hist_start:], start=hist_start):
            x = slot.get("item") or {}
            star = "★ " if x.get("pinned") else ""
            kind = "图" if x.get("kind") == "image" else "文"
            src = source_label(str(x.get("source") or ""))
            preview = "••••" if priv else (x.get("text") or "").replace("\n", " ")[:40]
            num = f"{i + 1}. " if i < 9 else "   "
            self._hist_list.addItem(f"{num}{star}[{kind}] {src} · {preview}")

        if phrase_n > 0:
            self._phrase_list.setCurrentRow(0)

        hist_count = self._hist_list.count()
        if hist_count > 0:
            self._hist_list.setCurrentRow(0)
            self._active_list = self._hist_list
            self._phrase_list.clearSelection()
        elif phrase_n > 0:
            self._active_list = self._phrase_list
            self._hist_list.clearSelection()
        elif self._slots:
            self._active_list = self._phrase_list
        self._update_preview()

    def _slot_index_from_ui(self) -> int:
        if self._active_list is self._phrase_list:
            row = self._phrase_list.currentRow()
            if row < 0:
                return -1
            return row
        row = self._hist_list.currentRow()
        if row < 0:
            return -1
        # 历史列表从 phrase 数量之后开始编号
        phrase_count = self._phrase_list.count()
        return phrase_count + row

    def _sync_from_phrase(self) -> None:
        self._active_list = self._phrase_list
        self._hist_list.clearSelection()
        self._update_preview()

    def _sync_from_hist(self) -> None:
        self._active_list = self._hist_list
        self._phrase_list.clearSelection()
        self._update_preview()

    def _current_slot(self) -> dict | None:
        idx = self._slot_index_from_ui()
        if 0 <= idx < len(self._slots):
            return self._slots[idx]
        return None

    def _update_preview(self) -> None:
        slot = self._current_slot()
        if not slot:
            self._preview_label.setText("选中条目预览")
            self._preview_label.setPixmap(QPixmap())
            return
        if privacy_on():
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("••••（隐私时段 · 内容已遮罩）")
            return
        if slot["kind"] == "phrase":
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText(str(slot.get("text") or "")[:800])
            return
        item = find_item(str(slot.get("id") or "")) or slot.get("item")
        if not item:
            self._preview_label.setText("选中条目预览")
            return
        if item.get("kind") == "image":
            path = image_abs_path(item)
            if path is None:
                self._preview_label.setText("[图片丢失]")
                self._preview_label.setPixmap(QPixmap())
                return
            pix = QPixmap(str(path))
            if pix.isNull():
                self._preview_label.setText("[无法加载]")
                self._preview_label.setPixmap(QPixmap())
                return
            dpr = max(device_pixel_ratio(self), 1.0)
            logical_w, logical_h = 280, 260
            phys_w = max(1, int(round(logical_w * dpr)))
            phys_h = max(1, int(round(logical_h * dpr)))
            scaled = pix.scaled(
                phys_w,
                phys_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            self._preview_label.setPixmap(scaled)
            self._preview_label.setText("")
        else:
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText(str(item.get("text") or "")[:800])

    def _write_slot(self, slot: dict) -> bool:
        get_clipboard_watcher().suppress_once()
        cb = QGuiApplication.clipboard()
        if cb is None:
            return False
        if slot["kind"] == "phrase":
            cb.setText(str(slot.get("text") or ""))
            return True
        item = find_item(str(slot.get("id") or "")) or slot.get("item")
        if not item:
            return False
        if item.get("kind") == "image":
            path = image_abs_path(item)
            if path is None:
                return False
            pix = QPixmap(str(path))
            if pix.isNull():
                return False
            cb.setPixmap(pix)
        else:
            cb.setText(str(item.get("text") or ""))
        return True

    def _paste_slot(self, index: int) -> None:
        if not (0 <= index < len(self._slots) and index < 9):
            return
        if self._write_slot(self._slots[index]):
            self._finish_paste()

    def _accept_paste(self) -> None:
        slot = self._current_slot()
        if not slot:
            return
        if self._write_slot(slot):
            self._finish_paste()

    def _finish_paste(self) -> None:
        hwnd = self._restore_hwnd
        self.accept()
        QTimer.singleShot(120, lambda: paste_to_window(hwnd))

    def _open_full(self) -> None:
        self.accept()
        if self._on_open_full:
            self._on_open_full()

    def _send_to_notepad(self) -> None:
        from core.user_messages import show_warning

        slot = self._current_slot()
        if not slot:
            show_warning(self, "请先选中一条历史。")
            return
        if slot["kind"] == "phrase":
            text = str(slot.get("text") or "").strip()
            if not text:
                show_warning(self, "没有可写入的文本。")
                return
            payload = {"title": "来自剪贴板速贴", "body": text, "image_path": None}
        else:
            item = find_item(str(slot.get("id") or "")) or slot.get("item")
            payload = notepad_handoff(item)
            if not payload:
                show_warning(self, "该条无法送入记事（空文本或图片丢失）。")
                return
        from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

        QuickNotepadPage.stash_incoming(
            str(payload.get("body") or ""),
            title=str(payload.get("title") or "来自剪贴板历史"),
            image_path=payload.get("image_path"),
        )
        shell = self.parent()
        self.accept()
        if shell is not None:
            if hasattr(shell, "showNormal"):
                shell.showNormal()
                shell.raise_()
                shell.activateWindow()
            if hasattr(shell, "navigate"):
                shell.navigate("quick_notepad")
            elif hasattr(shell, "_summon_module"):
                shell._summon_module("quick_notepad")

    def _send_to_harness(self) -> None:
        slot = self._current_slot()
        if not slot:
            return
        if slot["kind"] == "phrase":
            text = str(slot.get("text") or "").strip()
        else:
            item = find_item(str(slot.get("id") or "")) or slot.get("item")
            if not item or item.get("kind") == "image":
                from core.user_messages import show_warning

                show_warning(self, "图片条目请先在完整页处理或复制文字后再送智能体。")
                return
            text = str(item.get("text") or "").strip()
        if not text:
            from core.user_messages import show_warning

            show_warning(self, "没有可发送的文本。")
            return
        from services.harness_feed import navigate_to_harness

        shell = self.parent()
        if shell is not None:
            self.accept()
            navigate_to_harness(shell, text, title="来自剪贴板速贴", source="clipboard_popup")


def open_clipboard_quick_popup(shell) -> None:
    """热键入口：不抢主窗前台，记当前窗口以便粘贴写回。"""
    restore_hwnd = get_foreground_hwnd()

    def _full() -> None:
        if shell is not None:
            shell.showNormal()
            shell.raise_()
            shell.activateWindow()
            if hasattr(shell, "_summon_module"):
                shell._summon_module("clipboard_history")

    dlg = ClipboardQuickPopup(shell, on_open_full=_full, restore_hwnd=restore_hwnd)
    dlg.exec()
