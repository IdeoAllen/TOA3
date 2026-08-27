# -*- coding: utf-8 -*-
"""水印照片生成页：计划列表 + 实时预览 + 进度。"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.watermark_photo_generator.watermark_photo_service import (
    WatermarkProcessor,
    process_folder_to_output,
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
    ScrollPage,
    SecondaryButton,
)


class WatermarkPhotoGeneratorPage(BasePage):
    page_id = "watermark_photo_generator"
    page_title = "水印照片生成"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._proc = WatermarkProcessor()
        self._images: list[str] = []
        self._plan: dict[str, tuple[str, str]] = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(260)
        self._preview_timer.timeout.connect(self._refresh_preview)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "水印照片生成",
                "班级目录照片批量叠加「水印相机」风格时间 / 地点；左侧计划，右侧预览。",
            )
        )

        path_box = FormSection("源文件夹")
        row = QHBoxLayout()
        self._folder = LineEdit()
        self._folder.setPlaceholderText("选择班级照片根目录…")
        row.addWidget(self._folder, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        btn_load = SecondaryButton("载入计划")
        btn_load.clicked.connect(self._reload_plan)
        row.addWidget(btn_load)
        path_box.add_layout(row)
        path_box.add_widget(
            HintLabel("目录名含 YYYYMMDD-YYYYMMDD 时可自动推断起止；按子目录规则分配时段。")
        )
        scroll.add_widget(path_box)

        wm = FormSection("水印文案")
        self._text = LineEdit()
        self._text.setPlaceholderText("地点 / 水印文字，如：XX培训中心")
        self._text.textChanged.connect(self._schedule_preview)
        wm.add_widget(self._text)
        dates = QHBoxLayout()
        self._start = LineEdit()
        self._start.setPlaceholderText("开始日期 YYYY.MM.DD")
        self._start.textChanged.connect(lambda _=None: self._reload_plan())
        dates.addWidget(self._start)
        self._end = LineEdit()
        self._end.setPlaceholderText("结束日期 YYYY.MM.DD")
        self._end.textChanged.connect(lambda _=None: self._reload_plan())
        dates.addWidget(self._end)
        wm.add_layout(dates)
        scroll.add_widget(wm)

        mid = QHBoxLayout()
        list_box = FormSection("计划列表")
        self._list = ListWidget()
        self._list.setMinimumHeight(260)
        self._list.currentRowChanged.connect(lambda _=None: self._schedule_preview())
        list_box.add_widget(self._list)
        mid.addWidget(list_box, 1)

        prev_box = FormSection("水印预览")
        # 控件库例外：水印相机风格预览
        self._preview = QLabel("载入计划后点选左侧图片")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(340, 280)
        prev_box.add_widget(self._preview)
        mid.addWidget(prev_box, 1)
        scroll.add_layout(mid)

        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        scroll.add_widget(self._progress)

        actions = QHBoxLayout()
        self._overwrite = CheckBox("写回原图（TOA2 默认：覆盖班级目录内照片）")
        self._overwrite.setChecked(True)
        actions.addWidget(self._overwrite)
        btn_run = PrimaryButton("批量生成")
        btn_run.clicked.connect(self._on_run)
        actions.addWidget(btn_run)
        btn_open = SecondaryButton("打开输出目录")
        btn_open.clicked.connect(self._open_out)
        actions.addWidget(btn_open)
        actions.addStretch(1)
        scroll.add_layout(actions)

        self._result = HintLabel("默认写回原图；取消勾选则输出到本模块 output 目录。")
        scroll.add_widget(self._result)
        scroll.add_stretch(1)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择照片文件夹")
        if path:
            self._folder.setText(path)
            auto_s, auto_e = WatermarkProcessor.extract_dates_from_folder_name(path)
            if auto_s and not self._start.text().strip():
                self._start.setText(auto_s)
            if auto_e and not self._end.text().strip():
                self._end.setText(auto_e)
            self._reload_plan()

    def _parse_range(self) -> tuple[datetime, datetime] | None:
        s = self._start.text().strip()
        e = self._end.text().strip()
        start_dt = self._proc.parse_date(s) if s else None
        end_dt = self._proc.parse_date(e) if e else None
        if start_dt is None or end_dt is None:
            # 无日期时用今天～明天占位，仍可预览地点水印
            today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            from datetime import timedelta

            return today, today + timedelta(days=1)
        return start_dt, end_dt

    def _reload_plan(self) -> None:
        folder = self._folder.text().strip()
        if not folder or not Path(folder).is_dir():
            return
        self._images = self._proc.collect_images(folder)
        rng = self._parse_range()
        if rng is None:
            self._plan = {}
        else:
            self._plan = self._proc.plan_watermark_datetimes(folder, self._images, rng[0], rng[1])
        self._list.clear()
        for path in self._images:
            name = Path(path).name
            cat = self._proc.category_label(self._proc.classify_image(path, folder))
            dt = self._plan.get(path)
            stamp = f"{dt[0]} {dt[1]}" if dt else "—"
            self._list.addItem(f"{name}  ·  {cat}  ·  {stamp}")
        self._result.setText(f"共 {len(self._images)} 张；已规划 {len(self._plan)} 条时间。")
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
        path = self._images[row]
        loc = self._text.text().strip() or "培训中心"
        dt = self._plan.get(path)
        date_text = dt[0] if dt else self._start.text().strip()
        time_text = dt[1] if dt else None
        folder = self._folder.text().strip()

        def _run() -> None:
            pil = self._proc.generate_preview_image(
                path,
                date_text=date_text or "",
                location=loc,
                time_text=time_text,
                start_date=self._start.text().strip() or None,
                end_date=self._end.text().strip() or None,
                root_dir=folder or None,
                all_images=self._images,
                max_side=720,
            )
            if pil is None:
                self._preview.setText("预览失败")
                return
            buf = io.BytesIO()
            pil.convert("RGB").save(buf, format="PNG")
            pm = QPixmap()
            pm.loadFromData(buf.getvalue(), "PNG")
            # 适应显示区
            self._preview.setPixmap(
                pm.scaled(
                    420,
                    320,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.report_status(f"预览 {Path(path).name}")

        self.run_safe(_run, title="预览失败")

    def _on_run(self) -> None:
        folder = self._folder.text().strip()
        text = self._text.text().strip()
        if not folder:
            show_warning(self, "请先选择源文件夹。")
            return
        if not text:
            show_warning(self, "请填写地点 / 水印文字。")
            return
        if not self._images:
            self._reload_plan()
        if not self._images:
            show_warning(self, "目录内未找到图片。")
            return

        def _run() -> None:
            overwrite = self._overwrite.isChecked()
            start_s = self._start.text().strip()
            end_s = self._end.text().strip()
            if not start_s or not end_s:
                show_warning(self, "写回原图需填写有效起止日期（YYYY.MM.DD）。")
                return

            def _prog(i: int, n: int, _p: str) -> None:
                self._progress.setValue(int(100 * i / max(1, n)))

            if overwrite:
                ok, fail_n, _failed = self._proc.process_directory(
                    folder,
                    text,
                    start_s,
                    end_s,
                    progress_callback=_prog,
                    overwrite=True,
                )
                out_str = folder
            else:
                out = module_output_dir(self.page_id, create=True)
                ok, fail_n, _failed, out_str = process_folder_to_output(
                    folder,
                    out,
                    watermark_text=text,
                    start_date=start_s or None,
                    end_date=end_s or None,
                    progress_callback=_prog,
                )
            self._progress.setValue(100)
            self._result.setText(f"完成：成功 {ok}，失败 {fail_n}。\n输出：{out_str}")
            level = StatusLevel.SUCCESS if fail_n == 0 and ok else StatusLevel.WARNING
            self.report_status(f"水印 {ok} 成功 / {fail_n} 失败", level=level)
            show_saved(self, f"成功 {ok}，失败 {fail_n}\n{out_str}", out_str)

        self.run_safe(_run, title="生成失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self.report_status("水印照片生成")
