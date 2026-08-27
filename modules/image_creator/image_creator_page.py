# -*- coding: utf-8 -*-
"""创建空白图：尺寸/颜色即时预览。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.image_creator.image_creator_service import create_image, ensure_pillow, parse_hex_color
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


class ImageCreatorPage(BasePage):
    page_id = "image_creator"
    page_title = "创建空白图"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._update_swatch)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader("创建图片", "按尺寸与填充色生成纯色或噪点 PNG；右侧即时预览。（对齐办公底图场景）")
        )

        body = QHBoxLayout()
        left = QVBoxLayout()

        size = FormSection("尺寸")
        row = QHBoxLayout()
        self._w = SpinBox()
        self._w.setRange(1, 20000)
        self._w.setValue(1920)
        self._w.setSuffix(" 宽")
        self._w.valueChanged.connect(self._schedule)
        row.addWidget(self._w)
        self._h = SpinBox()
        self._h.setRange(1, 20000)
        self._h.setValue(1080)
        self._h.setSuffix(" 高")
        self._h.valueChanged.connect(self._schedule)
        row.addWidget(self._h)
        row.addStretch(1)
        size.add_layout(row)
        left.addWidget(size)

        fill = FormSection("填充")
        self._color = LineEdit()
        self._color.setText("#FFFFFF")
        self._color.setPlaceholderText("#RRGGBB")
        self._color.textChanged.connect(self._schedule)
        fill.add_widget(HintLabel("填充色"))
        fill.add_widget(self._color)
        self._mode = ComboBox()
        self._mode.addItem("纯色 solid", "solid")
        self._mode.addItem("噪点 noise", "noise")
        self._mode.currentIndexChanged.connect(self._schedule)
        fill.add_widget(HintLabel("模式"))
        fill.add_widget(self._mode)
        self._open_after = CheckBox("创建后打开文件")
        self._open_after.setChecked(False)
        fill.add_widget(self._open_after)
        left.addWidget(fill)

        actions = QHBoxLayout()
        btn = PrimaryButton("创建 PNG")
        btn.clicked.connect(self._on_create)
        actions.addWidget(btn)
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
        self._swatch = QLabel()
        self._swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._swatch.setMinimumSize(280, 200)
        # 控件库例外：色板预览边框（债务·Hold/非八件套）
        self._swatch.setStyleSheet("border: 1px solid palette(mid); border-radius: 8px;")
        prev.add_widget(self._swatch)
        self._dim = HintLabel("")
        prev.add_widget(self._dim)
        body.addWidget(prev, 1)

        scroll.add_layout(body)
        scroll.add_stretch(1)
        self._update_swatch()

    def _schedule(self) -> None:
        self._timer.start()

    def _update_swatch(self) -> None:
        try:
            r, g, b = parse_hex_color(self._color.text().strip() or "#FFFFFF")
        except Exception:
            r, g, b = 255, 255, 255
        mode = self._mode.currentData() or "solid"
        pm = QPixmap(280, 180)
        if mode == "noise":
            import random

            from PySide6.QtGui import QImage

            img = QImage(140, 90, QImage.Format.Format_RGB32)
            for y in range(90):
                for x in range(140):
                    j = random.randint(-28, 28)
                    img.setPixelColor(
                        x,
                        y,
                        QColor(max(0, min(255, r + j)), max(0, min(255, g + j)), max(0, min(255, b + j))),
                    )
            pm = QPixmap.fromImage(img).scaled(
                280,
                180,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        else:
            pm.fill(QColor(r, g, b))
        self._swatch.setPixmap(pm)
        self._dim.setText(f"{self._w.value()} × {self._h.value()} · {self._color.text().strip() or '#FFFFFF'} · {mode}")

    def _on_create(self) -> None:
        ok, msg = ensure_pillow()
        if not ok:
            show_warning(self, msg)
            return

        def _run() -> None:
            out = module_output_dir(self.page_id, create=True)
            path = create_image(
                self._w.value(),
                self._h.value(),
                fill=self._color.text().strip() or "#FFFFFF",
                mode=self._mode.currentData() or "solid",
                output_dir=out,
            )
            self._result.setText(f"已创建：\n{path}")
            self.report_status("空白图已创建", level=StatusLevel.SUCCESS)
            show_saved(self, f"已保存\n{path}", path)
            if self._open_after.isChecked():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

        self.run_safe(_run, title="创建失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("创建空白图")
        self._update_swatch()
