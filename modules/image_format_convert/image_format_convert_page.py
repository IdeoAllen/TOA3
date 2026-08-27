# -*- coding: utf-8 -*-
"""图片格式转换：列表 + 预览 + 进度。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.image_format_convert.image_format_convert_service import (
    collect_images,
    convert_batch,
    ensure_pillow,
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
    SpinBox,
)


class ImageFormatConvertPage(BasePage):
    page_id = "image_format_convert"
    page_title = "图片格式转换"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._files: list[str] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "图转文件",
                "办公常用：微信压缩 / 邮件适中 / 归档无损 → 批量转 PNG·JPG·WEBP·PDF。",
            )
        )

        path_box = FormSection("源")
        row = QHBoxLayout()
        self._path = LineEdit()
        self._path.setPlaceholderText("文件夹路径…")
        row.addWidget(self._path, 1)
        btn_files = SecondaryButton("选文件…")
        btn_files.clicked.connect(self._pick_files)
        row.addWidget(btn_files)
        btn_dir = SecondaryButton("选文件夹…")
        btn_dir.clicked.connect(self._pick_dir)
        row.addWidget(btn_dir)
        path_box.add_layout(row)
        self._recursive = CheckBox("文件夹含递归")
        self._recursive.setChecked(True)
        path_box.add_widget(self._recursive)
        scroll.add_widget(path_box)

        mid = QHBoxLayout()
        list_box = FormSection("文件列表")
        self._list = ListWidget()
        self._list.setMinimumHeight(220)
        self._list.currentRowChanged.connect(self._show_thumb)
        list_box.add_widget(self._list)
        mid.addWidget(list_box, 1)

        prev = FormSection("预览")
        # 控件库例外：格式转换缩略图
        self._preview = QLabel("选择列表项预览")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(280, 220)
        prev.add_widget(self._preview)
        mid.addWidget(prev, 1)
        scroll.add_layout(mid)

        opt = FormSection("目标格式 · 办公预设")
        preset_row = QHBoxLayout()
        for label, fmt, quality in (
            ("微信图", "JPG", 72),
            ("邮件附件", "JPG", 85),
            ("归档原图", "PNG", 90),
            ("高清 JPG", "JPG", 95),
        ):
            btn = SecondaryButton(label)
            btn.clicked.connect(
                lambda _=False, f=fmt, q=quality: self._apply_preset(f, q)
            )
            preset_row.addWidget(btn)
        preset_row.addStretch(1)
        opt.add_layout(preset_row)
        self._fmt = ComboBox()
        for f in ("PNG", "JPG", "WEBP", "PDF"):
            self._fmt.addItem(f, f)
        self._fmt.currentIndexChanged.connect(self._sync_quality)
        opt.add_widget(self._fmt)
        self._quality = SpinBox()
        self._quality.setRange(1, 100)
        self._quality.setValue(90)
        self._quality.setSuffix(" JPEG/WEBP 质量")
        opt.add_widget(self._quality)
        scroll.add_widget(opt)

        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        scroll.add_widget(self._progress)

        actions = QHBoxLayout()
        btn = PrimaryButton("开始转换")
        btn.clicked.connect(self._on_run)
        actions.addWidget(btn)
        btn_out = SecondaryButton("打开输出目录")
        btn_out.clicked.connect(self._open_out)
        actions.addWidget(btn_out)
        actions.addStretch(1)
        scroll.add_layout(actions)

        self._result = HintLabel("输出写入本模块 output 目录。")
        scroll.add_widget(self._result)
        scroll.add_stretch(1)
        self._sync_quality()

    def _apply_preset(self, fmt: str, quality: int) -> None:
        idx = self._fmt.findData(fmt)
        if idx >= 0:
            self._fmt.setCurrentIndex(idx)
        self._quality.setValue(int(quality))
        self._result.setText(f"已选预设：{fmt} · 质量 {quality}")

    def _sync_quality(self) -> None:
        fmt = self._fmt.currentData() or "PNG"
        self._quality.setEnabled(fmt in ("JPG", "WEBP", "PDF"))

    def _reload_list(self, sources: list[str]) -> None:
        self._files = collect_images(sources, recursive=self._recursive.isChecked())
        self._list.clear()
        for p in self._files:
            self._list.addItem(Path(p).name)
        self._result.setText(f"共 {len(self._files)} 个文件。")
        if self._files:
            self._list.setCurrentRow(0)

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif)",
        )
        if files:
            if not self._path.text().strip():
                self._path.setText(str(Path(files[0]).parent))
            self._reload_list(files)

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if path:
            self._path.setText(path)
            self._reload_list([path])

    def _show_thumb(self, row: int) -> None:
        if row < 0 or row >= len(self._files):
            return
        pm = QPixmap(self._files[row])
        if pm.isNull():
            self._preview.setText("无法预览")
            return
        self._preview.setPixmap(
            pm.scaled(
                280,
                220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _on_run(self) -> None:
        ok, msg = ensure_pillow()
        if not ok:
            show_warning(self, msg)
            return
        if not self._files:
            folder = self._path.text().strip()
            if folder:
                self._reload_list([folder])
        if not self._files:
            show_warning(self, "请选择文件或文件夹。")
            return

        def _run() -> None:
            out = module_output_dir(self.page_id, create=True)
            fmt = self._fmt.currentData() or "PNG"
            self._progress.setValue(15)
            n_ok, n_fail, _failed, out_str = convert_batch(
                self._files,
                out,
                fmt,
                quality=self._quality.value(),
                recursive=False,
            )
            self._progress.setValue(100)
            self._result.setText(f"完成：成功 {n_ok}，失败 {n_fail}。\n输出：{out_str}")
            level = StatusLevel.SUCCESS if n_fail == 0 else StatusLevel.WARNING
            self.report_status(f"转换 {n_ok} 成功 / {n_fail} 失败", level=level)
            show_saved(self, f"成功 {n_ok}，失败 {n_fail}\n{out_str}", out_str)

        self.run_safe(_run, title="转换失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("图片格式转换")
