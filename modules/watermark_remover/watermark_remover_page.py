# -*- coding: utf-8 -*-
"""去除图片水印：多图列表 + 框选/涂抹 + 自动角标识别 + 结果对照。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QMouseEvent, QPainter, QPen, QPixmap
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
        self._placeholder = placeholder
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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


class RegionPreviewLabel(QLabel):
    # 控件库例外：去水印预览画布（框选 + 涂抹 + 多框）
    marks_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background: palette(dark); border: 1px solid palette(mid);"
        )
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
        self._boxes: list[tuple[int, int, int, int]] = []
        self._brush_mask: object | None = None
        self._last_paint_img: tuple[int, int] | None = None
        self._emit_marks = True

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
        pm = QPixmap(path)
        if pm.isNull():
            self._source = None
            self._scaled = None
            self._sel_display = None
            self._boxes.clear()
            self._brush_mask = None
            self.setText("无法加载预览")
            return False
        self._source = pm
        self._sel_display = None
        self._boxes.clear()
        if _HAS_CV2:
            self._brush_mask = np.zeros((pm.height(), pm.width()), dtype=np.uint8)
        else:
            self._brush_mask = None
        self._rebuild_scaled()
        return True

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
        self._tool = "box"
        self._boxes = list(boxes)
        self._sel_display = None
        self._clear_brush()
        self.update()
        self._notify_marks()

    def selected_image_region(self) -> tuple[int, int, int, int] | None:
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
        if self._boxes:
            return list(self._boxes)
        one = self.selected_image_region()
        return [one] if one else []

    def brush_mask(self) -> object | None:
        if not _HAS_CV2 or self._brush_mask is None:
            return None
        if np.any(self._brush_mask):
            return self._brush_mask
        return None

    def has_marks(self) -> bool:
        if self.brush_mask() is not None:
            return True
        return bool(self.image_boxes())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source is not None:
            old_boxes = list(self._boxes)
            old_one = self.selected_image_region()
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
            one = self.selected_image_region()
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
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(Qt.GlobalColor.red)
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._files: list[str] = []
        self._preview_token = 0
        self._preview_busy = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(280)
        self._preview_timer.timeout.connect(self._refresh_effect_preview)
        self._preview_done.connect(self._on_effect_preview_done)

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(8)

        outer.addWidget(
            PageHeader(
                "去除图片水印",
                "擦除豆包/角标等：优先 AI 强引擎，未配置或失败时自动本地修复。Ctrl 多选可批量。",
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
        self._prefer_ai = CheckBox("优先 AI")
        self._prefer_ai.setToolTip(
            "走 integrations「watermark_ai」（系统设置 → 能力接入）。未启用时自动本地修复。"
        )
        self._prefer_ai.setChecked(True)
        top.addWidget(self._prefer_ai)
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
        list_box.add_widget(HintLabel("Ctrl/Shift 多选"))
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
        btn_sel.setToolTip("处理列表中多选的图片")
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

        self._result = HintLabel("框选/涂抹后右侧自动预览；AI 需在能力接入启用 watermark_ai。")
        outer.addWidget(self._result)
        self._refresh_ai_hint()

    def _refresh_ai_hint(self) -> None:
        try:
            from services.integrations import get_client

            client = get_client("watermark_ai")
            on = bool(getattr(client, "enabled", False))
        except Exception:
            on = False
        if on:
            self._ai_hint.setText("AI 已启用 · 优先走远程/本地模型")
        else:
            self._ai_hint.setText("AI 未启用 · 当前本地修复（设置→能力接入可开 watermark_ai）")

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
            self._preview.setText("预览")
            self._preview.setPixmap(QPixmap())
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
        from modules.watermark_remover.watermark_remover_processor import WatermarkRemoverProcessor

        proc = WatermarkRemoverProcessor()
        bgr = proc.imread(src)
        if bgr is None:
            show_warning(self, "无法读取图片。")
            return
        boxes = proc.detect_boxes(bgr)
        if not boxes:
            show_warning(self, "未识别到明显角标，请手动框选或涂抹。")
            return
        self._preview.apply_detected_boxes(boxes)
        self._tool_box.setChecked(True)
        self._result.setText(f"已识别 {len(boxes)} 个候选区域。")

    def _schedule_effect_preview(self) -> None:
        self._preview_timer.start()

    def _refresh_effect_preview(self) -> None:
        import threading

        src = self._current_path()
        if not src:
            return
        if not self._preview.has_marks():
            self._after.clear_preview("请先在左侧标记水印区域")
            return
        if self._preview_busy:
            self._preview_timer.start()
            return

        boxes = self._preview.image_boxes()
        brush = self._preview.brush_mask()
        region = self._preview.selected_image_region() if not boxes and not brush else None
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
                    region=region,
                    boxes=boxes if boxes else None,
                    brush_mask=brush,
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

    def _process_one(self, src: str, *, show_dialog: bool = True) -> bool:
        is_current = src == self._current_path()
        boxes = self._preview.image_boxes() if is_current else []
        brush = self._preview.brush_mask() if is_current else None
        region = (
            self._preview.selected_image_region()
            if is_current and not boxes and not brush
            else None
        )
        out_dir = module_output_dir(self.page_id, create=True)
        stem = Path(src).stem
        ext = Path(src).suffix or ".jpg"
        dest = out_dir / f"{stem}_去水印{ext}"
        result = remove_watermark(
            src,
            dest,
            prefer_ai=self._prefer_ai.isChecked(),
            mild_corner_blur=self._mild_corners.isChecked(),
            region=region,
            boxes=boxes if boxes else None,
            brush_mask=brush,
        )
        if result.ok and result.output_path:
            pm = QPixmap(result.output_path)
            if not pm.isNull():
                self._after.set_source_pixmap(pm)
            self._result.setText(f"{result.message}\n{result.output_path}")
            if show_dialog:
                show_saved(self, f"{result.message}\n{result.output_path}", result.output_path)
            return True
        self._result.setText(result.message or "失败")
        if show_dialog:
            show_warning(self, result.message or "去水印失败")
        return False

    def _current_path(self) -> str | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def _selected_paths(self) -> list[str]:
        rows = sorted({i.row() for i in self._list.selectedIndexes()})
        return [self._files[r] for r in rows if 0 <= r < len(self._files)]

    def _on_run_one(self) -> None:
        src = self._current_path()
        if not src:
            show_warning(self, "请先添加并选择图片。")
            return
        self.run_safe(lambda: self._process_one(src), title="去水印失败")
        self.report_status("去水印完成", level=StatusLevel.SUCCESS)

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
        def _run() -> None:
            ok = 0
            total = len(paths)
            for i, src in enumerate(paths, start=1):
                try:
                    idx = self._files.index(src)
                    self._list.setCurrentRow(idx)
                except ValueError:
                    pass
                self._preview.set_image_path(src)
                if self._process_one(src, show_dialog=False):
                    ok += 1
                self._progress.setValue(int(100 * i / max(1, total)))
            self._progress.setValue(100)
            self._result.setText(f"批量完成：成功 {ok} / {total}")
            show_saved(self, f"成功 {ok} / {total}", module_output_dir(self.page_id, create=True))
            self.report_status(f"批量去水印 {ok}/{total}", level=StatusLevel.SUCCESS)

        self.run_safe(_run, title="批量去水印失败")

    def _open_out(self) -> None:
        out = module_output_dir(self.page_id, create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def on_enter(self) -> None:
        self._refresh_ai_hint()
        self.report_status("去除图片水印")
