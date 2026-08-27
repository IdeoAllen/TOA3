# -*- coding: utf-8 -*-
"""图片转文字：以「截图直出」为主，选图为辅。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from core.base_page import BasePage
from core.exceptions import IntegrationError
from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning
from widgets import (
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)


class OcrToolPage(BasePage):
    page_id = "ocr_tool"
    page_title = "图片转文字"

    _last_text: str = ""
    _last_path: str = ""

    @classmethod
    def stash_last_result(cls, text: str, *, path: str = "") -> None:
        cls._last_text = text or ""
        cls._last_path = path or ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "图片转文字",
                "框选屏幕区域 → 立刻出字并复制。快捷键 Alt+O（全局）。",
            )
        )
        scroll.add_widget(
            SemanticLabel(
                "主路径：截图直出文字；也可选本地图片。识别完成请点「复制结果」。",
                kind="info",
            )
        )
        scroll.add_widget(
            HintLabel(
                "主流程是截图直采，不必先存文件再识别。"
                "本机无 chi_sim 时英文较准；装中文语言包后改 integrations.yml 的 lang。"
            )
        )

        primary = FormSection("截图转文字")
        row = QHBoxLayout()
        btn_region = PrimaryButton("框选截图转文字")
        btn_region.clicked.connect(lambda: self._shot_ocr(full=False))
        row.addWidget(btn_region)
        btn_full = SecondaryButton("全屏截图转文字")
        btn_full.clicked.connect(lambda: self._shot_ocr(full=True))
        row.addWidget(btn_full)
        btn_clip = SecondaryButton("识别剪贴板图片")
        btn_clip.clicked.connect(self._ocr_clipboard_image)
        row.addWidget(btn_clip)
        row.addStretch(1)
        primary.add_layout(row)
        scroll.add_widget(primary)

        # 控件库例外：截图缩略预览
        prev = FormSection("最近截图")
        self._thumb = QLabel("尚未截图")
        self._thumb.setMinimumHeight(120)
        self._thumb.setMaximumHeight(180)
        self._thumb.setScaledContents(False)
        prev.add_widget(self._thumb)
        scroll.add_widget(prev)

        box = FormSection("或从文件识别")
        path_row = QHBoxLayout()
        self._path = LineEdit()
        self._path.setPlaceholderText("可选：浏览本地图片…")
        path_row.addWidget(self._path, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        btn_file = SecondaryButton("识别文件")
        btn_file.clicked.connect(self._on_recognize_file)
        path_row.addWidget(btn_file)
        box.add_layout(path_row)
        scroll.add_widget(box)

        actions = QHBoxLayout()
        btn_copy = PrimaryButton("复制结果")
        btn_copy.clicked.connect(self._on_copy)
        actions.addWidget(btn_copy)
        btn_agent = SecondaryButton("送到智能体")
        btn_agent.setToolTip("将识别结果送入 Harness 编码智能体")
        btn_agent.clicked.connect(self._send_to_harness)
        actions.addWidget(btn_agent)
        actions.addStretch(1)
        scroll.add_layout(actions)

        out = FormSection("识别结果")
        self._text = PlainTextEdit()
        self._text.setMinimumHeight(220)
        self._text.setPlaceholderText("截图或识别后，文字会出现在这里…")
        out.add_widget(self._text)
        scroll.add_widget(out)
        scroll.add_stretch(1)

        if OcrToolPage._last_text:
            self._text.setPlainText(OcrToolPage._last_text)
        if OcrToolPage._last_path:
            self._show_thumb(OcrToolPage._last_path)

    def _show_thumb(self, path: str) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        p = Path(path)
        if not p.is_file():
            return
        pix = QPixmap(str(p))
        if pix.isNull():
            return
        self._thumb.setPixmap(
            pix.scaled(
                480,
                160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._path.setText(str(p))

    def _shot_ocr(self, *, full: bool) -> None:
        from services.screenshot_service import run_screenshot_ocr

        text = run_screenshot_ocr(self, full=full)
        if text is None and not OcrToolPage._last_path:
            return
        self._text.setPlainText(OcrToolPage._last_text or (text or ""))
        if OcrToolPage._last_path:
            self._show_thumb(OcrToolPage._last_path)
        if text:
            self.report_status(f"已识别并复制 {len(text)} 字", level=StatusLevel.SUCCESS)

    def _ocr_clipboard_image(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is None:
            return
        pix = cb.pixmap()
        if pix is None or pix.isNull():
            show_warning(self, "剪贴板里没有图片。可先截图或复制图片后再试。")
            return

        def _run() -> None:
            from services.integrations import get_client
            from services.screenshot_service import save_screenshot_pixmap

            path = save_screenshot_pixmap(pix, module_id="ocr_tool")
            client = get_client("ocr")
            result = client.recognize_pixmap(pix)
            text = str(result.get("text") or "")
            OcrToolPage.stash_last_result(text, path=str(path))
            self._text.setPlainText(text)
            self._show_thumb(str(path))
            if text.strip():
                cb.setText(text)
                self.report_status("剪贴板图片已识别并复制文字", level=StatusLevel.SUCCESS)
            else:
                show_info(self, "识别完成，但未提取到文字。")

        try:
            self.run_safe(_run, title="OCR 失败")
        except IntegrationError as exc:
            show_warning(self, exc.user_message)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;所有文件 (*.*)",
        )
        if path:
            self._path.setText(path)

    def _on_recognize_file(self) -> None:
        src = self._path.text().strip()
        if not src:
            show_warning(self, "请先选择图片，或直接用「框选截图转文字」。")
            return
        if not Path(src).is_file():
            show_warning(self, "文件不存在。")
            return

        def _run() -> None:
            from services.integrations import get_client

            client = get_client("ocr")
            result = client.recognize_image(src)
            text = str(result.get("text") or "")
            OcrToolPage.stash_last_result(text, path=src)
            self._text.setPlainText(text)
            self._show_thumb(src)
            engine = result.get("engine") or result.get("provider") or "ocr"
            self.report_status(f"OCR 完成（{engine}）", level=StatusLevel.SUCCESS)
            if not text.strip():
                show_info(self, "识别完成，但未提取到文字。")

        try:
            self.run_safe(_run, title="OCR 失败")
        except IntegrationError as exc:
            show_warning(self, exc.user_message)

    def _on_copy(self) -> None:
        text = self._text.toPlainText()
        if not text.strip():
            show_warning(self, "没有可复制的内容。")
            return
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(text)
            self.report_status("已复制到剪贴板", level=StatusLevel.SUCCESS)
            show_info(self, "已复制识别结果。")

    def _send_to_harness(self) -> None:
        text = self._text.toPlainText().strip()
        if not text:
            show_warning(self, "没有可发送的识别结果。")
            return
        from services.harness_feed import navigate_to_harness

        win = self.window()
        if win is not None:
            navigate_to_harness(win, text, title="来自图片转文字", source="ocr_tool")
        self.report_status("已送入编码智能体", level=StatusLevel.SUCCESS)

    def on_enter(self) -> None:
        if OcrToolPage._last_text and not self._text.toPlainText().strip():
            self._text.setPlainText(OcrToolPage._last_text)
        if OcrToolPage._last_path:
            self._show_thumb(OcrToolPage._last_path)
        self.report_status("图片转文字 · Alt+O 框选直出")
