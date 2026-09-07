# -*- coding: utf-8 -*-
"""通用加水印页：文字/Logo、颜色、旋转、字号；参数即时预览。"""
from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_saved, show_warning
from modules.image_watermark.image_watermark_service import (
    WatermarkOptions,
    apply_text_watermark,
    ensure_pillow,
    watermark_batch,
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
    SecondaryButton,
    SpinBox,
)


def _fit_pixmap(source: QPixmap, target_w: int, target_h: int, *, dpr: float) -> QPixmap:
    if source.isNull() or target_w < 8 or target_h < 8:
        return QPixmap()
    dpr = max(1.0, float(dpr or 1.0))
    phys_w = max(1, int(round(target_w * dpr)))
    phys_h = max(1, int(round(target_h * dpr)))
    scaled = source.scaled(
        phys_w,
        phys_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


class FitPixmapLabel(QLabel):
    """控件库例外：水印预览画布，随窗口放大并保持清晰。"""

    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        self._source: QPixmap | None = None
        self._placeholder = placeholder
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # 控件库例外：预览画布需随主题 palette 描边，勿走业务硬编码色
        self.setStyleSheet("background: palette(dark); border: 1px solid palette(mid);")
        self.setText(placeholder)

    def set_source_pixmap(self, pm: QPixmap | None) -> None:
        if pm is None or pm.isNull():
            self._source = None
            self.clear()
            self.setText(self._placeholder)
            return
        self._source = pm
        self._rebuild()

    def clear_preview(self, text: str | None = None) -> None:
        self._source = None
        self.clear()
        self.setText(text if text is not None else self._placeholder)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source is not None:
            self._rebuild()

    def _rebuild(self) -> None:
        if self._source is None:
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        scaled = _fit_pixmap(self._source, self.width() - 8, self.height() - 8, dpr=dpr)
        if scaled.isNull():
            return
        self.setPixmap(scaled)
        self.setText("")


class ImageWatermarkPage(BasePage):
    page_id = "image_watermark"
    page_title = "添加图片水印"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._refresh_preview)

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(8)

        outer.addWidget(
            PageHeader(
                "添加图片水印",
                "文字或 Logo：调色 / 旋转 / 字号即时预览，再批量叠加。",
            )
        )

        body = QHBoxLayout()
        body.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(8)

        path_box = FormSection("源")
        row = QHBoxLayout()
        self._path = LineEdit()
        self._path.setPlaceholderText("图片文件或文件夹路径…")
        row.addWidget(self._path, 1)
        btn_file = SecondaryButton("选文件…")
        btn_file.clicked.connect(self._pick_file)
        row.addWidget(btn_file)
        btn_dir = SecondaryButton("选文件夹…")
        btn_dir.clicked.connect(self._pick_dir)
        row.addWidget(btn_dir)
        path_box.add_layout(row)
        self._recursive = CheckBox("包含子文件夹")
        self._recursive.setChecked(True)
        path_box.add_widget(self._recursive)
        left.addWidget(path_box)

        wm = FormSection("水印与属性")
        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._text = LineEdit()
        self._text.setText("TOA")
        self._text.setPlaceholderText("水印文字（可选，若已选 Logo）")
        self._text.textChanged.connect(self._schedule_preview)
        form.addRow("文字", self._text)

        logo_row = QHBoxLayout()
        self._logo = LineEdit()
        self._logo.setPlaceholderText("可选 Logo 路径…")
        self._logo.textChanged.connect(self._schedule_preview)
        logo_row.addWidget(self._logo, 1)
        btn_logo = SecondaryButton("选 Logo…")
        btn_logo.clicked.connect(self._pick_logo)
        logo_row.addWidget(btn_logo)
        btn_clear_logo = SecondaryButton("清除")
        btn_clear_logo.clicked.connect(lambda: self._logo.clear())
        logo_row.addWidget(btn_clear_logo)
        form.addRow("Logo", logo_row)

        self._opacity = SpinBox()
        self._opacity.setRange(5, 100)
        self._opacity.setValue(40)
        self._opacity.setSuffix(" %")
        self._opacity.setToolTip("不透明度")
        self._opacity.valueChanged.connect(self._schedule_preview)
        form.addRow("不透明度", self._opacity)

        self._font_size = SpinBox()
        self._font_size.setRange(0, 200)
        self._font_size.setValue(0)
        self._font_size.setSpecialValueText("自适应")
        self._font_size.setSuffix(" px")
        self._font_size.valueChanged.connect(self._schedule_preview)
        form.addRow("字号", self._font_size)

        self._color = ComboBox()
        for label, data in (
            ("白色", "white"),
            ("黑色", "black"),
            ("红色", "red"),
            ("蓝色", "blue"),
            ("黄色", "yellow"),
            ("灰色", "gray"),
        ):
            self._color.addItem(label, data)
        self._color.setMinimumWidth(120)
        self._color.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("颜色", self._color)

        self._rotation = SpinBox()
        self._rotation.setRange(-180, 180)
        self._rotation.setValue(0)
        self._rotation.setSuffix(" °")
        self._rotation.valueChanged.connect(self._schedule_preview)
        form.addRow("旋转", self._rotation)

        self._pos = ComboBox()
        for label, data in (
            ("居中", "center"),
            ("左上", "top-left"),
            ("右上", "top-right"),
            ("左下", "bottom-left"),
            ("右下", "bottom-right"),
            ("平铺", "tile"),
        ):
            self._pos.addItem(label, data)
        self._pos.setCurrentIndex(4)
        self._pos.setMinimumWidth(120)
        self._pos.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("位置", self._pos)

        self._logo_scale = SpinBox()
        self._logo_scale.setRange(5, 60)
        self._logo_scale.setValue(18)
        self._logo_scale.setSuffix(" % 宽")
        self._logo_scale.setToolTip("Logo 相对图片宽度")
        self._logo_scale.valueChanged.connect(self._schedule_preview)
        form.addRow("Logo 大小", self._logo_scale)

        wm.add_widget(form_host)
        left.addWidget(wm)

        actions = QHBoxLayout()
        btn = PrimaryButton("批量加水印")
        btn.clicked.connect(self._on_run)
        actions.addWidget(btn)
        btn_out = SecondaryButton("打开输出目录")
        btn_out.clicked.connect(self._open_out)
        actions.addWidget(btn_out)
        actions.addStretch(1)
        left.addLayout(actions)
        self._result = HintLabel("选单张图片可看右侧预览；文件夹则直接批量。")
        left.addWidget(self._result)
        left.addStretch(1)
        body.addLayout(left, 2)

        prev = FormSection("预览（单图）")
        self._preview = FitPixmapLabel("选择单张图片后显示预览")
        prev.add_widget(self._preview, 1)
        body.addWidget(prev, 3)

        outer.addLayout(body, 1)

    def _opts(self) -> WatermarkOptions:
        return WatermarkOptions(
            text=self._text.text().strip(),
            opacity=self._opacity.value(),
            position=self._pos.currentData() or "bottom-right",
            font_size=self._font_size.value(),
            color=self._color.currentData() or "white",
            rotation=self._rotation.value(),
            logo_path=self._logo.text().strip(),
            logo_scale=self._logo_scale.value(),
        )

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)",
        )
        if path:
            self._path.setText(path)
            self._schedule_preview()

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if path:
            self._path.setText(path)
            self._preview.clear_preview("文件夹模式：预览请先选单张图片")

    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Logo",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self._logo.setText(path)
            self._schedule_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _preview_target_px(self) -> tuple[int, int]:
        dpr = float(self._preview.devicePixelRatioF() or 1.0)
        tw = max(480, int(round(max(360, self._preview.width()) * dpr)))
        th = max(480, int(round(max(360, self._preview.height()) * dpr)))
        return tw, th

    def _refresh_preview(self) -> None:
        src = self._path.text().strip()
        p = Path(src)
        if not p.is_file():
            return
        ok, _msg = ensure_pillow()
        if not ok:
            return
        opts = self._opts()
        if not opts.text and not opts.logo_path:
            self._preview.clear_preview("请填写文字或选择 Logo")
            return

        tw, th = self._preview_target_px()

        def _run() -> None:
            from PIL import Image as PILImage

            img = apply_text_watermark(src, opts)
            w, h = img.size
            # 按预览区物理像素生成，避免先压到 480 再放大发糊
            scale = min(tw / float(w), th / float(h), 1.0)
            if scale < 0.999:
                img = img.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    PILImage.Resampling.LANCZOS,
                )
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img.close()
            pm = QPixmap()
            pm.loadFromData(buf.getvalue(), "PNG")
            self._preview.set_source_pixmap(pm)
            self.report_status(f"水印预览 {p.name}")

        self.run_safe(_run, title="预览失败")

    def _on_run(self) -> None:
        src = self._path.text().strip()
        if not src:
            show_warning(self, "请先选择图片或文件夹。")
            return
        p = Path(src)
        if not p.exists():
            show_warning(self, "路径不存在。")
            return
        ok, msg = ensure_pillow()
        if not ok:
            show_warning(self, msg)
            return
        opts = self._opts()
        if not opts.text and not opts.logo_path:
            show_warning(self, "请填写水印文字或选择 Logo。")
            return

        def _run() -> None:
            out = module_output_dir(self.page_id, create=True)
            n_ok, n_fail, _failed, out_str = watermark_batch(
                src,
                out,
                opts,
                recursive=self._recursive.isChecked(),
            )
            self._result.setText(f"完成：成功 {n_ok}，失败 {n_fail}。\n输出：{out_str}")
            level = StatusLevel.SUCCESS if n_fail == 0 else StatusLevel.WARNING
            self.report_status(f"水印 {n_ok}/{n_ok + n_fail}", level=level)
            show_saved(self, f"成功 {n_ok}，失败 {n_fail}\n{out_str}", out_str)

        self.run_safe(_run, title="加水印失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("添加图片水印")
        if Path(self._path.text().strip()).is_file():
            self._schedule_preview()
