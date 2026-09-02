# -*- coding: utf-8 -*-
"""文件打包归档页。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.file_packager.pack_service import (
    PRESETS,
    PackEntry,
    collect_entries,
    render_zip_name,
    write_zip,
)
from services.storage_paths import module_output_dir
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)


class FilePackagerPage(BasePage):
    page_id = "file_packager"
    page_title = "文件打包归档"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._roots: list[str] = []
        self._entries: list[PackEntry] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "文件打包归档",
                "选文件/文件夹 → 预览清单（可剔项）→ 规范命名打 zip。",
            )
        )

        src = FormSection("来源")
        row = QHBoxLayout()
        btn_files = SecondaryButton("添加文件…")
        btn_files.clicked.connect(self._add_files)
        row.addWidget(btn_files)
        btn_dirs = SecondaryButton("添加文件夹…")
        btn_dirs.clicked.connect(self._add_dirs)
        row.addWidget(btn_dirs)
        btn_clear = SecondaryButton("清空来源")
        btn_clear.clicked.connect(self._clear_roots)
        row.addWidget(btn_clear)
        row.addStretch(1)
        src.add_layout(row)
        self._roots_hint = HintLabel("尚未选择")
        src.add_widget(self._roots_hint)
        scroll.add_widget(src)

        opts = FormSection("预设与过滤")
        row_p = QHBoxLayout()
        row_p.addWidget(HintLabel("预设"))
        self._preset = ComboBox()
        for key, (label, _tpl) in PRESETS.items():
            self._preset.addItem(label, key)
        self._preset.currentIndexChanged.connect(self._apply_preset_name)
        row_p.addWidget(self._preset, 1)
        opts.add_layout(row_p)

        row_n = QHBoxLayout()
        row_n.addWidget(HintLabel("输出文件名"))
        self._out_name = LineEdit()
        row_n.addWidget(self._out_name, 1)
        opts.add_layout(row_n)
        self._class_name = LineEdit()
        self._class_name.setPlaceholderText("班级名（可选，用于 {class}）")
        self._class_name.textChanged.connect(self._apply_preset_name)
        opts.add_widget(self._class_name)

        self._skip_empty = CheckBox("跳过空目录")
        self._skip_empty.setChecked(True)
        opts.add_widget(self._skip_empty)
        self._exclude = LineEdit()
        self._exclude.setPlaceholderText("排除后缀，逗号分隔，如 tmp,log,bak")
        opts.add_widget(HintLabel("排除后缀"))
        opts.add_widget(self._exclude)
        self._with_manifest = CheckBox("同时生成相对路径清单.txt")
        self._with_manifest.setChecked(True)
        opts.add_widget(self._with_manifest)
        scroll.add_widget(opts)

        prev = FormSection("入包预览（取消勾选则不入包）")
        row_a = QHBoxLayout()
        btn_refresh = SecondaryButton("刷新预览")
        btn_refresh.clicked.connect(self._refresh_preview)
        row_a.addWidget(btn_refresh)
        row_a.addStretch(1)
        prev.add_layout(row_a)
        self._list = ListWidget()
        self._list.setMinimumHeight(200)
        prev.add_widget(self._list)
        scroll.add_widget(prev)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("打包")
        btn_go.clicked.connect(self._on_pack)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        scroll.add_layout(actions)

        log = FormSection("结果")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(100)
        log.add_widget(self._log)
        scroll.add_widget(log)
        scroll.add_stretch(1)

        self._apply_preset_name()
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._out_name

    def _apply_preset_name(self) -> None:
        key = str(self._preset.currentData() or "general")
        _label, tpl = PRESETS.get(key, PRESETS["general"])
        self._out_name.setText(render_zip_name(tpl, class_name=self._class_name.text()))

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        for p in paths:
            if p not in self._roots:
                self._roots.append(p)
        self._update_roots_hint()
        self._refresh_preview()

    def _add_dirs(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path and path not in self._roots:
            self._roots.append(path)
        self._update_roots_hint()
        self._refresh_preview()

    def _clear_roots(self) -> None:
        self._roots.clear()
        self._entries.clear()
        self._list.clear()
        self._update_roots_hint()

    def _update_roots_hint(self) -> None:
        if not self._roots:
            self._roots_hint.setText("尚未选择")
            return
        names = [Path(p).name for p in self._roots[:8]]
        extra = f" 等 {len(self._roots)} 项" if len(self._roots) > 8 else f" · {len(self._roots)} 项"
        self._roots_hint.setText("、".join(names) + (extra if len(self._roots) > 1 else f" · {len(self._roots)} 项"))

    def _exclude_list(self) -> list[str]:
        raw = self._exclude.text().replace("，", ",")
        return [x.strip() for x in raw.split(",") if x.strip()]

    def _refresh_preview(self) -> None:
        if not self._roots:
            self._list.clear()
            self._entries = []
            return
        self._entries = collect_entries(
            self._roots,
            exclude_suffixes=self._exclude_list(),
            skip_empty_dirs=self._skip_empty.isChecked(),
        )
        self._list.clear()
        for e in self._entries:
            item = QListWidgetItem(e.arcname)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, e.arcname)
            self._list.addItem(item)
        self.report_status(f"预览 {len(self._entries)} 项")

    def _selected_entries(self) -> list[PackEntry]:
        checked: set[str] = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked.add(str(item.data(Qt.ItemDataRole.UserRole) or item.text()))
        return [e for e in self._entries if e.arcname in checked]

    def _on_pack(self) -> None:
        if not self._roots:
            show_warning(self, "请先添加文件或文件夹。")
            return
        if not self._entries:
            self._refresh_preview()
        selected = self._selected_entries()
        if not selected:
            show_warning(self, "预览清单为空或未勾选任何项。")
            return
        name = self._out_name.text().strip() or render_zip_name("归档_{date}")
        if not name.lower().endswith(".zip"):
            name += ".zip"

        def _run() -> None:
            out_dir = module_output_dir(self.page_id, create=True)
            zip_path = Path(out_dir) / name
            result = write_zip(
                selected,
                zip_path,
                write_manifest=self._with_manifest.isChecked(),
            )
            self._log.setPlainText(result.summary)
            if result.zip_path:
                self.report_status(
                    f"打包完成 · {result.file_count} 文件",
                    level=StatusLevel.SUCCESS if not result.errors else StatusLevel.WARNING,
                )
                show_saved(self, result.summary.split("\n", 1)[0], result.zip_path)
            else:
                self.report_status("打包失败", level=StatusLevel.ERROR)
                show_warning(self, result.summary)

        self.run_safe(_run, title="打包失败")

    def on_enter(self) -> None:
        self.report_status("文件打包归档 · 预览后规范命名 zip")
