# -*- coding: utf-8 -*-
"""文档合成器。"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.document_composer.document_composer_service import compose_from_images
from services.storage_paths import module_output_dir
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)


class DocumentComposerPage(BasePage):
    page_id = "document_composer"
    page_title = "文档合成器"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "文档合成器",
                "选择图片文件夹，合成 DOCX / PPTX；依赖缺失时回退为 ZIP+说明。",
            )
        )

        box = FormSection("图片文件夹")
        row = QHBoxLayout()
        self._folder = LineEdit()
        row.addWidget(self._folder, 1)
        btn = SecondaryButton("浏览…")
        btn.clicked.connect(self._browse)
        row.addWidget(btn)
        box.add_layout(row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(HintLabel("输出偏好"))
        self._prefer = ComboBox()
        self._prefer.addItems(["auto", "pdf", "docx", "pptx", "zip"])
        fmt_row.addWidget(self._prefer, 1)
        box.add_layout(fmt_row)
        box.add_widget(HintLabel("auto 优先 PDF（Pillow），其次 DOCX / PPTX，最后 ZIP。"))
        scroll.add_widget(box)

        file_box = FormSection("或直接多选图片")
        file_row = QHBoxLayout()
        self._files = LineEdit()
        self._files.setPlaceholderText("也可多选图片文件（分号分隔）")
        self._files.setReadOnly(True)
        file_row.addWidget(self._files, 1)
        btn_files = SecondaryButton("多选图片…")
        btn_files.clicked.connect(self._browse_files)
        file_row.addWidget(btn_files)
        file_box.add_layout(file_row)
        scroll.add_widget(file_box)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("合成")
        btn_go.clicked.connect(self._on_compose)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        scroll.add_layout(actions)

        out = FormSection("结果")
        self._log = ReadOnlyPlainTextEdit()
        out.add_widget(self._log)
        scroll.add_widget(out)
        scroll.add_stretch(1)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if path:
            self._folder.setText(path)
            self._files.clear()

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)",
        )
        if paths:
            self._files.setText(";".join(paths))
            self._folder.clear()

    def _on_compose(self) -> None:
        folder = self._folder.text().strip()
        files_raw = self._files.text().strip()
        if not folder and not files_raw:
            show_warning(self, "请选择图片文件夹或多选图片。")
            return

        def _run() -> None:
            from modules.document_composer.document_composer_service import compose_from_paths

            out_dir = module_output_dir(self.page_id, create=True)
            prefer = self._prefer.currentText()
            if files_raw:
                paths = [p.strip() for p in files_raw.split(";") if p.strip()]
                mode = prefer if prefer != "auto" else "pdf"
                result = compose_from_paths(paths, out_dir, prefer=mode)
            else:
                result = compose_from_images(folder, out_dir, prefer=prefer)
            msg = f"已生成：\n{result}"
            self._log.setPlainText(msg)
            self.report_status("合成完成", level=StatusLevel.SUCCESS)
            show_saved(self, msg, result)

        self.run_safe(_run, title="合成失败")

    def on_enter(self) -> None:
        self.report_status("文档合成器")
