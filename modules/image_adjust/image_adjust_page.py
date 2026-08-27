# -*- coding: utf-8 -*-
"""图片调整页：参数旁即时预览。"""
from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.image_adjust.image_adjust_service import (
    AdjustOptions,
    apply_adjust,
    ensure_pillow,
    save_adjusted,
)
from services.storage_paths import module_output_dir
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SpinBox,
)


class ImageAdjustPage(BasePage):
    page_id = "image_adjust"
    page_title = "图片调整"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(220)
        self._preview_timer.timeout.connect(self._refresh_preview)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "调整图片",
                "旋转、翻转、缩放与亮度/对比度；右侧即时预览，确认后再保存。",
            )
        )

        body = QHBoxLayout()
        left = QVBoxLayout()

        path_box = FormSection("源图片")
        row = QHBoxLayout()
        self._path = LineEdit()
        self._path.setPlaceholderText("选择图片文件…")
        row.addWidget(self._path, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        path_box.add_layout(row)
        left.addWidget(path_box)

        geo = FormSection("几何")
        self._rotate = ComboBox()
        for deg, label in ((0, "不旋转"), (90, "旋转 90°"), (180, "旋转 180°"), (270, "旋转 270°")):
            self._rotate.addItem(label, deg)
        self._rotate.currentIndexChanged.connect(self._schedule_preview)
        geo.add_widget(HintLabel("旋转"))
        geo.add_widget(self._rotate)
        flips = QHBoxLayout()
        self._flip_h = CheckBox("水平翻转")
        self._flip_v = CheckBox("垂直翻转")
        self._flip_h.toggled.connect(self._schedule_preview)
        self._flip_v.toggled.connect(self._schedule_preview)
        flips.addWidget(self._flip_h)
        flips.addWidget(self._flip_v)
        flips.addStretch(1)
        geo.add_layout(flips)
        sz = QHBoxLayout()
        self._rw = SpinBox()
        self._rw.setRange(0, 20000)
        self._rw.setValue(0)
        self._rw.setSuffix(" 宽(0=原)")
        self._rh = SpinBox()
        self._rh.setRange(0, 20000)
        self._rh.setValue(0)
        self._rh.setSuffix(" 高(0=原)")
        self._rw.valueChanged.connect(self._schedule_preview)
        self._rh.valueChanged.connect(self._schedule_preview)
        sz.addWidget(self._rw)
        sz.addWidget(self._rh)
        sz.addStretch(1)
        geo.add_layout(sz)
        left.addWidget(geo)

        tone = FormSection("影调")
        row_t = QHBoxLayout()
        self._bright = SpinBox()
        self._bright.setRange(10, 300)
        self._bright.setValue(100)
        self._bright.setSuffix(" % 亮度")
        self._contrast = SpinBox()
        self._contrast.setRange(10, 300)
        self._contrast.setValue(100)
        self._contrast.setSuffix(" % 对比度")
        self._bright.valueChanged.connect(self._schedule_preview)
        self._contrast.valueChanged.connect(self._schedule_preview)
        row_t.addWidget(self._bright)
        row_t.addWidget(self._contrast)
        row_t.addStretch(1)
        tone.add_layout(row_t)
        left.addWidget(tone)

        actions = QHBoxLayout()
        btn_save = PrimaryButton("保存到输出")
        btn_save.clicked.connect(self._on_save)
        actions.addWidget(btn_save)
        btn_out = SecondaryButton("打开输出目录")
        btn_out.clicked.connect(self._open_out)
        actions.addWidget(btn_out)
        actions.addStretch(1)
        left.addLayout(actions)
        self._result = HintLabel("就绪。")
        left.addWidget(self._result)
        left.addStretch(1)
        body.addLayout(left, 1)

        prev = FormSection("预览")
        # 控件库例外：调整结果实时预览
        self._preview = QLabel("选择图片后显示预览")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(360, 360)
        prev.add_widget(self._preview)
        body.addWidget(prev, 1)

        scroll.add_layout(body)
        scroll.add_stretch(1)

    def _options(self) -> AdjustOptions:
        return AdjustOptions(
            rotate=int(self._rotate.currentData() or 0),
            flip_h=self._flip_h.isChecked(),
            flip_v=self._flip_v.isChecked(),
            resize_w=self._rw.value(),
            resize_h=self._rh.value(),
            brightness=self._bright.value() / 100.0,
            contrast=self._contrast.value() / 100.0,
        )

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)",
        )
        if path:
            self._path.setText(path)
            self._schedule_preview()

    def _require_src(self) -> str | None:
        src = self._path.text().strip()
        if not src:
            show_warning(self, "请先选择图片。")
            return None
        if not Path(src).is_file():
            show_warning(self, "文件不存在。")
            return None
        ok, msg = ensure_pillow()
        if not ok:
            show_warning(self, msg)
            return None
        return src

    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _refresh_preview(self) -> None:
        src = self._path.text().strip()
        if not src or not Path(src).is_file():
            return
        ok, msg = ensure_pillow()
        if not ok:
            return

        def _run() -> None:
            from PIL import Image as PILImage

            img = apply_adjust(src, self._options())
            w, h = img.size
            max_side = 480
            if max(w, h) > max_side:
                scale = max_side / float(max(w, h))
                img = img.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    PILImage.Resampling.LANCZOS,
                )
            buf = io.BytesIO()
            if img.mode == "RGBA":
                bg = PILImage.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                bg.save(buf, format="PNG")
                bg.close()
            else:
                img.convert("RGB").save(buf, format="PNG")
            img.close()
            pm = QPixmap()
            pm.loadFromData(buf.getvalue(), "PNG")
            self._preview.setPixmap(pm)
            self.report_status(f"预览 {Path(src).name}")

        self.run_safe(_run, title="预览失败")

    def _on_save(self) -> None:
        src = self._require_src()
        if not src:
            return

        def _run() -> None:
            out = module_output_dir(self.page_id, create=True)
            path = save_adjusted(src, out, self._options())
            self._result.setText(f"已保存：\n{path}")
            self.report_status("调整图已保存", level=StatusLevel.SUCCESS)
            show_saved(self, f"已保存\n{path}", path)

        self.run_safe(_run, title="保存失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("图片调整")
        if self._path.text().strip():
            self._schedule_preview()
