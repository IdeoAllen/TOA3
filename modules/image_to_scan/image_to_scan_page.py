# -*- coding: utf-8 -*-
"""图片转扫描件页：列表 + 实时预览 + 批量 PDF。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_saved, show_warning
from modules.image_to_scan.image_to_scan_service import (
    DEFAULT_SETTINGS,
    ImageToScanProcessor,
    ScanSettings,
    batch_convert_folder,
    collect_images,
)
from services.storage_paths import module_output_dir
from widgets import (
    CheckBox,
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    SpinBox,
)


def _pil_to_qpixmap(pil_img) -> QPixmap:
    import io

    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="PNG")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue(), "PNG")
    return pm


def _param_cell(label: str, spin: SpinBox) -> QVBoxLayout:
    """标签在上、数字框在下，保证文字完整显示。"""
    col = QVBoxLayout()
    col.setSpacing(4)
    tip = HintLabel(label)
    tip.setWordWrap(False)
    col.addWidget(tip)
    spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    col.addWidget(spin)
    return col


class ImageToScanPage(BasePage):
    page_id = "image_to_scan"
    page_title = "图片转扫描件"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._images: list[str] = []
        self._proc = ImageToScanProcessor()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(280)
        self._preview_timer.timeout.connect(self._refresh_preview)

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(10)

        outer.addWidget(
            PageHeader(
                "图片转扫描件",
                "选文件夹并调参看预览，再批量输出清晰灰度 PDF。",
            )
        )

        # —— 源文件夹 + 扫描参数放同一区 ——
        top = FormSection("源文件夹与扫描参数")
        row = QHBoxLayout()
        row.setSpacing(8)
        self._folder = LineEdit()
        self._folder.setPlaceholderText("选择或粘贴图片文件夹…")
        row.addWidget(self._folder, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        btn_load = SecondaryButton("载入列表")
        btn_load.clicked.connect(self._load_list)
        row.addWidget(btn_load)
        top.add_layout(row)

        opts = QHBoxLayout()
        opts.setSpacing(16)
        self._recursive = CheckBox("包含子文件夹")
        self._recursive.setChecked(True)
        opts.addWidget(self._recursive)

        self._shadow = SpinBox()
        self._shadow.setRange(0, 100)
        self._shadow.setValue(DEFAULT_SETTINGS.shadow_remove)
        self._shadow.valueChanged.connect(self._schedule_preview)
        opts.addLayout(_param_cell("去阴影 (0–100)", self._shadow))

        self._clarity = SpinBox()
        self._clarity.setRange(0, 100)
        self._clarity.setValue(DEFAULT_SETTINGS.clarity)
        self._clarity.valueChanged.connect(self._schedule_preview)
        opts.addLayout(_param_cell("清晰度 (0–100)", self._clarity))

        self._bw = SpinBox()
        self._bw.setRange(0, 100)
        self._bw.setValue(DEFAULT_SETTINGS.bw_level)
        self._bw.valueChanged.connect(self._schedule_preview)
        opts.addLayout(_param_cell("黑白强度 (0–100)", self._bw))

        opts.addStretch(1)
        top.add_layout(opts)
        top.add_widget(HintLabel("调参后自动刷新预览；默认清晰灰度，黑白强度过高易伤细节。"))
        outer.addWidget(top)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        list_box = FormSection("图片列表")
        self._list = ListWidget()
        self._list.setMinimumHeight(240)
        self._list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._list.currentRowChanged.connect(lambda _=None: self._schedule_preview())
        list_box.add_widget(self._list, stretch=1)
        list_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        mid.addWidget(list_box, 1)

        prev_box = FormSection("效果预览")
        # 控件库例外：扫描件实时预览
        self._preview = QLabel("选择左侧图片查看扫描效果")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(280)
        self._preview.setMinimumWidth(320)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        prev_box.add_widget(self._preview, stretch=1)
        prev_box.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        mid.addWidget(prev_box, 1)
        outer.addLayout(mid, 1)

        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        outer.addWidget(self._progress)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_run = PrimaryButton("批量转为 PDF")
        btn_run.clicked.connect(self._on_run)
        actions.addWidget(btn_run)
        btn_open = SecondaryButton("打开输出目录")
        btn_open.clicked.connect(self._open_out)
        actions.addWidget(btn_open)
        actions.addStretch(1)
        outer.addLayout(actions)

        self._result = HintLabel("输出写入本模块 output 目录。")
        outer.addWidget(self._result)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._folder

    def _settings(self) -> ScanSettings:
        return ScanSettings(
            shadow_remove=self._shadow.value(),
            clarity=self._clarity.value(),
            bw_level=self._bw.value(),
            remove_black_blocks=True,
        ).clamped()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if path:
            self._folder.setText(path)
            self._load_list()

    def _load_list(self) -> None:
        folder = self._folder.text().strip()
        if not folder:
            show_warning(self, "请先选择源文件夹。")
            return
        self._images = collect_images(folder, recursive=self._recursive.isChecked())
        self._list.clear()
        for p in self._images:
            self._list.addItem(Path(p).name)
        self._result.setText(f"共 {len(self._images)} 张图片。")
        if self._images:
            self._list.setCurrentRow(0)
            self._schedule_preview()
        else:
            self._preview.setText("目录内未找到图片")
            self._preview.setPixmap(QPixmap())

    def _schedule_preview(self) -> None:
        self._preview_timer.start()

    def _refresh_preview(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._images):
            return
        src = self._images[row]

        def _run() -> None:
            pil, _ = self._proc.preview_fast(src, max_side=1200, settings=self._settings())
            if pil is None:
                self._preview.setText("预览失败")
                return
            w, h = pil.size
            max_show = 480
            if max(w, h) > max_show:
                scale = max_show / float(max(w, h))
                from PIL import Image as PILImage

                pil = pil.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    PILImage.Resampling.LANCZOS,
                )
            self._preview.setPixmap(_pil_to_qpixmap(pil))
            self.report_status(f"预览：{Path(src).name}")

        self.run_safe(_run, title="预览失败")

    def _on_run(self) -> None:
        folder = self._folder.text().strip()
        if not folder:
            show_warning(self, "请先选择源文件夹。")
            return
        if not self._images:
            self._load_list()
        if not self._images:
            show_warning(self, "目录内未找到图片。")
            return

        def _run() -> None:
            out = module_output_dir(self.page_id, create=True)
            total = len(self._images)

            def _prog(i: int, n: int, _path: str) -> None:
                self._progress.setValue(int(100 * i / max(1, n)))

            ok, fail_n, _failed, out_str = batch_convert_folder(
                folder,
                out,
                settings=self._settings(),
                recursive=self._recursive.isChecked(),
                progress_callback=_prog,
            )
            self._progress.setValue(100)
            self._result.setText(f"完成：成功 {ok}，失败 {fail_n}。\n输出：{out_str}")
            level = StatusLevel.SUCCESS if fail_n == 0 else StatusLevel.WARNING
            self.report_status(f"扫描件 {ok}/{total}", level=level)
            show_saved(self, f"成功 {ok}，失败 {fail_n}\n{out_str}", out_str)

        self.run_safe(_run, title="转换失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("图片转扫描件")
        self.schedule_primary_focus()
