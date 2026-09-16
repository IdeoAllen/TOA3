# -*- coding: utf-8 -*-
"""去除图片水印：多图列表 + 框选/涂抹 + 自动角标识别 + 结果对照。"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QColor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_saved, show_warning
from modules.watermark_remover.preview_io import (
    DISPLAY_MAX_EDGE,
    load_display_pixmap,
    scale_boxes_from_orig,
    scale_boxes_to_orig,
)
from modules.watermark_remover.watermark_remover_service import preview_remove, remove_watermark
from services.storage_paths import module_output_dir
from widgets import (
    CheckBox,
    FormSection,
    HintLabel,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ProgressBar,
    RadioButton,
    SecondaryButton,
    SpinBox,
)

try:
    import cv2
    import numpy as np

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    _HAS_CV2 = False

IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)"


from widgets.empty_preview import paint_empty_preview_canvas as _paint_empty_canvas
from widgets.empty_preview import theme_palette as _theme_palette


def _fit_pixmap(source: QPixmap, target_w: int, target_h: int, *, dpr: float) -> QPixmap:
    """按逻辑尺寸缩放，物理像素按 DPR 光栅化，避免糊。"""
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
    """控件库例外：结果预览画布，随窗口放大并保持清晰。"""

    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        self._source: QPixmap | None = None
        self._placeholder = placeholder or "效果预览"
        self._empty_subtitle = "处理或标记后，这里显示去水印效果"
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setText("")  # 空态由 paintEvent 绘制，避免黑底+灰字

    def set_source_pixmap(self, pm: QPixmap | None) -> None:
        if pm is None or pm.isNull():
            self._source = None
            self.clear()
            self.setText("")
            self.update()
            return
        self._source = pm
        self._rebuild()

    def clear_preview(self, text: str | None = None) -> None:
        self._source = None
        self.clear()
        self.setText("")
        if text is not None:
            self._placeholder = text
            # 状态类提示用短副标题；默认空态用引导文案
            if text in ("效果预览", "标记后自动显示效果预览"):
                self._empty_subtitle = "处理或标记后，这里显示去水印效果"
            else:
                self._empty_subtitle = "框选 / 涂抹水印区域后自动刷新"
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source is not None:
            self._rebuild()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._source is None or self.pixmap() is None or self.pixmap().isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            _paint_empty_canvas(
                self,
                painter,
                title=self._placeholder or "效果预览",
                subtitle=self._empty_subtitle,
            )
            painter.end()
            return
        super().paintEvent(event)

    def _rebuild(self) -> None:
        if self._source is None:
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        scaled = _fit_pixmap(self._source, self.width() - 8, self.height() - 8, dpr=dpr)
        if scaled.isNull():
            return
        self.setPixmap(scaled)
        self.setText("")


class RegionPreviewLabel(QLabel):
    # 控件库例外：去水印预览画布（框选 + 涂抹 + 多框）
    marks_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("")
        self.setMouseTracking(True)
        self._source: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._offset = QPoint(0, 0)
        self._scale = 1.0
        self._tool = "box"  # box | brush | erase
        self._brush_radius = 48
        self._dragging = False
        self._painting = False
        self._origin = QPoint()
        self._sel_display: QRect | None = None
        self._boxes: list[tuple[int, int, int, int]] = []  # 显示图坐标
        self._brush_mask: object | None = None  # 显示图分辨率
        self._last_paint_img: tuple[int, int] | None = None
        self._emit_marks = True
        self._empty_title = "标记水印区域"
        self._empty_subtitle = "添加图片后，在此框选或涂抹水印"
        self._orig_w = 0
        self._orig_h = 0
        self._scale_to_orig = 1.0  # 原图像素 / 显示图像素

    def _notify_marks(self) -> None:
        if self._emit_marks:
            self.marks_changed.emit()

    def set_tool(self, tool: str) -> None:
        if tool == self._tool:
            return
        self._tool = tool
        if tool == "box":
            self._clear_brush()
        else:
            self._sel_display = None
            self._boxes.clear()
        self.update()

    def set_brush_radius(self, radius: int) -> None:
        self._brush_radius = max(4, int(radius))

    def set_image_path(self, path: str) -> bool:
        pm, ow, oh = load_display_pixmap(path, max_edge=DISPLAY_MAX_EDGE)
        if pm.isNull() or ow <= 0 or oh <= 0:
            self._source = None
            self._scaled = None
            self._sel_display = None
            self._boxes.clear()
            self._brush_mask = None
            self._orig_w = self._orig_h = 0
            self._scale_to_orig = 1.0
            self.setText("")
            self._empty_title = "无法加载预览"
            self._empty_subtitle = "请换一张图片后重试"
            self.update()
            return False
        self._source = pm
        self._orig_w, self._orig_h = ow, oh
        self._scale_to_orig = float(ow) / float(max(1, pm.width()))
        self._empty_title = "标记水印区域"
        if self._scale_to_orig > 1.02:
            self._empty_subtitle = f"大图已限边预览（原图 {ow}×{oh}）；导出仍用原分辨率"
        else:
            self._empty_subtitle = "添加图片后，在此框选或涂抹水印"
        self._sel_display = None
        self._boxes.clear()
        if _HAS_CV2:
            self._brush_mask = np.zeros((pm.height(), pm.width()), dtype=np.uint8)
        else:
            self._brush_mask = None
        self._rebuild_scaled()
        return True

    def clear_image(self) -> None:
        self._source = None
        self._scaled = None
        self._sel_display = None
        self._boxes.clear()
        self._brush_mask = None
        self._orig_w = self._orig_h = 0
        self._scale_to_orig = 1.0
        self.clear()
        self.setText("")
        self._empty_title = "标记水印区域"
        self._empty_subtitle = "添加图片后，在此框选或涂抹水印"
        self.update()

    def clear_selection(self) -> None:
        self._sel_display = None
        self._boxes.clear()
        self._clear_brush()
        self.update()
        self._notify_marks()

    def _clear_brush(self) -> None:
        if _HAS_CV2 and self._source is not None:
            self._brush_mask = np.zeros((self._source.height(), self._source.width()), dtype=np.uint8)
        else:
            self._brush_mask = None

    def apply_detected_boxes(self, boxes: list[tuple[int, int, int, int]]) -> None:
        """boxes 为原图像素坐标，内部转为显示坐标。"""
        self._tool = "box"
        self._boxes = scale_boxes_from_orig(list(boxes), scale_to_orig=self._scale_to_orig)
        self._sel_display = None
        self._clear_brush()
        self.update()
        self._notify_marks()

    def selected_image_region(self) -> tuple[int, int, int, int] | None:
        """返回原图像素选区（供处理/预览）。"""
        disp = self._selected_display_region()
        if disp is None:
            return None
        mapped = scale_boxes_to_orig([disp], scale=self._scale_to_orig)
        return mapped[0] if mapped else None

    def _selected_display_region(self) -> tuple[int, int, int, int] | None:
        if self._boxes:
            return self._boxes[0]
        if self._source is None or self._sel_display is None or self._scale <= 0:
            return None
        r = self._sel_display.normalized()
        if r.width() < 4 or r.height() < 4:
            return None
        x = int(round((r.x() - self._offset.x()) / self._scale))
        y = int(round((r.y() - self._offset.y()) / self._scale))
        w = int(round(r.width() / self._scale))
        h = int(round(r.height() / self._scale))
        sw, sh = self._source.width(), self._source.height()
        x = max(0, min(x, sw - 1))
        y = max(0, min(y, sh - 1))
        w = max(1, min(w, sw - x))
        h = max(1, min(h, sh - y))
        return x, y, w, h

    def image_boxes(self) -> list[tuple[int, int, int, int]]:
        """原图像素框列表。"""
        if self._boxes:
            return scale_boxes_to_orig(list(self._boxes), scale=self._scale_to_orig)
        one = self.selected_image_region()
        return [one] if one else []

    def brush_mask(self) -> object | None:
        """原图分辨率蒙版（涂抹时从显示分辨率上采样）。"""
        if not _HAS_CV2 or self._brush_mask is None:
            return None
        if not np.any(self._brush_mask):
            return None
        if self._orig_w <= 0 or self._orig_h <= 0:
            return self._brush_mask
        if (
            self._brush_mask.shape[0] == self._orig_h
            and self._brush_mask.shape[1] == self._orig_w
        ):
            return self._brush_mask
        return cv2.resize(
            self._brush_mask,
            (self._orig_w, self._orig_h),
            interpolation=cv2.INTER_NEAREST,
        )

    def has_marks(self) -> bool:
        if not _HAS_CV2 or self._brush_mask is None:
            return bool(self._boxes) or self._selected_display_region() is not None
        if np.any(self._brush_mask):
            return True
        return bool(self._boxes) or self._selected_display_region() is not None

    def marks_snapshot(self) -> dict:
        """线程安全快照：原图坐标 boxes / brush / region。"""
        brush = self.brush_mask()
        if brush is not None and _HAS_CV2:
            brush = np.asarray(brush).copy()
        boxes = self.image_boxes()
        region = None if boxes or brush is not None else self.selected_image_region()
        return {
            "boxes": boxes,
            "brush_mask": brush,
            "region": region,
            "orig_w": self._orig_w,
            "orig_h": self._orig_h,
        }

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source is not None:
            old_boxes = list(self._boxes)
            old_one = None if old_boxes else self._selected_display_region()
            self._rebuild_scaled()
            if old_boxes:
                self._boxes = old_boxes
            elif old_one is not None:
                self._set_display_from_image(old_one)

    def _rebuild_scaled(self) -> None:
        if self._source is None:
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        avail_w = max(1, self.width() - 8)
        avail_h = max(1, self.height() - 8)
        scaled = _fit_pixmap(self._source, avail_w, avail_h, dpr=dpr)
        if scaled.isNull():
            return
        self._scaled = scaled
        self._scale = (scaled.width() / dpr) / max(1, self._source.width())
        ox = (self.width() - int(round(scaled.width() / dpr))) // 2
        oy = (self.height() - int(round(scaled.height() / dpr))) // 2
        self._offset = QPoint(ox, oy)
        self.setPixmap(scaled)
        self.setText("")

    def _set_display_from_image(self, region: tuple[int, int, int, int]) -> None:
        x, y, w, h = region
        self._sel_display = QRect(
            int(round(x * self._scale)) + self._offset.x(),
            int(round(y * self._scale)) + self._offset.y(),
            int(round(w * self._scale)),
            int(round(h * self._scale)),
        )

    def _display_to_image(self, pt: QPoint) -> tuple[int, int] | None:
        if self._source is None or self._scale <= 0:
            return None
        x = int(round((pt.x() - self._offset.x()) / self._scale))
        y = int(round((pt.y() - self._offset.y()) / self._scale))
        sw, sh = self._source.width(), self._source.height()
        if x < 0 or y < 0 or x >= sw or y >= sh:
            return None
        return x, y

    def _paint_brush(self, pt: tuple[int, int], erase: bool = False) -> None:
        if not _HAS_CV2 or self._brush_mask is None:
            return
        color = 0 if erase else 255
        r = max(1, self._brush_radius)
        if self._last_paint_img is not None:
            cv2.line(
                self._brush_mask,
                self._last_paint_img,
                pt,
                color,
                thickness=max(2, r * 2),
                lineType=cv2.LINE_AA,
            )
        cv2.circle(self._brush_mask, pt, r, color, thickness=-1, lineType=cv2.LINE_AA)
        self._last_paint_img = pt

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._scaled is None:
            super().mousePressEvent(event)
            return
        pt = event.position().toPoint()
        if self._tool in ("brush", "erase"):
            if not _HAS_CV2:
                show_warning(self, "涂抹需要 OpenCV（opencv-python）。")
                super().mousePressEvent(event)
                return
            self._painting = True
            img_pt = self._display_to_image(pt)
            if img_pt:
                self._last_paint_img = img_pt
                self._paint_brush(img_pt, erase=self._tool == "erase")
                self.update()
        else:
            self._dragging = True
            self._origin = pt
            self._sel_display = QRect(self._origin, self._origin)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._painting:
            img_pt = self._display_to_image(event.position().toPoint())
            if img_pt:
                self._paint_brush(img_pt, erase=self._tool == "erase")
                self.update()
        elif self._dragging:
            self._sel_display = QRect(self._origin, event.position().toPoint()).normalized()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        changed = False
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._sel_display = QRect(self._origin, event.position().toPoint()).normalized()
            one = self._selected_display_region()
            if one:
                self._boxes = [one]
            self.update()
            changed = True
        if event.button() == Qt.MouseButton.LeftButton and self._painting:
            self._painting = False
            self._last_paint_img = None
            changed = True
        if changed:
            self._notify_marks()
        super().mouseReleaseEvent(event)

    def _box_display_rect(self, box: tuple[int, int, int, int]) -> QRect:
        x, y, w, h = box
        return QRect(
            int(round(x * self._scale)) + self._offset.x(),
            int(round(y * self._scale)) + self._offset.y(),
            int(round(w * self._scale)),
            int(round(h * self._scale)),
        ).normalized()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._source is None or self._scaled is None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            _paint_empty_canvas(
                self,
                painter,
                title=self._empty_title,
                subtitle=self._empty_subtitle,
            )
            painter.end()
            return

        # 浅色衬底，避免图片周围露黑边
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p = _theme_palette()
        surface = QColor(str(p.get("surface") or "#F7F3EE"))
        painter.fillRect(self.rect(), surface)
        painter.end()

        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor("#E11D48"))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        for box in self._boxes:
            painter.drawRect(self._box_display_rect(box))
        if not self._boxes and self._sel_display is not None:
            painter.drawRect(self._sel_display.normalized())
        if (
            _HAS_CV2
            and self._brush_mask is not None
            and np.any(self._brush_mask)
            and self._source is not None
        ):
            sw = max(1, int(round(self._source.width() * self._scale)))
            sh = max(1, int(round(self._source.height() * self._scale)))
            disp = cv2.resize(self._brush_mask, (sw, sh), interpolation=cv2.INTER_NEAREST)
            overlay = np.zeros((sh, sw, 4), dtype=np.uint8)
            overlay[disp > 0] = (220, 40, 40, 120)
            from PySide6.QtGui import QImage

            qimg = QImage(
                overlay.data,
                sw,
                sh,
                sw * 4,
                QImage.Format.Format_RGBA8888,
            )
            painter.drawImage(self._offset.x(), self._offset.y(), qimg)
        painter.end()


class WatermarkRemoverPage(BasePage):
    page_id = "watermark_remover"
    page_title = "去除图片水印"
    _preview_done = Signal(int, object)  # token, png_bytes | None
    _process_done = Signal(int, object)  # token, RemoveResult-like dict | None
    _batch_item_done = Signal(int, int, int, object)  # token, i, total, result dict
    _batch_finished = Signal(int, int, int)  # token, ok, total
    _detect_done = Signal(int, object)  # token, boxes list | str error

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._files: list[str] = []
        self._preview_token = 0
        self._preview_busy = False
        self._job_token = 0
        self._job_busy = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(280)
        self._preview_timer.timeout.connect(self._refresh_effect_preview)
        self._preview_done.connect(self._on_effect_preview_done)
        self._process_done.connect(self._on_process_done)
        self._batch_item_done.connect(self._on_batch_item_done)
        self._batch_finished.connect(self._on_batch_finished)
        self._detect_done.connect(self._on_detect_done)

        # 操作按钮稍后挂到 layout；先占位便于 _set_job_busy
        self._action_btns: list = []

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(8)

        outer.addWidget(
            PageHeader(
                "去除图片水印",
                "擦除豆包/角标：默认 light 本地轻量；可选 AI（LaMa）。Ctrl 多选可批量。大图限边预览。",
            )
        )

        top = QHBoxLayout()
        btn_add = SecondaryButton("添加图片…")
        btn_add.clicked.connect(self._add_files)
        top.addWidget(btn_add)
        btn_folder = SecondaryButton("添加文件夹…")
        btn_folder.clicked.connect(self._add_folder)
        top.addWidget(btn_folder)
        btn_del = SecondaryButton("删除选中")
        btn_del.setToolTip("从列表移除选中项（不删磁盘文件）")
        btn_del.clicked.connect(self._remove_selected)
        top.addWidget(btn_del)
        self._prefer_ai = CheckBox("AI 增强")
        self._prefer_ai.setToolTip(
            "默认关＝本地轻量 light（低配可用）。装好模型并勾选后才走 LaMa。"
        )
        self._prefer_ai.setChecked(False)
        self._prefer_ai.toggled.connect(self._on_prefer_ai_toggled)
        top.addWidget(self._prefer_ai)
        self._btn_ai_setup = SecondaryButton("安装 AI…")
        self._btn_ai_setup.setToolTip(
            "两步引导：① 下载 LaMa 模型 ② 勾选「AI 增强」。不装也能用本地轻量。"
        )
        self._btn_ai_setup.clicked.connect(self._open_ai_setup)
        top.addWidget(self._btn_ai_setup)
        self._ai_hint = HintLabel("")
        top.addWidget(self._ai_hint, 1)
        outer.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(8)
        list_box = FormSection("待处理")
        list_box.setMaximumWidth(220)
        self._list = ListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setMinimumWidth(160)
        self._list.currentRowChanged.connect(self._on_select)
        list_box.add_widget(self._list, 1)
        list_box.add_widget(HintLabel("Ctrl/Shift 多选 · 可「处理选中」"))
        mid.addWidget(list_box)

        edit_box = FormSection("标记水印")
        self._preview = RegionPreviewLabel()
        self._preview.marks_changed.connect(self._schedule_effect_preview)
        edit_box.add_widget(self._preview, 1)
        tool_row = QHBoxLayout()
        self._tool_box = RadioButton("框选")
        self._tool_box.setChecked(True)
        self._tool_box.toggled.connect(lambda c: c and self._preview.set_tool("box"))
        tool_row.addWidget(self._tool_box)
        self._tool_brush = RadioButton("涂抹")
        self._tool_brush.toggled.connect(lambda c: c and self._preview.set_tool("brush"))
        tool_row.addWidget(self._tool_brush)
        self._tool_erase = RadioButton("擦除")
        self._tool_erase.toggled.connect(lambda c: c and self._preview.set_tool("erase"))
        tool_row.addWidget(self._tool_erase)
        self._brush_spin = SpinBox()
        self._brush_spin.setRange(8, 120)
        self._brush_spin.setValue(48)
        self._brush_spin.setPrefix("笔刷 ")
        self._brush_spin.valueChanged.connect(self._preview.set_brush_radius)
        tool_row.addWidget(self._brush_spin)
        tool_row.addStretch(1)
        edit_box.add_layout(tool_row)
        row_prev = QHBoxLayout()
        btn_clear_sel = SecondaryButton("清除标记")
        btn_clear_sel.clicked.connect(self._preview.clear_selection)
        row_prev.addWidget(btn_clear_sel)
        btn_auto = SecondaryButton("自动识别角标")
        btn_auto.clicked.connect(self._auto_detect)
        row_prev.addWidget(btn_auto)
        self._mild_corners = CheckBox("四角轻度模糊")
        self._mild_corners.setChecked(False)
        self._mild_corners.toggled.connect(lambda _c: self._schedule_effect_preview())
        row_prev.addWidget(self._mild_corners)
        row_prev.addStretch(1)
        edit_box.add_layout(row_prev)
        mid.addWidget(edit_box, 3)

        after_box = FormSection("效果预览")
        self._after = FitPixmapLabel("标记后自动显示效果预览")
        after_box.add_widget(self._after, 1)
        mid.addWidget(after_box, 3)
        outer.addLayout(mid, 1)

        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        outer.addWidget(self._progress)

        actions = QHBoxLayout()
        btn_one = PrimaryButton("处理当前")
        btn_one.clicked.connect(self._on_run_one)
        actions.addWidget(btn_one)
        btn_sel = SecondaryButton("处理选中")
        btn_sel.setToolTip("处理列表中多选的图片（后台执行，不卡界面）")
        btn_sel.clicked.connect(self._on_run_selected)
        actions.addWidget(btn_sel)
        btn_all = SecondaryButton("全部处理")
        btn_all.clicked.connect(self._on_run_all)
        actions.addWidget(btn_all)
        btn_open = SecondaryButton("打开输出目录")
        btn_open.clicked.connect(self._open_out)
        actions.addWidget(btn_open)
        actions.addStretch(1)
        outer.addLayout(actions)
        self._action_btns = [btn_one, btn_sel, btn_all, btn_add, btn_folder, btn_del]

        self._result = HintLabel(
            "框选/涂抹后右侧自动预览；默认本地轻量 light。可选勾「AI 增强」走 LaMa。"
        )
        outer.addWidget(self._result)
        self._refresh_ai_hint()

    def _refresh_ai_hint(self) -> None:
        try:
            from services.integrations import get_client

            client = get_client("watermark_ai")
            hint = getattr(client, "status_hint", None)
            text = hint() if callable(hint) else ""
            ready = bool(client.health_check()) if getattr(client, "enabled", False) else False
        except Exception:
            text = ""
            ready = False
        self._btn_ai_setup.setVisible(not ready)
        if ready:
            self._ai_hint.setText(
                f"LaMa 已装好 · 勾「AI 增强」走 lama，不勾仍为 light（{text or '就绪'}）"
            )
        else:
            self._ai_hint.setText(
                "当前引擎：light（默认）。有条件再点「安装 AI…」→ 装完可勾选走 lama"
            )
        # 未就绪时强制保持不勾，避免误以为已开 AI
        if not ready and self._prefer_ai.isChecked():
            self._prefer_ai.blockSignals(True)
            self._prefer_ai.setChecked(False)
            self._prefer_ai.blockSignals(False)

    def _on_prefer_ai_toggled(self, checked: bool) -> None:
        if not checked:
            self.report_status("已切回本地轻量 light", StatusLevel.INFO)
            self._schedule_effect_preview()
            return
        try:
            from services.integrations import get_client

            client = get_client("watermark_ai")
            ready = bool(client.enabled and client.health_check())
        except Exception:
            ready = False
        if ready:
            self.report_status("已开 AI 增强（lama）；失败自动回退 light", StatusLevel.INFO)
            return
        self._prefer_ai.blockSignals(True)
        self._prefer_ai.setChecked(False)
        self._prefer_ai.blockSignals(False)
        from core.user_messages import ask_confirm

        if ask_confirm(
            self,
            "还没装 AI（LaMa）模型，无法勾选增强。\n\n"
            "两步即可：\n"
            "① 点「安装 AI…」→「下载去水印模型」\n"
            "② 装完后本页会自动勾选「AI 增强」\n\n"
            "不装也没关系：继续用默认本地轻量 light。",
            title="安装 AI 增强？",
        ):
            self._open_ai_setup()

    def _open_ai_setup(self) -> None:
        from modules.watermark_remover.watermark_ai_setup_dialog import WatermarkAiSetupDialog

        dlg = WatermarkAiSetupDialog(self)
        dlg.exec()
        self._refresh_ai_hint()
        if dlg.installed:
            self._prefer_ai.blockSignals(True)
            self._prefer_ai.setChecked(True)
            self._prefer_ai.blockSignals(False)
            self.report_status("AI 已就绪：已勾选，导出走 lama（可随时取消勾选回 light）", StatusLevel.SUCCESS)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", IMAGE_FILTER)
        if files:
            self._append_files(files)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if not folder:
            return
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
        files = sorted(
            str(p) for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in exts
        )
        self._append_files(files)

    def _append_files(self, files: list[str]) -> None:
        for f in files:
            if f not in self._files:
                self._files.append(f)
                self._list.addItem(Path(f).name)
        if self._files and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)
        self._result.setText(f"列表 {len(self._files)} 张。")

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self._list.selectedIndexes()}, reverse=True)
        if not rows:
            show_warning(self, "请先选中要移除的项。")
            return
        for row in rows:
            if 0 <= row < len(self._files):
                self._files.pop(row)
                self._list.takeItem(row)
        self._preview_timer.stop()
        self._preview_token += 1
        if self._files:
            self._list.setCurrentRow(min(rows[-1], len(self._files) - 1))
        else:
            self._preview.clear_image()
            self._after.clear_preview()
        self._result.setText(f"列表 {len(self._files)} 张。")

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._files):
            return
        path = self._files[row]
        self._preview_timer.stop()
        self._preview_token += 1
        self._after.clear_preview("请先在左侧标记水印区域")
        if not self._preview.set_image_path(path):
            show_warning(self, "无法加载预览。")

    def _auto_detect(self) -> None:
        src = self._current_path()
        if not src:
            show_warning(self, "请先选择图片。")
            return
        if not _HAS_CV2:
            show_warning(self, "自动识别需要 OpenCV（opencv-python）。")
            return
        if self._job_busy:
            show_warning(self, "正在处理中，请稍候。")
            return
        self._job_token += 1
        token = self._job_token
        self._result.setText("正在识别角标…")

        def worker() -> None:
            try:
                from modules.watermark_remover.watermark_remover_processor import (
                    WatermarkRemoverProcessor,
                )

                proc = WatermarkRemoverProcessor()
                bgr = proc.imread(src)
                if bgr is None:
                    self._detect_done.emit(token, "无法读取图片。")
                    return
                boxes = proc.detect_boxes(bgr)
                self._detect_done.emit(token, boxes if boxes else [])
            except Exception as exc:
                self._detect_done.emit(token, f"识别失败：{exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_detect_done(self, token: int, payload: object) -> None:
        if token != self._job_token:
            return
        if isinstance(payload, str):
            show_warning(self, payload)
            self._result.setText(payload)
            return
        boxes = list(payload) if isinstance(payload, list) else []
        if not boxes:
            show_warning(self, "未识别到明显角标，请手动框选或涂抹。")
            self._result.setText("未识别到角标")
            return
        self._preview.apply_detected_boxes(boxes)
        self._tool_box.setChecked(True)
        self._result.setText(f"已识别 {len(boxes)} 个候选区域。")

    def _schedule_effect_preview(self) -> None:
        self._preview_timer.start()

    def _refresh_effect_preview(self) -> None:
        src = self._current_path()
        if not src:
            return
        if not self._preview.has_marks():
            self._after.clear_preview("请先在左侧标记水印区域")
            return
        if self._preview_busy:
            self._preview_timer.start()
            return

        snap = self._preview.marks_snapshot()
        mild = self._mild_corners.isChecked()
        self._preview_busy = True
        self._preview_token += 1
        token = self._preview_token
        self._result.setText("正在刷新右侧效果预览…")

        def worker() -> None:
            try:
                result = preview_remove(
                    src,
                    mild_corner_blur=mild,
                    region=snap.get("region"),
                    boxes=snap.get("boxes") or None,
                    brush_mask=snap.get("brush_mask"),
                )
                payload = result.png_bytes if result.ok else None
                self._preview_done.emit(token, payload)
            except Exception:
                self._preview_done.emit(token, None)

        threading.Thread(target=worker, daemon=True).start()

    def _on_effect_preview_done(self, token: int, png_bytes: object) -> None:
        if token != self._preview_token:
            return
        self._preview_busy = False
        if not isinstance(png_bytes, (bytes, bytearray)) or not png_bytes:
            self._after.clear_preview("预览失败，请调整标记后重试")
            self._result.setText("效果预览失败")
            return
        pm = QPixmap()
        if not pm.loadFromData(bytes(png_bytes), "PNG") or pm.isNull():
            self._after.clear_preview("预览解码失败")
            return
        self._after.set_source_pixmap(pm)
        self._result.setText("右侧已更新效果预览；满意后点「处理当前」导出")
        self.report_status("效果预览已更新")

    def _set_job_busy(self, busy: bool) -> None:
        self._job_busy = busy
        for btn in self._action_btns:
            btn.setEnabled(not busy)

    def _dest_for(self, src: str):
        out_dir = module_output_dir(self.page_id, create=True)
        stem = Path(src).stem
        ext = Path(src).suffix or ".jpg"
        return out_dir / f"{stem}_去水印{ext}"

    def _on_run_one(self) -> None:
        src = self._current_path()
        if not src:
            show_warning(self, "请先添加并选择图片。")
            return
        if self._job_busy:
            show_warning(self, "正在处理中，请稍候。")
            return
        snap = self._preview.marks_snapshot()
        prefer_ai = self._prefer_ai.isChecked()
        mild = self._mild_corners.isChecked()
        dest = self._dest_for(src)
        self._job_token += 1
        token = self._job_token
        self._set_job_busy(True)
        engine_hint = "lama" if prefer_ai else "light"
        self._result.setText(f"正在处理（引擎优先 {engine_hint}）…")
        self._progress.setRange(0, 0)

        def worker() -> None:
            try:
                result = remove_watermark(
                    src,
                    dest,
                    prefer_ai=prefer_ai,
                    mild_corner_blur=mild,
                    region=snap.get("region"),
                    boxes=snap.get("boxes") or None,
                    brush_mask=snap.get("brush_mask"),
                )
                self._process_done.emit(
                    token,
                    {
                        "ok": result.ok,
                        "output_path": result.output_path,
                        "engine": result.engine,
                        "message": result.message,
                    },
                )
            except Exception as exc:
                self._process_done.emit(
                    token,
                    {"ok": False, "output_path": "", "engine": "", "message": str(exc)},
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_process_done(self, token: int, payload: object) -> None:
        if token != self._job_token:
            return
        self._set_job_busy(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        if not isinstance(payload, dict):
            show_warning(self, "处理失败")
            return
        if payload.get("ok") and payload.get("output_path"):
            path = str(payload["output_path"])
            pm, _, _ = load_display_pixmap(path, max_edge=DISPLAY_MAX_EDGE)
            if not pm.isNull():
                self._after.set_source_pixmap(pm)
            msg = str(payload.get("message") or "完成")
            eng = str(payload.get("engine") or "")
            self._result.setText(f"{msg}\n{path}")
            show_saved(self, f"{msg}\n引擎：{eng}\n{path}", path)
            self.report_status(f"去水印完成（{eng}）", level=StatusLevel.SUCCESS)
            return
        err = str(payload.get("message") or "去水印失败")
        self._result.setText(err)
        show_warning(self, err)

    def _current_path(self) -> str | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def _selected_paths(self) -> list[str]:
        rows = sorted({i.row() for i in self._list.selectedIndexes()})
        return [self._files[r] for r in rows if 0 <= r < len(self._files)]

    def _on_run_selected(self) -> None:
        paths = self._selected_paths()
        if not paths:
            show_warning(self, "请先多选图片（Ctrl/Shift）。")
            return
        self._run_batch(paths)

    def _on_run_all(self) -> None:
        if not self._files:
            show_warning(self, "请先添加图片。")
            return
        self._run_batch(list(self._files))

    def _run_batch(self, paths: list[str]) -> None:
        if self._job_busy:
            show_warning(self, "正在处理中，请稍候。")
            return
        prefer_ai = self._prefer_ai.isChecked()
        mild = self._mild_corners.isChecked()
        current = self._current_path()
        # 仅当前图带上手动标记；其余走自动角标 / 默认右下
        snap = self._preview.marks_snapshot() if current else {}
        jobs: list[dict] = []
        for src in paths:
            dest = self._dest_for(src)
            if src == current and (snap.get("boxes") or snap.get("brush_mask") or snap.get("region")):
                jobs.append(
                    {
                        "src": src,
                        "dest": dest,
                        "region": snap.get("region"),
                        "boxes": snap.get("boxes") or None,
                        "brush_mask": snap.get("brush_mask"),
                    }
                )
            else:
                jobs.append(
                    {
                        "src": src,
                        "dest": dest,
                        "region": None,
                        "boxes": None,
                        "brush_mask": None,
                    }
                )

        self._job_token += 1
        token = self._job_token
        self._set_job_busy(True)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        engine_hint = "lama" if prefer_ai else "light"
        self._result.setText(f"批量处理中（{len(jobs)} 张 · 优先 {engine_hint}）…")

        def worker() -> None:
            ok = 0
            total = len(jobs)
            for i, job in enumerate(jobs, start=1):
                try:
                    result = remove_watermark(
                        job["src"],
                        job["dest"],
                        prefer_ai=prefer_ai,
                        mild_corner_blur=mild,
                        region=job.get("region"),
                        boxes=job.get("boxes"),
                        brush_mask=job.get("brush_mask"),
                    )
                    payload = {
                        "ok": result.ok,
                        "output_path": result.output_path,
                        "engine": result.engine,
                        "message": result.message,
                        "src": job["src"],
                    }
                    if result.ok:
                        ok += 1
                except Exception as exc:
                    payload = {
                        "ok": False,
                        "output_path": "",
                        "engine": "",
                        "message": str(exc),
                        "src": job["src"],
                    }
                self._batch_item_done.emit(token, i, total, payload)
            self._batch_finished.emit(token, ok, total)

        threading.Thread(target=worker, daemon=True).start()

    def _on_batch_item_done(self, token: int, i: int, total: int, payload: object) -> None:
        if token != self._job_token:
            return
        self._progress.setValue(int(100 * i / max(1, total)))
        if isinstance(payload, dict) and payload.get("src"):
            src = str(payload["src"])
            try:
                idx = self._files.index(src)
                self._list.setCurrentRow(idx)
            except ValueError:
                pass
            if payload.get("ok") and payload.get("output_path"):
                pm, _, _ = load_display_pixmap(
                    str(payload["output_path"]), max_edge=DISPLAY_MAX_EDGE
                )
                if not pm.isNull():
                    self._after.set_source_pixmap(pm)

    def _on_batch_finished(self, token: int, ok: int, total: int) -> None:
        if token != self._job_token:
            return
        self._set_job_busy(False)
        self._progress.setValue(100)
        self._result.setText(f"批量完成：成功 {ok} / {total}")
        show_saved(self, f"成功 {ok} / {total}", module_output_dir(self.page_id, create=True))
        self.report_status(f"批量去水印 {ok}/{total}", level=StatusLevel.SUCCESS)

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self._refresh_ai_hint()
        # 进页保证默认 light：未装 AI 时不勾选
        if not self._prefer_ai.isChecked():
            pass
        self.report_status("去除图片水印 · 默认 light")
