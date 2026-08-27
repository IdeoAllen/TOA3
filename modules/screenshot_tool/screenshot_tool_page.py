# -*- coding: utf-8 -*-
"""截图工具页：区域/全屏 + 精简历史（双击打开，主按钮复制）。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.config_service import get_hotkeys_config
from services.icon_registry import device_pixel_ratio
from services.screenshot_history import list_recent_screenshots
from services.screenshot_service import capture_fullscreen, capture_region, hotkeys_enabled
from widgets import (
    FormSection,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)


class ScreenshotToolPage(BasePage):
    page_id = "screenshot_tool"
    page_title = "截图工具"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        hk = get_hotkeys_config()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll, 1)

        scroll.add_widget(
            PageHeader(
                "截图工具",
                "框选 → 标注 → Enter 复制。剪贴板历史用 Alt+Shift+C；热键在系统设置。",
            )
        )

        box = FormSection("截图")
        box.add_widget(
            SemanticLabel(
                f"热键：区域 {hk.get('screenshot') or 'Alt+A'} · "
                f"全屏 {hk.get('screenshot_region') or 'Alt+Shift+A'} · "
                f"{'已开启' if hotkeys_enabled() else '已关闭'}\n"
                "标注：R/C/A/P/M/T 工具 · S 重选 · F 填充 · 1/2/3 细中粗 · "
                "Shift 正方形/矩形马赛克 · Ctrl+Z/Y 撤销重做 · Enter 完成复制 · "
                "Ctrl+S 另存 · Esc 取消",
                kind="info",
            )
        )
        row = QHBoxLayout()
        btn_region = PrimaryButton("区域截图")
        btn_region.clicked.connect(self._region)
        row.addWidget(btn_region)
        btn_full = SecondaryButton("全屏")
        btn_full.clicked.connect(self._full)
        row.addWidget(btn_full)
        btn_hist = SecondaryButton("刷新")
        btn_hist.clicked.connect(self._reload_history)
        row.addWidget(btn_hist)
        row.addStretch(1)
        box.add_layout(row)
        scroll.add_widget(box)

        mid = QHBoxLayout()
        hist = FormSection("最近截图")
        hist.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list = ListWidget()
        self._list.setMinimumHeight(320)
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.currentRowChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(self._open_selected)
        hist.add_widget(self._list, 1)
        act = QHBoxLayout()
        btn_copy = PrimaryButton("复制")
        btn_copy.clicked.connect(self._copy_selected)
        act.addWidget(btn_copy)
        btn_open = SecondaryButton("打开")
        btn_open.clicked.connect(self._open_selected)
        act.addWidget(btn_open)
        btn_folder = SecondaryButton("文件夹")
        btn_folder.clicked.connect(self._reveal_or_out)
        act.addWidget(btn_folder)
        act.addStretch(1)
        hist.add_layout(act)
        mid.addWidget(hist, 2)

        prev = FormSection("预览")
        prev.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview = QLabel("选择左侧历史项 · 双击打开")
        self._preview.setMinimumHeight(320)
        self._preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 控件库例外：截图历史缩略预览
        self._preview.setStyleSheet("background: palette(base); border: 1px solid palette(mid);")
        prev.add_widget(self._preview, 1)
        mid.addWidget(prev, 2)
        scroll.content_layout.addLayout(mid, 1)
        self._reload_history()

    def _region(self) -> None:
        capture_region(self)
        self._reload_history()

    def _full(self) -> None:
        capture_fullscreen(self)
        self._reload_history()

    def _reload_history(self) -> None:
        self._paths = list_recent_screenshots(30)
        self._list.clear()
        for p in self._paths:
            self._list.addItem(f"{p.name}  ·  {p.parent.name}")
        if self._paths:
            self._list.setCurrentRow(0)
        else:
            self._preview.setText("（暂无截图）")
            self._preview.setPixmap(QPixmap())
        self.report_status(f"截图历史 {len(self._paths)} 条")

    def _current(self) -> Path | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._paths):
            return self._paths[row]
        return None

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._paths):
            return
        p = self._paths[row]
        pm = QPixmap(str(p))
        if pm.isNull():
            self._preview.setText("无法预览")
            self._preview.setPixmap(QPixmap())
            return
        dpr = max(device_pixel_ratio(self), 1.0)
        logical_w = max(320, self._preview.width() - 16)
        logical_h = max(280, self._preview.height() - 16)
        phys_w = max(1, int(round(logical_w * dpr)))
        phys_h = max(1, int(round(logical_h * dpr)))
        scaled = pm.scaled(
            phys_w,
            phys_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self._preview.setPixmap(scaled)
        self._preview.setText("")

    def _open_selected(self) -> None:
        p = self._current()
        if not p:
            show_warning(self, "请先选择一条历史。")
            return
        self._open_path(p)

    def _copy_selected(self) -> None:
        p = self._current()
        if not p:
            show_warning(self, "请先选择一条历史。")
            return
        pm = QPixmap(str(p))
        if pm.isNull():
            show_warning(self, "无法读取图片。")
            return
        QGuiApplication.clipboard().setPixmap(pm)
        show_info(self, f"已复制：{p.name}")
        self.report_status(f"已复制 {p.name}")

    def _reveal_or_out(self) -> None:
        p = self._current()
        if p is not None:
            self._open_path(p.parent)
            return
        from services.storage_paths import module_output_dir

        self._open_path(module_output_dir("screenshot", create=True))

    def _open_path(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as e:
            show_warning(self, f"无法打开：{e}")

    def on_enter(self) -> None:
        self._reload_history()
        self.report_status("截图 · Alt+A")
