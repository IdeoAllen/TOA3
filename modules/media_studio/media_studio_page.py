# -*- coding: utf-8 -*-
"""媒体工坊：左控右看 · 图片 / 视频创作台。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal, QSize, QTimer
from PySide6.QtGui import (
    QFontMetrics,
    QGuiApplication,
    QImageReader,
    QPainter,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_error, show_saved, show_warning
from modules.media_studio.gen_queue import MediaGenQueueController, MediaGenSpec, MediaGenTask
from services.compute_source import pick_effective_profile_id
from services.model_catalog import get_active_profile_id, resolve_profile, set_active_profile_id
from services.model_presentation import (
    group_profiles_for_combo,
    is_evolink_image_profile,
    is_volcengine_image_profile,
)
from services.model_ready_registry import list_ready
from services.storage_paths import module_output_dir
from widgets.empty_preview import paint_empty_preview_canvas
from widgets import (
    ComboBox,
    FormRow,
    HintLabel,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ProgressBar,
    RadioButton,
    SecondaryButton,
    SectionTitle,
    SemanticLabel,
    Slider,
    SpinBox,
    Switch,
    TabWidget,
)

# —— 图片 ——
_KIND_IMAGE = "image"
_KIND_VIDEO = "video"

_IMG_TXT = "txt2img"
_IMG_REF = "img2img"
_IMG_FUSE = "fusion"

_IMAGE_RATIOS: list[tuple[str, str, int, int]] = [
    ("智能", "smart", 1024, 1024),
    ("1:1", "1:1", 1024, 1024),
    ("3:4", "3:4", 768, 1024),
    ("4:3", "4:3", 1024, 768),
    ("16:9", "16:9", 1280, 720),
    ("9:16", "9:16", 720, 1280),
    ("2:3", "2:3", 768, 1152),
    ("3:2", "3:2", 1152, 768),
]

_VIDEO_RATIOS = ["自适应", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]
_VIDEO_RES = ["480p", "720p", "1080p"]


def _clip_line(text: str, limit: int) -> str:
    line = text.replace("\n", " ").strip()
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def _fit_pixmap(path: Path, max_w: int, max_h: int) -> QPixmap:
    """按原比例缩略，不变形。"""
    if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
        return QPixmap()
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    src = reader.size()
    if src.isValid() and src.width() > 0 and src.height() > 0:
        fit = src.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(fit)
    else:
        reader.setScaledSize(QSize(max_w, max_h))
    img = reader.read()
    if img.isNull():
        return QPixmap()
    return QPixmap.fromImage(img)


def _set_semantic(label: SemanticLabel, kind: str, text: str, *, compact: bool = False) -> None:
    label.setText(text)
    label.setProperty("class", f"semantic-{kind}")
    if compact:
        label.setProperty("compact", "true")
    else:
        label.setProperty("compact", "false")
    st = label.style()
    if st is not None:
        st.unpolish(label)
        st.polish(label)


_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mov"})


def _capture_video_poster_async(
    path: Path,
    max_w: int,
    max_h: int,
    on_done,
) -> None:
    """异步抽视频首帧，避免 QEventLoop 阻塞整窗。"""
    if path.suffix.lower() not in _VIDEO_EXTS:
        QTimer.singleShot(0, lambda: on_done(QPixmap()))
        return
    try:
        from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
    except ImportError:
        QTimer.singleShot(0, lambda: on_done(QPixmap()))
        return

    player = QMediaPlayer()
    sink = QVideoSink()
    player.setVideoSink(sink)
    state = {"done": False}

    def finish(pix: QPixmap | None = None) -> None:
        if state["done"]:
            return
        state["done"] = True
        try:
            player.stop()
        except Exception:
            pass
        player.deleteLater()
        on_done(pix if pix is not None and not pix.isNull() else QPixmap())

    def _on_frame(frame) -> None:
        if state["done"] or not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        pix = QPixmap.fromImage(img).scaled(
            max_w,
            max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        finish(pix)

    sink.videoFrameChanged.connect(_on_frame)
    player.setSource(QUrl.fromLocalFile(str(path.resolve())))
    player.setPosition(120)
    player.play()
    QTimer.singleShot(1500, finish)


def _tune_param_combo(combo: ComboBox, *, min_chars: int = 6, min_width: int = 88) -> None:
    combo.setMinimumWidth(min_width)
    combo.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(min_chars)


class _RefThumb(QFrame):
    remove_requested = Signal(str)

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MediaRefThumb")
        self.setFixedSize(72, 86)
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        img = QLabel()
        img.setObjectName("MediaRefThumbImage")
        img.setFixedSize(56, 36)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setScaledContents(False)
        pix = _fit_pixmap(path, 56, 36)
        if not pix.isNull():
            img.setPixmap(pix)
        else:
            img.setText("?")
        lay.addWidget(img)
        btn = SecondaryButton("移除")
        btn.setObjectName("MediaRefRemoveBtn")
        btn.setFixedHeight(24)
        btn.setMinimumWidth(52)
        btn.clicked.connect(lambda: self.remove_requested.emit(str(self.path)))
        lay.addWidget(btn)


class _WorkTile(QFrame):
    selected = Signal(str)
    _PREVIEW_W = 68
    _PREVIEW_H = 64

    def __init__(self, path: Path, *, defer_thumb: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MediaWorkTile")
        self.setFixedSize(76, 72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(path.name)
        self.path = path
        self._is_video = path.suffix.lower() in _VIDEO_EXTS
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)
        thumb_host = QWidget()
        thumb_host.setFixedSize(self._PREVIEW_W, self._PREVIEW_H)
        preview = QLabel(thumb_host)
        preview.setObjectName("MediaWorkThumb")
        preview.setGeometry(0, 0, self._PREVIEW_W, self._PREVIEW_H)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setScaledContents(False)
        if defer_thumb:
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
                preview.setText("图")
            elif self._is_video:
                preview.setText("视频")
            else:
                preview.setText("?")
        elif path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            pix = _fit_pixmap(path, self._PREVIEW_W, self._PREVIEW_H)
            if not pix.isNull():
                preview.setPixmap(pix)
            else:
                preview.setText("图")
        elif self._is_video:
            preview.setText("视频")
        else:
            preview.setText("?")
        self._preview_label = preview
        self._play_badge = QLabel("▶", thumb_host)
        self._play_badge.setObjectName("MediaWorkPlayBadge")
        self._play_badge.setGeometry(0, 0, self._PREVIEW_W, self._PREVIEW_H)
        self._play_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._play_badge.setVisible(self._is_video)
        lay.addWidget(thumb_host, 0, Qt.AlignmentFlag.AlignCenter)

    def set_poster(self, pix: QPixmap) -> None:
        if pix.isNull():
            return
        try:
            self._preview_label.setPixmap(pix)
            self._preview_label.setText("")
            if self._is_video:
                self._play_badge.show()
                self._play_badge.raise_()
        except RuntimeError:
            return

    def needs_poster(self) -> bool:
        try:
            pix = self._preview_label.pixmap()
            return pix is None or pix.isNull()
        except RuntimeError:
            return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(str(self.path))
        super().mousePressEvent(event)


class _VResizeHandle(QFrame):
    """上下拖动调整预览/作品区高度（不用 QSplitter，避免 Windows 闪退）。"""

    delta_dragged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MediaStudioVHandle")
        self.setFixedHeight(6)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._dragging = False
        self._last_global_y = 0.0

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_global_y = event.globalPosition().y()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            y = event.globalPosition().y()
            dy = int(y - self._last_global_y)
            self._last_global_y = y
            if dy:
                self.delta_dragged.emit(dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _ImagePreviewPane(QLabel):
    """图片预览：滚轮缩放，窗口变化时保持比例；无图时空态同去水印画布。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MediaPreviewImagePane")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWordWrap(True)
        self.setToolTip("滚轮缩放预览 · 双击恢复原始大小")
        self._source: QPixmap | None = None
        self._zoom = 1.0
        self._empty_title = "媒体预览"
        self._empty_subtitle = text or "生成完成后，图片或视频将显示在这里"
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(16)
        self._fit_timer.timeout.connect(self._paint_fit)
        self.setText("")

    def set_placeholder(self, text: str) -> None:
        self._source = None
        self._zoom = 1.0
        self.setPixmap(QPixmap())
        self.setText("")
        # 失败/视频提示：整段作副标题；默认空态用固定标题
        tip = (text or "").strip()
        if tip and "\n" in tip:
            lines = [ln.strip() for ln in tip.splitlines() if ln.strip()]
            self._empty_title = lines[0] if lines else "媒体预览"
            self._empty_subtitle = "\n".join(lines[1:]) if len(lines) > 1 else ""
        elif tip:
            self._empty_title = "媒体预览"
            self._empty_subtitle = tip
        else:
            self._empty_title = "媒体预览"
            self._empty_subtitle = "生成完成后，图片或视频将显示在这里"
        self.update()

    def set_image_path(self, path: Path) -> None:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        src = reader.size()
        if src.isValid() and src.width() > 0 and src.height() > 0:
            max_dim = 2048
            if src.width() > max_dim or src.height() > max_dim:
                fit = src.scaled(max_dim, max_dim, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(fit)
        img = reader.read()
        if img.isNull():
            self.set_placeholder(path.name)
            return
        self._source = QPixmap.fromImage(img)
        self._zoom = 1.0
        self.setText("")
        self._paint_fit()

    def source_pixmap(self) -> QPixmap | None:
        return self._source

    def reset_zoom(self) -> None:
        if self._source is None or self._source.isNull():
            return
        self._zoom = 1.0
        self._paint_fit()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._source is None or self._source.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            paint_empty_preview_canvas(
                self,
                painter,
                title=self._empty_title,
                subtitle=self._empty_subtitle,
            )
            painter.end()
            return
        super().paintEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._source is None or self._source.isNull():
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        step = 1.12 if delta > 0 else 1.0 / 1.12
        self._zoom = max(0.25, min(5.0, self._zoom * step))
        self._paint_fit()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_zoom()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source is not None and not self._source.isNull():
            self._fit_timer.start()

    def _paint_fit(self) -> None:
        if self._source is None or self._source.isNull():
            return
        pad = 24
        w = max(1, self.width() - pad)
        h = max(1, self.height() - pad)
        base = self._source.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if abs(self._zoom - 1.0) > 0.01:
            nw = max(1, int(base.width() * self._zoom))
            nh = max(1, int(base.height() * self._zoom))
            out = base.scaled(
                nw,
                nh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            out = base
        self.setPixmap(out)


class _PreviewCanvas(QWidget):
    """主预览：图片缩放 + 内嵌视频播放。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MediaPreviewCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(240)
        self.setToolTip("图片可滚轮缩放 · 视频可直接预览")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        self._image = _ImagePreviewPane(text)
        self._stack.addWidget(self._image)
        self._video_wrap = QWidget()
        video_lay = QVBoxLayout(self._video_wrap)
        video_lay.setContentsMargins(0, 0, 0, 0)
        self._player = None
        self._audio = None
        self._video_widget = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self._video_widget = QVideoWidget()
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._audio = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self._video_widget)
            video_lay.addWidget(self._video_widget, 1)
            self._stack.addWidget(self._video_wrap)
        except ImportError:
            self._video_wrap = None
        outer.addWidget(self._stack, 1)
        self._stack.setCurrentWidget(self._image)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(480, 360)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(240, 240)

    def _stop_video(self) -> None:
        if self._player is not None:
            self._player.stop()

    def set_placeholder(self, text: str) -> None:
        self._stop_video()
        self._stack.setCurrentWidget(self._image)
        self._image.set_placeholder(text)

    def set_video_hint(self, text: str) -> None:
        self.set_placeholder(text)

    def set_video_path(self, path: Path) -> None:
        if self._player is None or self._video_wrap is None:
            self.set_video_hint(
                f"视频已就绪\n{path.name}\n当前环境不支持内嵌播放，请点「播放」用系统播放器观看"
            )
            return
        self._stack.setCurrentWidget(self._video_wrap)
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._player.play()

    def set_image_path(self, path: Path) -> None:
        self._stop_video()
        self._stack.setCurrentWidget(self._image)
        self._image.set_image_path(path)

    def source_pixmap(self) -> QPixmap | None:
        return self._image.source_pixmap()

    def is_video_mode(self) -> bool:
        return (
            self._player is not None
            and self._video_wrap is not None
            and self._stack.currentWidget() is self._video_wrap
        )

    def toggle_playback(self) -> None:
        if self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def stop_media(self) -> None:
        self._stop_video()


class _TaskRow(QFrame):
    cancel_requested = Signal(str)
    preview_requested = Signal(str)

    def __init__(self, task: MediaGenTask, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MediaTaskRow")
        self.task_id = task.id
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(3)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._title = HintLabel("")
        self._title.setWordWrap(False)
        self._title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        head.addWidget(self._title, 1)
        self._state = SemanticLabel("", kind="info", compact=True)
        head.addWidget(self._state, 0)
        lay.addLayout(head)

        self._prompt = HintLabel("")
        self._prompt.setWordWrap(False)
        self._prompt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(self._prompt)

        self._bar = ProgressBar()
        self._bar.setObjectName("MediaTaskProgress")
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        lay.addWidget(self._bar)

        foot = QHBoxLayout()
        foot.setSpacing(4)
        self._msg = HintLabel("")
        self._msg.setWordWrap(False)
        self._msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        foot.addWidget(self._msg, 1)
        self._btn_cancel = SecondaryButton("取消")
        self._btn_cancel.setFixedSize(44, 22)
        self._btn_cancel.clicked.connect(lambda: self.cancel_requested.emit(self.task_id))
        foot.addWidget(self._btn_cancel)
        self._btn_view = SecondaryButton("预览")
        self._btn_view.setFixedSize(44, 22)
        self._btn_view.clicked.connect(lambda: self.preview_requested.emit(self.task_id))
        foot.addWidget(self._btn_view)
        lay.addLayout(foot)
        self.apply_task(task)

    def apply_task(self, task: MediaGenTask) -> None:
        self._title.setText(_clip_line(task.spec.label or "生成任务", 28))
        snippet = _clip_line(task.spec.prompt, 56)
        self._prompt.setText(snippet)
        self._prompt.setVisible(bool(snippet))

        running = task.status == "running"
        pending = task.status == "pending"
        done = task.status == "completed"
        failed = task.status == "failed"
        cancelled = task.status == "cancelled"

        if pending:
            _set_semantic(self._state, "info", "排队", compact=True)
        elif running:
            _set_semantic(self._state, "warning", "运行", compact=True)
        elif done:
            _set_semantic(self._state, "success", "完成", compact=True)
        elif failed:
            _set_semantic(self._state, "danger", "失败", compact=True)
        else:
            _set_semantic(self._state, "info", "取消", compact=True)

        self._btn_cancel.setVisible(pending or running)
        self._btn_view.setVisible(done and bool(task.result_path))

        if task.indeterminate or task.status in ("pending", "running") and task.progress <= 0:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, 100)
            self._bar.setValue(max(0, min(100, task.progress)))
        msg = task.message or ""
        if running and task.progress > 0 and not task.indeterminate:
            msg = f"{task.progress}% · {msg}" if msg else f"{task.progress}%"
        self._msg.setText(_clip_line(msg, 40))


class MediaStudioPage(BasePage):
    page_id = "media_studio"
    page_title = "媒体工坊"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._kind = _KIND_IMAGE
        self._img_mode = _IMG_TXT
        self._ref_paths: list[Path] = []
        self._image_profiles: list[dict] = []
        self._video_profiles: list[dict] = []
        self._queue = MediaGenQueueController(self)
        self._task_rows: dict[str, _TaskRow] = {}
        self._last_enqueue_batch = 1
        self._result_path: Path | None = None
        self._selected_work: Path | None = None
        self._work_tiles: list[_WorkTile] = []
        self._ratio_key = "1:1"
        self._image_res = "2K"
        self._video_ratio = "16:9"
        self._video_res = "720p"
        self._video_dur = 5
        self._generate_audio = True
        self._web_search = False
        self._image_quality = "medium"
        self._image_n = 1
        self._aspect_w = 1024
        self._aspect_h = 1024
        self._enter_models_ready = False
        self._model_combo_width_applied = False
        self._works_panel_height = 152
        self._poster_jobs: list[tuple[_WorkTile, Path]] = []
        self._video_poster_jobs: list[tuple[_WorkTile, Path]] = []
        self._works_reload_gen = 0
        self._works_sig_cache: tuple[tuple[str, float], ...] | None = None
        self._pending_kind_index = 0
        self._kind_switch_timer = QTimer(self)
        self._kind_switch_timer.setSingleShot(True)
        self._kind_switch_timer.setInterval(60)
        self._kind_switch_timer.timeout.connect(self._apply_kind_switch)

        self._ui_ready = False
        self._ui_build_started = False

        m = page_content_margins()
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(*m)
        self._root.setSpacing(8)
        self._boot_hint = HintLabel(
            "正在打开媒体工坊…\n可随时点其它菜单离开，无需等待。"
        )
        self._boot_hint.setWordWrap(True)
        self._boot_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addStretch(1)
        self._root.addWidget(self._boot_hint)
        self._root.addStretch(1)

    def request_deferred_ui(self) -> None:
        """壳层/进页调用：分块建完整 UI，中间让出事件循环以便立刻点走。"""
        if self._ui_ready or self._ui_build_started:
            return
        self._ui_build_started = True
        QTimer.singleShot(0, self._build_ui_phase1)

    def _clear_boot_skeleton(self) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._boot_hint = None

    def _build_ui_phase1(self) -> None:
        if self._ui_ready:
            return
        self._clear_boot_skeleton()
        root = self._root

        head = QHBoxLayout()
        head.addWidget(
            PageHeader("媒体工坊", "文生图 / 图生图 / 短视频"),
            1,
        )

        def _make_model_combo() -> ComboBox:
            combo = ComboBox()
            combo.setMinimumWidth(260)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setSizeAdjustPolicy(
                ComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.currentIndexChanged.connect(self._on_model_changed)
            return combo

        self._image_model_combo = _make_model_combo()
        self._video_model_combo = _make_model_combo()
        self._model_combo_stack = QStackedWidget()
        self._model_combo_stack.addWidget(self._image_model_combo)
        self._model_combo_stack.addWidget(self._video_model_combo)
        head.addWidget(self._model_combo_stack, 1)
        self._btn_tasks = SecondaryButton("任务")
        self._btn_tasks.setCheckable(True)
        self._btn_tasks.setMinimumWidth(72)
        self._btn_tasks.clicked.connect(self._toggle_task_panel)
        head.addWidget(self._btn_tasks)
        btn_simple = SecondaryButton("简单配置…")
        btn_simple.setToolTip("本机生图一键安装（≤2 步）；云端 Key 走「高级」")
        btn_simple.clicked.connect(self._open_simple_setup)
        head.addWidget(btn_simple)
        btn_models = SecondaryButton("高级…")
        btn_models.setToolTip("系统设置 · 模型管理（完整表单）")
        btn_models.clicked.connect(self._open_model_settings)
        head.addWidget(btn_models)
        root.addLayout(head)

        self._empty_models = HintLabel("")
        self._empty_models.setWordWrap(True)
        self._empty_models.setVisible(False)
        root.addWidget(self._empty_models)

        self._model_note = HintLabel("")
        self._model_note.setWordWrap(True)
        self._model_note.setVisible(False)
        root.addWidget(self._model_note)

        body_row = QWidget()
        self._body_row = body_row
        body_lay = QHBoxLayout(body_row)
        self._body_lay = body_lay
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(8)
        root.addWidget(body_row, 1)

        # —— 左侧创作栈 ——
        left = QFrame()
        left.setObjectName("MediaStudioLeft")
        left.setFixedWidth(328)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 6, 8, 8)
        left_lay.setSpacing(4)

        left_body = QWidget()
        left_body_lay = QVBoxLayout(left_body)
        left_body_lay.setContentsMargins(0, 0, 0, 0)
        left_body_lay.setSpacing(5)

        self._kind_tabs = TabWidget()
        self._kind_tabs.addTab(QWidget(), "图片创作")
        self._kind_tabs.addTab(QWidget(), "视频创作")
        left_body_lay.addWidget(self._kind_tabs)

        self._mode_block = QWidget()
        mode_lay = QVBoxLayout(self._mode_block)
        mode_lay.setContentsMargins(0, 2, 0, 0)
        mode_lay.setSpacing(4)
        mode_lay.addWidget(SectionTitle("玩法"))
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        self._img_mode_group = QButtonGroup(self)
        self._rb_txt = RadioButton("文生图")
        self._rb_ref = RadioButton("图生图")
        self._rb_fuse = RadioButton("多图融合")
        self._rb_txt.setChecked(True)
        self._img_mode_group.addButton(self._rb_txt, 0)
        self._img_mode_group.addButton(self._rb_ref, 1)
        self._img_mode_group.addButton(self._rb_fuse, 2)
        self._img_mode_group.idClicked.connect(self._on_img_mode_id)
        mode_row.addWidget(self._rb_txt)
        mode_row.addWidget(self._rb_ref)
        mode_row.addWidget(self._rb_fuse)
        mode_row.addStretch(1)
        mode_lay.addLayout(mode_row)
        left_body_lay.addWidget(self._mode_block)

        left_body_lay.addWidget(SectionTitle("参考图"))
        ref_tools = QHBoxLayout()
        ref_tools.setSpacing(6)
        self._btn_ref = SecondaryButton("添加参考")
        self._btn_ref.clicked.connect(self._add_refs)
        ref_tools.addWidget(self._btn_ref, 1)
        self._btn_clear_ref = SecondaryButton("清空")
        self._btn_clear_ref.clicked.connect(self._clear_refs)
        ref_tools.addWidget(self._btn_clear_ref, 1)
        left_body_lay.addLayout(ref_tools)

        ref_scroll = QScrollArea()
        ref_scroll.setObjectName("MediaStudioRefScroll")
        ref_scroll.setWidgetResizable(True)
        ref_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        ref_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ref_scroll.setFixedHeight(90)
        self._thumbs_host = QWidget()
        self._thumbs_lay = QHBoxLayout(self._thumbs_host)
        self._thumbs_lay.setContentsMargins(0, 0, 0, 0)
        self._thumbs_lay.setSpacing(8)
        ref_scroll.setWidget(self._thumbs_host)
        left_body_lay.addWidget(ref_scroll)

        left_body_lay.addWidget(SectionTitle("创意描述"))
        self._prompt = PlainTextEdit()
        self._prompt.setObjectName("MediaStudioPrompt")
        self._prompt.setFixedHeight(80)
        self._prompt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._prompt.setPlaceholderText(
            "写清主体、风格、镜头运动或要改动的细节…\n"
            "图生图 / 多图融合 / 视频首帧需先添加参考图。"
        )
        left_body_lay.addWidget(self._prompt)
        left_body_lay.addSpacing(8)

        self._image_params = QWidget()
        img_param_lay = QVBoxLayout(self._image_params)
        img_param_lay.setContentsMargins(0, 0, 0, 0)
        img_param_lay.setSpacing(4)
        img_param_lay.addWidget(SectionTitle("图片参数"))
        param_grid = QGridLayout()
        param_grid.setContentsMargins(0, 0, 0, 0)
        param_grid.setHorizontalSpacing(6)
        param_grid.setVerticalSpacing(4)
        param_grid.setColumnStretch(0, 1)
        param_grid.setColumnStretch(1, 1)
        self._ratio_combo = ComboBox()
        for label, key, w, h in _IMAGE_RATIOS:
            self._ratio_combo.addItem(label if key == "smart" else label, (key, w, h))
        self._ratio_combo.currentIndexChanged.connect(self._on_image_ratio)
        _tune_param_combo(self._ratio_combo, min_chars=8, min_width=92)
        self._ratio_combo.setToolTip("画幅比例")
        param_grid.addWidget(FormRow("画幅", self._ratio_combo, label_width=44), 0, 0)

        self._res_combo = ComboBox()
        for r in ("1K", "2K"):
            self._res_combo.addItem(r, r)
        self._res_combo.setCurrentIndex(1)
        self._res_combo.currentIndexChanged.connect(self._on_image_res)
        _tune_param_combo(self._res_combo, min_chars=4, min_width=72)
        self._seedream_res_row = FormRow("分辨率", self._res_combo, label_width=44)
        param_grid.addWidget(self._seedream_res_row, 0, 1)

        self._evo_res = ComboBox()
        for r in ("1K", "2K"):
            self._evo_res.addItem(r, r)
        self._evo_res.setCurrentIndex(1)
        self._evo_res.currentIndexChanged.connect(self._on_evo_res)
        _tune_param_combo(self._evo_res, min_chars=4, min_width=72)
        self._evo_res_row = FormRow("分辨率", self._evo_res, label_width=44)
        self._evo_res_row.setVisible(False)
        param_grid.addWidget(self._evo_res_row, 0, 1)

        self._evo_quality = ComboBox()
        self._evo_quality.addItem("标准", "medium")
        self._evo_quality.addItem("快速", "low")
        self._evo_quality.currentIndexChanged.connect(self._on_evo_quality)
        _tune_param_combo(self._evo_quality, min_chars=4, min_width=72)
        self._evo_quality_row = FormRow("画质", self._evo_quality, label_width=44)
        self._evo_quality_row.setVisible(False)
        param_grid.addWidget(self._evo_quality_row, 1, 0)

        n_row = QWidget()
        n_lay = QHBoxLayout(n_row)
        n_lay.setContentsMargins(0, 0, 0, 0)
        n_lay.setSpacing(4)
        self._evo_n = SpinBox()
        self._evo_n.setMinimum(1)
        self._evo_n.setMaximum(4)
        self._evo_n.setValue(1)
        self._evo_n.setFixedWidth(52)
        self._evo_n.valueChanged.connect(self._on_evo_n)
        n_lay.addWidget(self._evo_n)
        n_lay.addWidget(HintLabel("张"))
        n_lay.addStretch(1)
        self._evo_n_row = FormRow("张数", n_row, label_width=44)
        self._evo_n_row.setVisible(False)
        param_grid.addWidget(self._evo_n_row, 1, 1)

        img_param_lay.addLayout(param_grid)
        self._on_image_ratio(self._ratio_combo.currentIndex())

        self._video_params = QWidget()
        self._video_params.setMinimumHeight(248)
        vid_param_lay = QVBoxLayout(self._video_params)
        vid_param_lay.setContentsMargins(0, 4, 0, 0)
        vid_param_lay.setSpacing(10)
        vid_param_lay.addWidget(SectionTitle("视频参数"))
        vid_form = QVBoxLayout()
        vid_form.setContentsMargins(0, 0, 0, 0)
        vid_form.setSpacing(10)

        def _vid_row(label: str, field: QWidget) -> FormRow:
            row = FormRow(label, field, label_width=44)
            row.setMinimumHeight(32)
            return row

        self._v_ratio = ComboBox()
        for r in _VIDEO_RATIOS:
            val = "adaptive" if r == "自适应" else r
            self._v_ratio.addItem(r, val)
        self._v_ratio.currentIndexChanged.connect(self._on_video_ratio)
        _tune_param_combo(self._v_ratio, min_chars=6, min_width=92)
        vid_form.addWidget(_vid_row("比例", self._v_ratio))
        self._v_res = ComboBox()
        for r in _VIDEO_RES:
            self._v_res.addItem(r.upper(), r)
        self._v_res.setCurrentIndex(1)
        self._v_res.currentIndexChanged.connect(self._on_video_res)
        _tune_param_combo(self._v_res, min_chars=4, min_width=72)
        vid_form.addWidget(_vid_row("清晰度", self._v_res))
        dur_row = QWidget()
        dur_lay = QHBoxLayout(dur_row)
        dur_lay.setContentsMargins(0, 0, 0, 0)
        dur_lay.setSpacing(8)
        self._dur_slider = Slider(minimum=4, maximum=15, value=5)
        self._dur_slider.setTickInterval(1)
        self._dur_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._dur_slider.valueChanged.connect(self._on_video_dur_slider)
        dur_lay.addWidget(self._dur_slider, 1)
        self._dur_label = HintLabel("5s")
        self._dur_label.setFixedWidth(28)
        dur_lay.addWidget(self._dur_label)
        vid_form.addWidget(_vid_row("时长", dur_row))
        vid_param_lay.addLayout(vid_form)

        switch_box = QWidget()
        switch_lay = QVBoxLayout(switch_box)
        switch_lay.setContentsMargins(0, 0, 0, 0)
        switch_lay.setSpacing(8)
        self._sw_audio = Switch("生成音频")
        self._sw_audio.setChecked(True)
        self._sw_audio.toggled.connect(self._on_audio_toggle)
        switch_lay.addWidget(self._sw_audio)
        self._sw_web = Switch("联网搜索（仅文生视频）")
        self._sw_web.toggled.connect(self._on_web_toggle)
        switch_lay.addWidget(self._sw_web)
        vid_param_lay.addWidget(switch_box)

        self._video_hint = HintLabel(
            "Seedance 2.0：写镜头描述即可；加 1 张图作首帧，或 2 张作首尾帧。"
            "生成链接 24 小时有效，请及时保存。"
        )
        self._video_hint.setWordWrap(True)
        self._video_hint.setMinimumHeight(44)
        vid_param_lay.addWidget(self._video_hint)

        self._image_kind_page = QWidget()
        img_kind_lay = QVBoxLayout(self._image_kind_page)
        img_kind_lay.setContentsMargins(0, 0, 0, 0)
        img_kind_lay.setSpacing(4)
        img_kind_lay.addWidget(self._image_params)

        left_body_lay.addWidget(self._image_kind_page)
        left_body_lay.addWidget(self._video_params)

        left_body_lay.addSpacing(6)
        self._hint = HintLabel("文生图：写清主体、风格与构图即可。")
        self._hint.setWordWrap(True)
        left_body_lay.addWidget(self._hint)

        left_scroll = QScrollArea()
        left_scroll.setObjectName("MediaStudioLeftScroll")
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setWidget(left_body)
        left_lay.addWidget(left_scroll, 1)

        self._left_footer = QFrame()
        self._left_footer.setObjectName("MediaStudioFooter")
        footer_lay = QVBoxLayout(self._left_footer)
        footer_lay.setContentsMargins(0, 6, 0, 0)
        footer_lay.setSpacing(6)

        batch_row = QHBoxLayout()
        batch_row.addWidget(HintLabel("批次"))
        self._batch_spin = SpinBox()
        self._batch_spin.setMinimum(1)
        self._batch_spin.setMaximum(8)
        self._batch_spin.setValue(1)
        self._batch_spin.setFixedWidth(72)
        batch_row.addWidget(self._batch_spin)
        batch_row.addStretch(1)
        footer_lay.addLayout(batch_row)

        self._btn_gen = PrimaryButton("运行")
        self._btn_gen.setMinimumHeight(32)
        self._btn_gen.clicked.connect(self._on_generate)
        gen_row = QHBoxLayout()
        gen_row.addWidget(self._btn_gen, 1)
        footer_lay.addLayout(gen_row)

        self._status_line = HintLabel("加入任务后点顶栏「任务」查看进度。")
        self._status_line.setWordWrap(True)
        footer_lay.addWidget(self._status_line)
        left_lay.addWidget(self._left_footer, 0)

        body_lay.addWidget(left, 0)

        QTimer.singleShot(0, self._build_ui_phase2)

    def _build_ui_phase2(self) -> None:
        if self._ui_ready:
            return
        # —— 右侧：预览 + 可选任务侧栏（不用 QSplitter，避免 Windows 上 OverflowError 闪退）——
        self._right_row = QWidget()
        right_row_lay = QHBoxLayout(self._right_row)
        right_row_lay.setContentsMargins(0, 0, 0, 0)
        right_row_lay.setSpacing(8)

        preview_col = QWidget()
        preview_top = QWidget()
        preview_top.setMinimumHeight(220)
        top_lay = QVBoxLayout(preview_top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(6)

        self._stage = QFrame()
        self._stage.setObjectName("MediaStudioStage")
        stage_lay = QVBoxLayout(self._stage)
        stage_lay.setContentsMargins(8, 8, 8, 8)
        self._preview = _PreviewCanvas("生成完成后，图片或视频将显示在这里")
        stage_lay.addWidget(self._preview, 1)
        top_lay.addWidget(self._stage, 1)

        meta = QHBoxLayout()
        self._result_meta = HintLabel("尚未生成")
        meta.addWidget(self._result_meta, 1)
        self._btn_copy = SecondaryButton("复制")
        self._btn_copy.setEnabled(False)
        self._btn_copy.setToolTip("复制当前图片到剪贴板")
        self._btn_copy.clicked.connect(self._copy_result)
        meta.addWidget(self._btn_copy)
        self._btn_open = SecondaryButton("打开目录")
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_result)
        meta.addWidget(self._btn_open)
        self._btn_play = SecondaryButton("播放")
        self._btn_play.setEnabled(False)
        self._btn_play.setToolTip("播放/暂停内嵌预览，或系统播放器打开")
        self._btn_play.clicked.connect(self._play_result)
        meta.addWidget(self._btn_play)
        top_lay.addLayout(meta)

        self._works_block = QFrame()
        self._works_block.setObjectName("MediaWorksBlock")
        self._works_block.setMinimumHeight(96)
        self._works_block.setFixedHeight(self._works_panel_height)
        works_block_lay = QVBoxLayout(self._works_block)
        works_block_lay.setContentsMargins(0, 4, 0, 0)
        works_block_lay.setSpacing(4)
        hist_head = QHBoxLayout()
        hist_head.addWidget(SectionTitle("最近作品"), 1)
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(lambda: self._reload_works_if_needed(force=True, poster_videos=True))
        hist_head.addWidget(btn_refresh)
        works_block_lay.addLayout(hist_head)

        film_scroll = QScrollArea()
        film_scroll.setObjectName("MediaStudioFilmScroll")
        film_scroll.setWidgetResizable(True)
        film_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        film_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        film_scroll.setMinimumHeight(88)
        self._works_host = QWidget()
        self._works_lay = QHBoxLayout(self._works_host)
        self._works_lay.setContentsMargins(0, 0, 0, 0)
        self._works_lay.setSpacing(6)
        film_scroll.setWidget(self._works_host)
        works_block_lay.addWidget(film_scroll, 1)

        self._v_handle = _VResizeHandle()
        self._v_handle.delta_dragged.connect(self._on_works_panel_drag)

        right_lay = QVBoxLayout(preview_col)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        right_lay.addWidget(preview_top, 1)
        right_lay.addWidget(self._v_handle, 0)
        right_lay.addWidget(self._works_block, 0)

        right_row_lay.addWidget(preview_col, 1)

        task_panel = QFrame()
        task_panel.setObjectName("MediaTaskPanel")
        self._task_panel = task_panel
        self._task_panel.setFixedWidth(280)
        self._task_panel.setVisible(False)
        task_lay = QVBoxLayout(task_panel)
        task_lay.setContentsMargins(8, 8, 8, 8)
        task_lay.setSpacing(6)
        task_head = QHBoxLayout()
        task_head.addWidget(SectionTitle("任务"), 1)
        self._task_badge = SemanticLabel("无活动", kind="info", compact=True)
        task_head.addWidget(self._task_badge)
        task_lay.addLayout(task_head)

        task_tools = QHBoxLayout()
        task_tools.setSpacing(6)
        btn_cancel_run = SecondaryButton("取消")
        btn_cancel_run.clicked.connect(self._cancel_running)
        task_tools.addWidget(btn_cancel_run)
        btn_clear_wait = SecondaryButton("清等待")
        btn_clear_wait.clicked.connect(self._queue.clear_pending)
        task_tools.addWidget(btn_clear_wait)
        btn_clear_done = SecondaryButton("清完成")
        btn_clear_done.clicked.connect(self._clear_finished_tasks)
        task_tools.addWidget(btn_clear_done)
        task_tools.addStretch(1)
        task_lay.addLayout(task_tools)

        self._task_scroll = QScrollArea()
        self._task_scroll.setWidgetResizable(True)
        self._task_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._task_host = QWidget()
        self._task_lay = QVBoxLayout(self._task_host)
        self._task_lay.setContentsMargins(0, 0, 0, 0)
        self._task_lay.setSpacing(6)
        self._task_empty = HintLabel("暂无任务")
        self._task_lay.addWidget(self._task_empty)
        self._task_lay.addStretch(1)
        self._task_scroll.setWidget(self._task_host)
        task_lay.addWidget(self._task_scroll, 1)
        right_row_lay.addWidget(self._task_panel, 0)

        self._body_lay.addWidget(self._right_row, 1)

        self._apply_kind_ui()
        self._kind_tabs.currentChanged.connect(self._on_kind_tab)
        self._queue.task_updated.connect(self._on_task_updated)
        self._queue.queue_changed.connect(self._refresh_task_badge)
        self._ui_ready = True
        self.apply_page_focus_policy()
        if self._page_is_active():
            self._schedule_enter_data()


    def primary_focus_widget(self):
        if not self._ui_ready:
            return None
        return self._prompt

    def focus_tab_widgets(self) -> list[QWidget]:
        if not self._ui_ready:
            return []
        return [
            self._prompt,
            self._btn_ref,
            self._btn_clear_ref,
            self._btn_gen,
            self._btn_copy,
            self._btn_open,
            self._btn_play,
        ]

    def _active_model_combo(self) -> ComboBox:
        return self._video_model_combo if self._kind == _KIND_VIDEO else self._image_model_combo

    def _set_result_actions(self, path: Path) -> None:
        if not self._ui_ready:
            return
        is_video = path.suffix.lower() in (".mp4", ".webm", ".mov")
        self._btn_open.setEnabled(True)
        self._btn_play.setEnabled(is_video)
        self._btn_copy.setEnabled(not is_video)

    def _on_works_panel_drag(self, dy: int) -> None:
        if not self._ui_ready:
            return
        # 向下拖 = 预览区变大 → 作品条高度减小
        new_h = max(96, min(320, self._works_block.height() - dy))
        if new_h == self._works_block.height():
            return
        self._works_panel_height = new_h
        self._works_block.setFixedHeight(new_h)

    def _init_models_once(self) -> None:
        if not self._ui_ready or self._enter_models_ready:
            return
        # 先进图片模型（当前默认 tab），视频模型滞后，减轻首进卡顿
        self._reload_models(
            select_active=True,
            refresh_cache=True,
            capabilities=("image_gen",),
            persist_pick=False,
        )
        self._enter_models_ready = True
        QTimer.singleShot(350, self._deferred_load_video_models)

    def _deferred_load_video_models(self) -> None:
        if not self._ui_ready or not self._page_is_active():
            return
        self._reload_models(
            select_active=True,
            refresh_cache=True,
            capabilities=("video_gen",),
            persist_pick=True,
        )

    def prewarm_enter(self) -> None:
        """壳层空闲预建：先分块 UI，再轻量刷图片模型。"""
        self.request_deferred_ui()
        if not self._ui_ready or self._enter_models_ready:
            return
        self._init_models_once()

    def _schedule_enter_data(self) -> None:
        """UI 就绪后灌模型/作品；可被 on_enter 与建页收尾共用。"""
        if not self._ui_ready:
            return
        if self._enter_models_ready:
            QTimer.singleShot(2400, self._ensure_video_posters_if_active)
            QTimer.singleShot(450, self._deferred_reload_works_if_active)
            return
        QTimer.singleShot(50, self._bootstrap_models_deferred)
        QTimer.singleShot(420, self._bootstrap_works_deferred)

    def on_enter(self) -> None:
        self.report_status("媒体工坊")
        self.request_deferred_ui()
        if self._ui_ready:
            self._schedule_enter_data()

    def _bootstrap_models_deferred(self) -> None:
        if not self._ui_ready or not self._page_is_active() or self._enter_models_ready:
            return
        self._init_models_once()

    def _bootstrap_works_deferred(self) -> None:
        if not self._ui_ready or not self._page_is_active():
            return
        self._show_works_loading_hint()
        self._reload_works_if_needed()

    def _deferred_reload_works_if_active(self) -> None:
        if not self._page_is_active():
            return
        self._reload_works_if_needed()

    def _show_works_loading_hint(self) -> None:
        if self._work_tiles or self._works_sig_cache is not None:
            return
        while self._works_lay.count():
            item = self._works_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._works_lay.addWidget(HintLabel("正在加载最近作品…"))
        self._works_lay.addStretch(1)

    def _page_is_active(self) -> bool:
        shell = self.window()
        return shell is not None and getattr(shell, "_current_id", None) == "media_studio"

    def _ensure_video_posters_if_active(self) -> None:
        if not self._page_is_active():
            return
        self._ensure_video_posters()

    def _ensure_video_posters(self) -> None:
        """进页不阻塞；稍后补视频首帧缩略图。"""
        if not self._page_is_active():
            return
        pending = [
            (tile, tile.path)
            for tile in self._work_tiles
            if tile._is_video and tile.needs_poster()
        ]
        if not pending:
            return
        self._video_poster_jobs = pending
        gen = self._works_reload_gen
        QTimer.singleShot(600, lambda g=gen: self._run_next_video_poster_job(g))

    def _bootstrap_enter(self) -> None:
        """兼容旧调用：模型 + 作品分批。"""
        if self._enter_models_ready:
            return
        self._init_models_once()
        QTimer.singleShot(350, self._bootstrap_works_deferred)

    def on_leave(self) -> None:
        if self._ui_ready and hasattr(self, "_preview"):
            self._preview.stop_media()
        self._works_reload_gen += 1

    def _deferred_reload_works(self) -> None:
        self._reload_works()

    def _open_model_settings(self) -> None:
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            shell.navigate("system_settings")
            page = getattr(shell, "_pages", {}).get("system_settings")
            if page is not None and hasattr(page, "open_models_tab"):
                page.open_models_tab()
            elif page is not None and hasattr(page, "open_model_hub_tab"):
                page.open_model_hub_tab()

    def _open_simple_setup(self) -> None:
        """探索路径：图片优先一键装本机生图；视频引导高级绑定。"""
        if self._kind == _KIND_VIDEO:
            from core.user_messages import ask_confirm

            if ask_confirm(
                self,
                "视频算力通常需云端 Key。\n"
                "下一步打开「模型管理」：① 选视频来源 ② 粘贴 Key 保存。\n"
                "也可稍后再说，先浏览本页。",
                title="简单配置 · 视频",
            ):
                self._open_model_settings()
            return
        from modules.system_settings.local_image_setup_dialog import LocalImageSetupDialog

        dlg = LocalImageSetupDialog(self)
        dlg.exec()
        self._reload_models(select_active=True, refresh_cache=True)
        if dlg.ready:
            self.report_status("本机生图已就绪", level=StatusLevel.SUCCESS)

    def _on_kind_tab(self, index: int) -> None:
        self._pending_kind_index = int(index)
        self._kind_switch_timer.start()

    def _apply_kind_switch(self) -> None:
        index = self._pending_kind_index
        new_kind = _KIND_VIDEO if index == 1 else _KIND_IMAGE
        if new_kind == self._kind:
            return
        self._kind = new_kind
        self._model_combo_stack.setCurrentIndex(0 if new_kind == _KIND_IMAGE else 1)
        self._apply_kind_ui()
        self._sync_empty_models_hint()

    def _on_img_mode_id(self, index: int) -> None:
        self._img_mode = (_IMG_TXT, _IMG_REF, _IMG_FUSE)[index]
        self._apply_kind_ui()
        self._sync_image_param_panels()

    def _apply_kind_ui(self) -> None:
        is_img = self._kind == _KIND_IMAGE
        self._mode_block.setVisible(is_img)
        self._image_kind_page.setVisible(is_img)
        self._video_params.setVisible(not is_img)
        self._hint.setVisible(is_img)
        if is_img:
            self._sync_image_param_panels()
            self._btn_gen.setText("运行 · 生图")
            self._btn_ref.setText("添加参考")
        else:
            self._btn_gen.setText("运行 · 视频")
            self._sw_web.setEnabled(len(self._ref_paths) == 0)
            self._btn_ref.setText("添加首帧")
            self._sync_model_note()

    def _on_image_ratio(self, index: int) -> None:
        data = self._ratio_combo.itemData(index)
        if isinstance(data, tuple) and len(data) == 3:
            self._ratio_key, self._aspect_w, self._aspect_h = data[0], int(data[1]), int(data[2])
        if index >= 0:
            self._ratio_combo.setToolTip(self._ratio_combo.itemText(index))

    def _on_image_res(self, index: int) -> None:
        self._image_res = str(self._res_combo.itemData(index) or "2K")

    def _on_evo_res(self, index: int) -> None:
        self._image_res = str(self._evo_res.itemData(index) or "2K")

    def _on_evo_quality(self, index: int) -> None:
        self._image_quality = str(self._evo_quality.itemData(index) or "medium")

    def _on_evo_n(self, value: int) -> None:
        self._image_n = max(1, min(4, int(value)))

    def _on_video_ratio(self, index: int) -> None:
        self._video_ratio = str(self._v_ratio.itemData(index) or "16:9")

    def _on_video_res(self, index: int) -> None:
        self._video_res = str(self._v_res.itemData(index) or "720p")

    def _on_video_dur_slider(self, value: int) -> None:
        self._video_dur = int(value)
        self._dur_label.setText(f"{value}s")

    def _on_audio_toggle(self, checked: bool) -> None:
        self._generate_audio = bool(checked)

    def _on_web_toggle(self, checked: bool) -> None:
        self._web_search = bool(checked)

    def _current_profile_row(self) -> dict | None:
        pid = self._current_profile_id()
        if not pid:
            return None
        rows = self._video_profiles if self._kind == _KIND_VIDEO else self._image_profiles
        for p in rows:
            if str(p.get("id") or "") == pid:
                return p
        return None

    def _sync_model_note(self) -> None:
        prof = self._current_profile_row()
        note = str((prof or {}).get("note") or "").strip()
        if note:
            self._model_note.setText(note)
            self._model_note.setVisible(True)
        else:
            self._model_note.clear()
            self._model_note.setVisible(False)

    def _sync_image_param_panels(self) -> None:
        if self._kind != _KIND_IMAGE:
            self._sync_model_note()
            return
        prof = self._current_profile_row()
        pid = self._current_profile_id()
        evolink = is_evolink_image_profile(prof, pid)
        self._sync_model_note()
        self._seedream_res_row.setVisible(not evolink)
        self._evo_res_row.setVisible(evolink)
        self._evo_quality_row.setVisible(evolink)
        self._evo_n_row.setVisible(evolink)
        if evolink:
            if self._img_mode == _IMG_REF:
                self._hint.setText("Grok 图生图：1～3 张参考图；写清要保留或修改的内容。")
            elif self._img_mode == _IMG_FUSE:
                self._hint.setText("Grok 参考编辑：1～3 张参考图（更多张数请用 Seedream）。")
            else:
                self._hint.setText("Grok 文生图：写清主体与风格；可调分辨率、画质与单次张数。")
        elif is_volcengine_image_profile(prof, pid):
            if self._img_mode == _IMG_REF:
                self._hint.setText("Seedream 图生图：1 张参考图 + 修改说明。")
            elif self._img_mode == _IMG_FUSE:
                self._hint.setText("Seedream 多图融合：2～10 张参考图。")
            else:
                self._hint.setText("Seedream 文生图：写清主体、风格与构图。")
        else:
            if self._img_mode == _IMG_REF:
                self._hint.setText("图生图：添加参考图并说明要改什么。")
            elif self._img_mode == _IMG_FUSE:
                self._hint.setText("多图融合：添加多张参考图并说明合成方式。")
            else:
                self._hint.setText("文生图：写清主体、风格与构图；无需参考图。")

    def _fill_grouped_model_combo(
        self,
        combo: ComboBox,
        profiles: list[dict],
        *,
        select_id: str = "",
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        select_index = -1
        if not profiles:
            combo.addItem("（无可用模型）", "")
            combo.addItem("＋ 简单配置…", "__bind__")
        else:
            idx = 0
            for label, prof in group_profiles_for_combo(profiles):
                if prof is None:
                    combo.addItem(label, "")
                    item = combo.model().item(idx)
                    if item is not None:
                        item.setEnabled(False)
                else:
                    pid = str(prof.get("id") or "")
                    combo.addItem(label, pid)
                    if select_id and pid == select_id:
                        select_index = idx
                idx += 1
            combo.addItem("＋ 简单配置…", "__bind__")
            if select_index >= 0:
                combo.setCurrentIndex(select_index)
            else:
                for i in range(combo.count()):
                    item = combo.model().item(i)
                    if item is not None and item.isEnabled() and combo.itemData(i) not in ("", "__bind__"):
                        combo.setCurrentIndex(i)
                        break
        combo.blockSignals(False)

    def _sync_model_combo_width(self) -> None:
        if self._model_combo_width_applied:
            for combo in (self._image_model_combo, self._video_model_combo):
                idx = combo.currentIndex()
                if idx >= 0:
                    combo.setToolTip(combo.itemText(idx))
            return
        fm = QFontMetrics(self._image_model_combo.font())
        max_w = 260
        for profiles in (self._image_profiles, self._video_profiles):
            for label, prof in group_profiles_for_combo(profiles):
                if prof is None:
                    continue
                max_w = max(max_w, fm.horizontalAdvance(label) + 56)
        max_w = min(max_w, 480)
        for combo in (self._image_model_combo, self._video_model_combo):
            combo.setMinimumWidth(max_w)
            combo.setMinimumContentsLength(max(18, min(36, max_w // 10)))
            idx = combo.currentIndex()
            if idx >= 0:
                combo.setToolTip(combo.itemText(idx))
        self._model_combo_width_applied = True

    def _reload_models(
        self,
        *,
        select_active: bool = False,
        refresh_cache: bool = True,
        capabilities: tuple[str, ...] | None = None,
        persist_pick: bool = True,
    ) -> None:
        caps = capabilities or ("image_gen", "video_gen")
        if refresh_cache:
            if "image_gen" in caps:
                self._image_profiles = [
                    p for p in list_ready("image_gen", ready_only=True) if p.get("source") == "catalog"
                ]
            if "video_gen" in caps:
                self._video_profiles = [
                    p for p in list_ready("video_gen", ready_only=True) if p.get("source") == "catalog"
                ]
        rows = self._video_profiles if self._kind == _KIND_VIDEO else self._image_profiles
        select_id = ""
        if select_active and rows:
            cap = "video_gen" if self._kind == _KIND_VIDEO else "image_gen"
            ids = [str(p.get("id") or "") for p in rows]
            active = get_active_profile_id(cap)
            if active in ids:
                select_id = active
            elif refresh_cache:
                select_id = pick_effective_profile_id(cap, persist=persist_pick)
            else:
                select_id = str(rows[0].get("id") or "")
        if refresh_cache:
            img_id = ""
            vid_id = ""
            if "image_gen" in caps:
                cap = "image_gen"
                ids = [str(p.get("id") or "") for p in self._image_profiles]
                active = get_active_profile_id(cap)
                img_id = (
                    active
                    if active in ids
                    else (
                        pick_effective_profile_id(cap, persist=persist_pick)
                        if self._image_profiles
                        else ""
                    )
                )
                self._fill_grouped_model_combo(
                    self._image_model_combo, self._image_profiles, select_id=img_id
                )
            if "video_gen" in caps:
                cap = "video_gen"
                ids = [str(p.get("id") or "") for p in self._video_profiles]
                active = get_active_profile_id(cap)
                vid_id = (
                    active
                    if active in ids
                    else (
                        pick_effective_profile_id(cap, persist=persist_pick)
                        if self._video_profiles
                        else ""
                    )
                )
                self._fill_grouped_model_combo(
                    self._video_model_combo, self._video_profiles, select_id=vid_id
                )
            if caps == ("image_gen", "video_gen") or set(caps) >= {"image_gen", "video_gen"}:
                self._sync_model_combo_width()
            elif "image_gen" in caps or "video_gen" in caps:
                self._sync_model_combo_width()
        else:
            combo = self._active_model_combo()
            self._fill_grouped_model_combo(combo, rows, select_id=select_id)
        self._model_combo_stack.setCurrentIndex(0 if self._kind == _KIND_IMAGE else 1)
        self._sync_image_param_panels()
        self._sync_empty_models_hint()

    def _sync_empty_models_hint(self) -> None:
        rows = self._video_profiles if self._kind == _KIND_VIDEO else self._image_profiles
        if rows:
            self._empty_models.setVisible(False)
            return
        if self._kind == _KIND_VIDEO:
            self._empty_models.setText(
                "暂无视频模型。点「简单配置…」两步绑 Key；也可稍后再说，先浏览本页。"
            )
        else:
            self._empty_models.setText(
                "暂无生图模型。点「简单配置…」一键装本机生图（≤2 步）；也可稍后再说。"
            )
        self._empty_models.setVisible(True)

    def _combo_index_for_profile(self, profile_id: str) -> int:
        combo = self._active_model_combo()
        for i in range(combo.count()):
            if str(combo.itemData(i) or "") == profile_id:
                item = combo.model().item(i)
                if item is not None and item.isEnabled():
                    return i
        return -1

    def _current_profile_id(self) -> str:
        combo = self._active_model_combo()
        idx = combo.currentIndex()
        item = combo.model().item(idx)
        if item is not None and not item.isEnabled():
            return ""
        data = combo.currentData()
        if data in ("", "__bind__", None):
            return ""
        return str(data)

    def _on_model_changed(self, _index: int) -> None:
        sender = self.sender()
        combo = self._active_model_combo()
        if sender is not None and sender is not combo:
            return
        idx = combo.currentIndex()
        if idx >= 0:
            combo.setToolTip(combo.itemText(idx))
        data = combo.currentData()
        if data == "__bind__":
            combo.blockSignals(True)
            for i in range(combo.count()):
                item = combo.model().item(i)
                d = combo.itemData(i)
                if item is not None and item.isEnabled() and d not in ("", "__bind__", None):
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)
            self._open_simple_setup()
            return
        pid = self._current_profile_id()
        if not pid:
            return
        cap = "video_gen" if self._kind == _KIND_VIDEO else "image_gen"
        set_active_profile_id(cap, pid)
        self._sync_image_param_panels()

    def _supports_edit(self, pid: str) -> bool:
        try:
            prof = resolve_profile("image_gen", pid)
        except KeyError:
            return False
        if bool(prof.get("supports_edit")):
            return True
        base = str(prof.get("api_base") or "").lower()
        model = str(prof.get("model") or "").lower()
        provider = str(prof.get("provider") or "").lower()
        return (
            "volces.com" in base
            or "evolink.ai" in base
            or "seedream" in model
            or "doubao" in model
            or "grok-imagine" in model
            or provider == "evolink_images"
        )

    def _add_refs(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择参考内容",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not paths:
            return
        if self._kind == _KIND_VIDEO or self._img_mode == _IMG_REF:
            max_n = 1
        elif self._img_mode == _IMG_FUSE:
            max_n = 3 if is_evolink_image_profile(None, self._current_profile_id()) else 10
        else:
            max_n = 10
            self._rb_ref.setChecked(True)
            self._img_mode = _IMG_REF
            self._apply_kind_ui()
        for p in paths:
            path = Path(p)
            if not path.is_file():
                continue
            if any(x.resolve() == path.resolve() for x in self._ref_paths):
                continue
            self._ref_paths.append(path)
            if len(self._ref_paths) >= max_n:
                break
        self._ref_paths = self._ref_paths[:max_n]
        self._rebuild_thumbs()
        if self._kind == _KIND_VIDEO:
            self._sw_web.setEnabled(len(self._ref_paths) == 0)
            if self._ref_paths:
                self._sw_web.setChecked(False)
                self._web_search = False

    def _clear_refs(self) -> None:
        self._ref_paths = []
        self._rebuild_thumbs()
        if self._kind == _KIND_VIDEO:
            self._sw_web.setEnabled(True)

    def _remove_ref(self, path_s: str) -> None:
        target = Path(path_s)
        self._ref_paths = [p for p in self._ref_paths if p.resolve() != target.resolve()]
        self._rebuild_thumbs()
        if self._kind == _KIND_VIDEO:
            self._sw_web.setEnabled(len(self._ref_paths) == 0)

    def _rebuild_thumbs(self) -> None:
        while self._thumbs_lay.count():
            item = self._thumbs_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for p in self._ref_paths:
            card = _RefThumb(p)
            card.remove_requested.connect(self._remove_ref)
            self._thumbs_lay.addWidget(card)
        add_tile = QFrame()
        add_tile.setObjectName("MediaRefAddTile")
        add_tile.setFixedSize(72, 86)
        add_lay = QVBoxLayout(add_tile)
        add_lay.setContentsMargins(4, 4, 4, 4)
        add_btn = SecondaryButton("+")
        add_btn.setObjectName("MediaRefRemoveBtn")
        add_btn.setFixedSize(52, 40)
        add_btn.clicked.connect(self._add_refs)
        add_lay.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self._thumbs_lay.addWidget(add_tile)
        self._thumbs_lay.addStretch(1)

    def _task_label(self) -> str:
        if self._kind == _KIND_VIDEO:
            return "视频 · Seedance"
        mode = {
            _IMG_TXT: "文生图",
            _IMG_REF: "图生图",
            _IMG_FUSE: "多图融合",
        }.get(self._img_mode, "图片")
        return f"图片 · {mode}"

    def _task_btn_caption(self) -> str:
        active = self._queue.active_count()
        if active <= 0:
            return "任务"
        running = self._queue.running_task()
        if running and running.progress > 0:
            return f"任务 · {active} · {running.progress}%"
        return f"任务 · {active}"

    def _apply_task_panel_layout(self, visible: bool) -> None:
        self._task_panel.setVisible(visible)
        self._refresh_task_badge()

    def _toggle_task_panel(self, checked: bool) -> None:
        self._apply_task_panel_layout(checked)

    def _refresh_task_badge(self) -> None:
        active = self._queue.active_count()
        if active <= 0:
            _set_semantic(self._task_badge, "info", "无活动", compact=True)
        else:
            running = self._queue.running_task()
            if running and running.progress > 0:
                _set_semantic(
                    self._task_badge,
                    "warning",
                    f"{active} 个活动 · 当前 {running.progress}%",
                    compact=True,
                )
            else:
                _set_semantic(self._task_badge, "warning", f"{active} 个活动任务", compact=True)
        if self._btn_tasks.isChecked():
            self._btn_tasks.setText("收起任务" if active <= 0 else f"收起任务 · {active}")
        else:
            self._btn_tasks.setText(self._task_btn_caption())

    def _on_task_updated(self, task_id: str) -> None:
        task = next((t for t in self._queue.tasks() if t.id == task_id), None)
        if task is None:
            return
        if self._task_empty.isVisible():
            self._task_empty.hide()
        row = self._task_rows.get(task_id)
        if row is None:
            row = _TaskRow(task)
            row.cancel_requested.connect(self._queue.cancel_task)
            row.preview_requested.connect(self._preview_task)
            self._task_rows[task_id] = row
            self._task_lay.insertWidget(0, row)
        row.apply_task(task)
        self._refresh_task_badge()
        if task.status == "running":
            self._status_line.setText(task.message)
            self.report_status(task.message, level=StatusLevel.INFO)
        elif task.status == "completed":
            self._on_task_completed(task)
        elif task.status == "failed":
            self._status_line.setText(task.message)
            show_error(self, task.error or task.message)
            self.report_status("生成失败", level=StatusLevel.ERROR)
        elif task.status == "cancelled":
            self._status_line.setText("任务已取消")

    def _on_task_completed(self, task: MediaGenTask) -> None:
        path = Path(task.result_path)
        if not path.is_file():
            return
        self._result_path = path
        self._show_preview(path)
        self._result_meta.setText(path.name)
        self._set_result_actions(path)
        self._works_sig_cache = None
        self._reload_works(poster_videos=False)
        self._mark_work_selected(path)
        self._status_line.setText(f"完成：{path.name}")
        self.report_status(f"完成：{path.name}", level=StatusLevel.SUCCESS)
        is_video = path.suffix.lower() in (".mp4", ".webm", ".mov")
        if self._last_enqueue_batch == 1 and self._queue.active_count() == 0:
            show_saved(self, "已生成" + ("视频" if is_video else "图片"), str(path.parent))

    def _preview_task(self, task_id: str) -> None:
        task = next((t for t in self._queue.tasks() if t.id == task_id), None)
        if task and task.result_path:
            self._select_work(task.result_path)

    def _cancel_running(self) -> None:
        running = self._queue.running_task()
        if running:
            self._queue.cancel_task(running.id)

    def _clear_finished_tasks(self) -> None:
        done_ids = [
            t.id
            for t in self._queue.tasks()
            if t.status in ("completed", "failed", "cancelled")
        ]
        for tid in done_ids:
            row = self._task_rows.pop(tid, None)
            if row is not None:
                self._task_lay.removeWidget(row)
                row.deleteLater()
        self._queue.clear_finished()
        if not self._task_rows:
            self._task_empty.show()
        self._refresh_task_badge()

    def _on_generate(self) -> None:
        prompt = self._prompt.toPlainText().strip()
        if not prompt:
            show_warning(self, "请先填写创意描述。")
            return
        pid = self._current_profile_id()
        if not pid:
            from core.user_messages import ask_confirm

            if ask_confirm(
                self,
                "还没有可用模型。现在「简单配置」？\n"
                "图片：一键装本机生图；视频：两步绑 Key。\n"
                "也可稍后再说。",
                title="探索模型",
            ):
                self._open_simple_setup()
            return

        refs = [str(p) for p in self._ref_paths if p.is_file()]
        if self._kind == _KIND_IMAGE:
            if self._img_mode == _IMG_TXT:
                refs = []
            elif self._img_mode == _IMG_REF:
                if len(refs) < 1:
                    show_warning(self, "图生图请先添加 1 张参考图。")
                    return
                refs = refs[:1]
            elif self._img_mode == _IMG_FUSE:
                if is_evolink_image_profile(None, pid):
                    if len(refs) < 1:
                        show_warning(self, "Grok 参考图编辑至少需要 1 张参考图。")
                        return
                    refs = refs[:3]
                else:
                    if len(refs) < 2:
                        show_warning(self, "多图融合至少需要 2 张参考图。")
                        return
                    refs = refs[:10]
            if refs and not self._supports_edit(pid):
                for p in self._image_profiles:
                    cand = str(p.get("id") or "")
                    if self._supports_edit(cand):
                        pid = cand
                        ids = [str(x.get("id") or "") for x in self._image_profiles]
                        if pid in ids:
                            idx = self._combo_index_for_profile(pid)
                            if idx >= 0:
                                self._image_model_combo.setCurrentIndex(idx)
                        break
                else:
                    show_warning(self, "当前模型不支持参考图，请选「豆包 · Seedream」。")
                    return
            try:
                from services.model_catalog import save_user_profile_patch

                save_user_profile_patch("image_gen", pid, {"size": self._image_res})
            except Exception:
                pass
        else:
            refs = refs[:2]

        gen_audio = self._generate_audio if self._kind == _KIND_VIDEO else False
        web_search = self._web_search if self._kind == _KIND_VIDEO and not refs else False
        batch = int(self._batch_spin.value())
        self._last_enqueue_batch = batch

        spec = MediaGenSpec(
            kind=self._kind,
            prompt=prompt,
            profile_id=pid,
            image_paths=refs,
            width=self._aspect_w,
            height=self._aspect_h,
            image_size=self._image_res,
            ratio=self._video_ratio,
            resolution=self._video_res,
            duration=self._video_dur,
            generate_audio=gen_audio,
            web_search=web_search,
            image_quality=self._image_quality if is_evolink_image_profile(None, pid) else "",
            image_n=self._image_n if is_evolink_image_profile(None, pid) else 1,
            label=self._task_label(),
        )
        ids = self._queue.enqueue_many(spec, batch)
        self._btn_tasks.blockSignals(True)
        self._btn_tasks.setChecked(True)
        self._btn_tasks.blockSignals(False)
        self._apply_task_panel_layout(True)
        self._status_line.setText(f"已加入 {len(ids)} 个任务。")
        self.report_status(f"已加入 {len(ids)} 个任务", level=StatusLevel.INFO)
        self._refresh_task_badge()

    def _show_preview(self, path: Path) -> None:
        if path.suffix.lower() in (".mp4", ".webm", ".mov"):
            self._preview.set_video_path(path)
            return
        self._preview.set_image_path(path)

    def _copy_result(self) -> None:
        if not self._result_path or not self._result_path.is_file():
            show_warning(self, "还没有可复制的内容。")
            return
        if self._result_path.suffix.lower() in (".mp4", ".webm", ".mov"):
            show_warning(self, "视频请用「打开目录」复制文件。")
            return
        pix = self._preview.source_pixmap()
        if pix is None or pix.isNull():
            pix = QPixmap(str(self._result_path))
        if pix.isNull():
            show_warning(self, "无法读取图片。")
            return
        QGuiApplication.clipboard().setPixmap(pix)
        self.report_status("已复制到剪贴板", level=StatusLevel.SUCCESS)

    def _open_result(self) -> None:
        from services.os_open import open_in_file_manager

        if self._result_path and self._result_path.is_file():
            open_in_file_manager(str(self._result_path), select=True)
        else:
            show_warning(self, "还没有生成结果。")

    def _play_result(self) -> None:
        if self._preview.is_video_mode():
            self._preview.toggle_playback()
            self.report_status("视频预览已切换播放状态", level=StatusLevel.INFO)
            return
        from services.os_open import open_path

        if self._result_path and self._result_path.is_file():
            open_path(str(self._result_path))
        else:
            show_warning(self, "还没有视频文件。")

    def _mark_work_selected(self, path: Path | None) -> None:
        self._selected_work = path
        for tile in self._work_tiles:
            selected = path is not None and tile.path.resolve() == path.resolve()
            tile.setProperty("selected", "true" if selected else "false")
            tile.style().unpolish(tile)
            tile.style().polish(tile)

    def _works_list_signature(self) -> tuple[tuple[str, float], ...]:
        out = module_output_dir("media_studio", create=True)
        seen: set[Path] = set()
        entries: list[tuple[float, str]] = []
        patterns = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.mp4", "*.webm", "*.mov")
        for pattern in patterns:
            for p in out.glob(pattern):
                rp = p.resolve()
                if not rp.is_file() or rp in seen:
                    continue
                seen.add(rp)
                try:
                    entries.append((rp.stat().st_mtime, str(rp)))
                except OSError:
                    continue
        entries.sort(key=lambda x: x[0], reverse=True)
        return tuple((name, mtime) for mtime, name in entries[:16])

    def _reload_works_if_needed(
        self,
        *,
        force: bool = False,
        poster_videos: bool = False,
    ) -> None:
        if not force and self._works_sig_cache is not None and self._work_tiles:
            return
        if force:
            sig = self._works_list_signature()
            self._works_sig_cache = sig
            self._reload_works(poster_videos=poster_videos)
            return
        sig = self._works_list_signature()
        if sig == self._works_sig_cache and self._work_tiles:
            return
        self._works_sig_cache = sig
        self._reload_works(poster_videos=False)

    def _reload_works(self, *, poster_videos: bool = False) -> None:
        self._works_reload_gen += 1
        gen = self._works_reload_gen
        while self._works_lay.count():
            item = self._works_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._work_tiles = []
        self._poster_jobs = []
        self._video_poster_jobs = []
        out = module_output_dir("media_studio", create=True)
        files: list[Path] = []
        patterns = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.mp4", "*.webm", "*.mov")
        for pattern in patterns:
            files.extend(out.glob(pattern))
        files = sorted({p.resolve() for p in files if p.is_file()}, key=lambda p: p.stat().st_mtime, reverse=True)[
            :16
        ]
        if not files:
            self._works_lay.addWidget(HintLabel("暂无作品，生成后会出现在这里。"))
        else:
            for path in files:
                tile = _WorkTile(path, defer_thumb=True)
                tile.selected.connect(self._select_work)
                self._work_tiles.append(tile)
                self._works_lay.addWidget(tile)
                if path.suffix.lower() in _VIDEO_EXTS:
                    self._video_poster_jobs.append((tile, path))
                else:
                    self._poster_jobs.append((tile, path))
            if self._poster_jobs:
                QTimer.singleShot(600, lambda g=gen: self._run_next_image_poster_job(g))
            if self._video_poster_jobs:
                vdelay = 600 if poster_videos else 2800
                QTimer.singleShot(
                    vdelay,
                    lambda g=gen: self._run_next_video_poster_job(g),
                )

            pick: Path | None = None
            if self._result_path and self._result_path.is_file():
                target = self._result_path.resolve()
                pick = next((f for f in files if f.resolve() == target), None)
            if pick is None:
                pick = files[0]

            current = (
                self._result_path.resolve()
                if self._result_path and self._result_path.is_file()
                else None
            )
            pick_s = str(pick)
            if current != pick.resolve():

                def _select_pick() -> None:
                    self._select_work(pick_s)

                QTimer.singleShot(180, _select_pick)
            else:

                def _restore_preview() -> None:
                    self._show_preview(pick)
                    self._result_meta.setText(pick.name)
                    self._set_result_actions(pick)
                    self._mark_work_selected(pick)

                QTimer.singleShot(180, _restore_preview)
        self._works_lay.addStretch(1)
        self._works_host.adjustSize()
        self._works_block.update()

    def _run_next_image_poster_job(self, gen: int | None = None) -> None:
        if gen is not None and gen != self._works_reload_gen:
            return
        if not self._poster_jobs:
            return
        tile, path = self._poster_jobs.pop(0)
        if tile not in self._work_tiles:
            if self._poster_jobs and (gen is None or gen == self._works_reload_gen):
                QTimer.singleShot(8, lambda g=gen: self._run_next_image_poster_job(g))
            return
        pix = _fit_pixmap(path, _WorkTile._PREVIEW_W, _WorkTile._PREVIEW_H)
        if not pix.isNull():
            try:
                tile.set_poster(pix)
            except RuntimeError:
                pass
        if self._poster_jobs and (gen is None or gen == self._works_reload_gen):
            QTimer.singleShot(8, lambda g=gen: self._run_next_image_poster_job(g))

    def _run_next_video_poster_job(self, gen: int | None = None) -> None:
        if gen is not None and gen != self._works_reload_gen:
            return
        if not self._video_poster_jobs:
            return
        tile, path = self._video_poster_jobs.pop(0)
        if tile not in self._work_tiles:
            if self._video_poster_jobs and (gen is None or gen == self._works_reload_gen):
                QTimer.singleShot(16, lambda g=gen: self._run_next_video_poster_job(g))
            return

        def _apply(pix: QPixmap) -> None:
            if gen is not None and gen != self._works_reload_gen:
                return
            if tile not in self._work_tiles:
                if self._video_poster_jobs and (gen is None or gen == self._works_reload_gen):
                    QTimer.singleShot(16, lambda g=gen: self._run_next_video_poster_job(g))
                return
            if not pix.isNull():
                try:
                    tile.set_poster(pix)
                except RuntimeError:
                    pass
            if self._video_poster_jobs and (gen is None or gen == self._works_reload_gen):
                QTimer.singleShot(96, lambda g=gen: self._run_next_video_poster_job(g))

        _capture_video_poster_async(
            path,
            _WorkTile._PREVIEW_W,
            _WorkTile._PREVIEW_H,
            _apply,
        )

    def _select_work(self, path_s: str) -> None:
        path = Path(path_s)
        if not path.is_file():
            return
        self._result_path = path
        self._show_preview(path)
        self._result_meta.setText(path.name)
        self._set_result_actions(path)
        self._mark_work_selected(path)
        self.report_status(f"已载入预览：{path.name}")
