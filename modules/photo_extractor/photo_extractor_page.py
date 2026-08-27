# -*- coding: utf-8 -*-
"""照片提取：子目录多选 + 进度 + 复制/长图。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.photo_extractor.photo_extractor_service import (
    collect_photos,
    collect_photos_from_dirs,
    extract_photos,
    list_subdirectories,
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
    ProgressBar,
    ScrollPage,
    SecondaryButton,
)


class PhotoExtractorPage(BasePage):
    page_id = "photo_extractor"
    page_title = "照片提取"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._subdirs: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "照片提取",
                "选班级根目录 → 勾选子文件夹 → 复制图片或拼成长图。",
            )
        )

        path_box = FormSection("源文件夹")
        row = QHBoxLayout()
        self._folder = LineEdit()
        self._folder.setPlaceholderText("选择含照片的文件夹…")
        row.addWidget(self._folder, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        btn_reload = SecondaryButton("刷新子目录")
        btn_reload.clicked.connect(self._reload_subs)
        row.addWidget(btn_reload)
        path_box.add_layout(row)
        self._recursive = CheckBox("子目录内继续递归")
        self._recursive.setChecked(True)
        path_box.add_widget(self._recursive)
        scroll.add_widget(path_box)

        mid = QHBoxLayout()
        sub_box = FormSection("子目录（可多选）")
        self._subs = ListWidget()
        self._subs.setSelectionMode(self._subs.SelectionMode.MultiSelection)
        self._subs.setMinimumHeight(220)
        self._subs.itemSelectionChanged.connect(self._update_count)
        sub_box.add_widget(self._subs)
        row_sel = QHBoxLayout()
        btn_all = SecondaryButton("全选")
        btn_all.clicked.connect(self._subs.selectAll)
        row_sel.addWidget(btn_all)
        btn_none = SecondaryButton("取消")
        btn_none.clicked.connect(self._subs.clearSelection)
        row_sel.addWidget(btn_none)
        row_sel.addStretch(1)
        sub_box.add_layout(row_sel)
        mid.addWidget(sub_box, 1)

        mode_box = FormSection("导出")
        self._mode = ComboBox()
        self._mode.addItem("复制图片到输出目录", "copy")
        self._mode.addItem("生成 Word (.docx)", "word")
        self._mode.addItem("生成 PPT (.pptx)", "ppt")
        self._mode.addItem("生成 PDF", "pdf")
        self._mode.addItem("生成竖向长图", "long_image")
        mode_box.add_widget(self._mode)
        self._count = HintLabel("未选择子目录时，将处理整个根目录。")
        mode_box.add_widget(self._count)
        mode_box.add_widget(
            HintLabel("Word/PPT/PDF 需 python-docx、python-pptx、PyPDF2、reportlab。")
        )
        mid.addWidget(mode_box, 1)
        scroll.add_layout(mid)

        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        scroll.add_widget(self._progress)

        actions = QHBoxLayout()
        btn_run = PrimaryButton("开始提取")
        btn_run.clicked.connect(self._on_run)
        actions.addWidget(btn_run)
        btn_open = SecondaryButton("打开输出目录")
        btn_open.clicked.connect(self._open_out)
        actions.addWidget(btn_open)
        actions.addStretch(1)
        scroll.add_layout(actions)

        self._result = HintLabel("就绪。")
        scroll.add_widget(self._result)
        scroll.add_stretch(1)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择照片文件夹")
        if path:
            self._folder.setText(path)
            self._reload_subs()

    def _reload_subs(self) -> None:
        folder = self._folder.text().strip()
        self._subs.clear()
        self._subdirs = []
        if not folder or not Path(folder).is_dir():
            return
        self._subdirs = list_subdirectories(folder)
        for d in self._subdirs:
            n = len(collect_photos(d, recursive=self._recursive.isChecked()))
            self._subs.addItem(f"{Path(d).name}  ({n} 张)")
        if not self._subdirs:
            self._count.setText(
                f"无子目录；根目录约 {len(collect_photos(folder, recursive=True))} 张。"
            )
        else:
            self._subs.selectAll()
            self._update_count()

    def _selected_dirs(self) -> list[str]:
        rows = self._subs.selectedIndexes()
        dirs = []
        for ix in rows:
            r = ix.row()
            if 0 <= r < len(self._subdirs):
                dirs.append(self._subdirs[r])
        return dirs

    def _update_count(self) -> None:
        folder = self._folder.text().strip()
        dirs = self._selected_dirs()
        if dirs:
            photos = collect_photos_from_dirs(dirs, recursive=self._recursive.isChecked())
            self._count.setText(f"已选 {len(dirs)} 个子目录 · 约 {len(photos)} 张图")
        elif folder:
            photos = collect_photos(folder, recursive=self._recursive.isChecked())
            self._count.setText(f"未勾选子目录 · 将处理根目录约 {len(photos)} 张")
        else:
            self._count.setText("请先选择文件夹。")

    def _on_run(self) -> None:
        folder = self._folder.text().strip()
        if not folder:
            show_warning(self, "请先选择源文件夹。")
            return
        dirs = self._selected_dirs()
        mode = self._mode.currentData() or "copy"

        def _run() -> None:
            out = module_output_dir(self.page_id, create=True)
            self._progress.setValue(10)
            if dirs:
                # 按选中子目录分别提取到子文件夹，再汇总
                from modules.photo_extractor.photo_extractor_service import ExtractResult

                total = ExtractResult(mode=str(mode), output_path=str(out))
                for i, d in enumerate(dirs, start=1):
                    sub_out = out / Path(d).name
                    sub_out.mkdir(parents=True, exist_ok=True)
                    part = extract_photos(
                        d,
                        sub_out,
                        mode=str(mode),
                        recursive=self._recursive.isChecked(),
                    )
                    total.copied.extend(part.copied)
                    total.failed.extend(part.failed)
                    self._progress.setValue(int(100 * i / max(1, len(dirs))))
                result = total
            else:
                self._progress.setValue(40)
                result = extract_photos(
                    folder,
                    out,
                    mode=str(mode),
                    recursive=self._recursive.isChecked(),
                )
                self._progress.setValue(100)
            self._progress.setValue(100)
            self._result.setText(result.summary)
            level = StatusLevel.SUCCESS if not result.failed else StatusLevel.WARNING
            self.report_status(f"提取 {len(result.copied)} 项", level=level)
            show_saved(self, result.summary, result.output_path)

        self.run_safe(_run, title="提取失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("照片提取")
