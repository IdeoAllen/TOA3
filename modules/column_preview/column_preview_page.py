# -*- coding: utf-8 -*-
"""MACOS风格桌面：沉浸式分栏/图标/列表 + 彩色标签 + 预览 + 新建/重命名/复制粘贴/删除。"""
from __future__ import annotations

import shutil
import struct
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QMimeData,
    QPoint,
    QSize,
    QStandardPaths,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QBrush, QImageReader, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Windows CF_PREFERREDDROPEFFECT（资源管理器剪切/复制互通）
_DROPEFFECT_COPY = 1
_DROPEFFECT_MOVE = 2
_WIN_DROP_EFFECT_MIME = 'application/x-qt-windows-mime;value="Preferred DropEffect"'

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import ask_confirm, show_saved, show_warning
from modules.column_preview.desktop_state import load_saved_root, save_root
from modules.column_preview.finder_icons import finder_file_pixmap, finder_folder_pixmap
from modules.column_preview.folder_tags import (
    TAG_COLORS,
    load_tags,
    path_key,
    save_tags,
    tag_dot_pixmap,
)
from services.icon_registry import device_pixel_ratio, get_icon
from services.office_preview import (
    OFFICE_EXTENSIONS,
    is_office_preview_path,
    office_kind_label,
    read_office_preview,
)
from services.os_open import open_in_file_manager
from widgets import (
    DataTable,
    HintLabel,
    LineEdit,
    ListWidget,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
    SectionTitle,
)
from widgets.list_edit import FormEditDialog

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
_PDF_EXT = {".pdf"}
_TEXT_EXT = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".log",
    ".ini",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".bat",
    ".ps1",
    ".sql",
}
_COL_WIDTH = 240
_COL_ICON = 20
_ICON_VIEW_SIZE = 88
# 图标在上、两行标题在下；过窄会导致文字溢出叠到邻格（用户反馈「样式乱掉」）
_ICON_GRID_W = 132
_ICON_GRID_H = 138
_ICON_LABEL_MAX = 18  # 约两行中文，超出省略
_TEXT_MAX_BYTES = 512_000
_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 1

_PAGE_IDLE = 0
_PAGE_FOLDER = 1
_PAGE_IMAGE = 2
_PAGE_TEXT = 3
_PAGE_OTHER = 4

_MODE_COLUMNS = "columns"
_MODE_ICONS = "icons"
_MODE_LIST = "list"
_MODE_DETAILS = "details"

_KIND_ALL = "all"
_KIND_DIRS = "dirs"
_KIND_FILES = "files"

_FORMAT_ALL = "all"
_FORMAT_IMAGE = "image"
_FORMAT_OFFICE = "office"
_FORMAT_PDF = "pdf"
_FORMAT_TEXT = "text"
_FORMAT_OTHER = "other"

_KIND_LABELS = {"all": "全部", "dirs": "文件夹", "files": "文件"}
_FORMAT_LABELS = {
    "all": "全部",
    "image": "图片",
    "office": "Office",
    "pdf": "PDF",
    "text": "文本",
    "other": "其他",
}
_KIND_BTN = {"all": "全", "dirs": "夹", "files": "件"}
_FORMAT_BTN = {
    "all": "全",
    "image": "图",
    "office": "Off",
    "pdf": "PDF",
    "text": "文",
    "other": "他",
}

_ROLE_SORT = Qt.ItemDataRole.UserRole + 2


def _unique_paste_dest(parent: Path, name: str, *, is_dir: bool) -> Path:
    """目标已存在时生成「名称 - 副本」类唯一名。"""
    cand = parent / name
    if not cand.exists():
        return cand
    if is_dir:
        stem, suffix = name, ""
    else:
        p = Path(name)
        stem, suffix = p.stem, p.suffix
    n = 1
    while True:
        cand = parent / f"{stem} - 副本{'' if n == 1 else f' {n}'}{suffix}"
        if not cand.exists():
            return cand
        n += 1


def _clipboard_drop_is_move(mime: QMimeData) -> bool:
    raw = mime.data(_WIN_DROP_EFFECT_MIME)
    if raw is None or len(raw) < 4:
        return False
    effect = struct.unpack("<I", bytes(raw[:4]))[0]
    return effect == _DROPEFFECT_MOVE


def _local_paths_from_mime(mime: QMimeData) -> list[Path]:
    if not mime.hasUrls():
        return []
    out: list[Path] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        p = Path(url.toLocalFile())
        if p.exists():
            out.append(p)
    return out


def _is_nested_under(child: Path, ancestor: Path) -> bool:
    try:
        child.resolve().relative_to(ancestor.resolve())
        return True
    except (ValueError, OSError):
        return False


def _icon_view_label(name: str) -> str:
    """图标模式标题：最多约两行，避免撑破格子叠到旁边。"""
    text = (name or "").strip() or "未命名"
    if len(text) <= _ICON_LABEL_MAX:
        return text
    # 优先在分隔符处断行
    cut = _ICON_LABEL_MAX - 1
    head = text[:cut]
    for sep in ("-", "_", " ", "·", "—"):
        idx = head.rfind(sep)
        if idx >= 4:
            cut = idx + 1
            break
    return text[:cut] + "…"


def _entry_format_bucket(path: Path, is_dir: bool) -> str | None:
    if is_dir:
        return None
    ext = path.suffix.lower()
    if ext in _IMAGE_EXT:
        return _FORMAT_IMAGE
    if ext in _PDF_EXT:
        return _FORMAT_PDF
    if ext in _TEXT_EXT or ext in {".rtf"}:
        return _FORMAT_TEXT
    if ext in OFFICE_EXTENSIONS or is_office_preview_path(path):
        return _FORMAT_OFFICE
    return _FORMAT_OTHER


def _breadcrumb_segments(folder: Path, root: Path | None) -> list[tuple[str, Path]]:
    try:
        folder = folder.resolve()
    except OSError:
        return [(folder.name, folder)]
    if root is None:
        return [(folder.name, folder)]
    try:
        root = root.resolve()
    except OSError:
        return [(folder.name, folder)]
    if folder == root:
        return [(root.name, root)]
    try:
        rel = folder.relative_to(root)
    except ValueError:
        return [(folder.name, folder)]
    segments: list[tuple[str, Path]] = [(root.name, root)]
    acc = root
    for part in rel.parts:
        acc = acc / part
        segments.append((part, acc))
    return segments


class _BreadcrumbBar(QWidget):
    """可点击路径面包屑。"""

    navigated = Signal(object)
    root_change_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FinderBreadcrumbBar")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 2)
        self._lay.setSpacing(0)

    def set_path(self, folder: Path, root: Path | None) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        segments = _breadcrumb_segments(folder, root)
        for i, (label, path) in enumerate(segments):
            if i > 0:
                sep = QLabel("›")
                sep.setObjectName("FinderBreadcrumbSep")
                self._lay.addWidget(sep)
            is_last = i == len(segments) - 1
            is_root_seg = i == 0 and root is not None
            if is_last and not is_root_seg:
                current = QLabel(label)
                current.setObjectName("FinderBreadcrumbCurrent")
                self._lay.addWidget(current)
                continue
            btn = QToolButton()
            btn.setObjectName(
                "FinderBreadcrumbRootBtn" if is_root_seg and is_last else "FinderBreadcrumbBtn"
            )
            btn.setText(label if not is_root_seg or not is_last else f"根 · {label}")
            btn.setAutoRaise(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if is_root_seg and is_last:
                btn.setToolTip("点击更换根目录")
                btn.clicked.connect(lambda _=False: self.root_change_requested.emit())
            elif is_root_seg:
                btn.setToolTip("返回根目录（点击根名可更换根目录）")
                btn.clicked.connect(lambda _=False, p=path: self.navigated.emit(p))
            else:
                btn.clicked.connect(lambda _=False, p=path: self.navigated.emit(p))
            self._lay.addWidget(btn)
        self._lay.addStretch(1)


class _SortItem(QTableWidgetItem):
    def __lt__(self, other):  # noqa: N802
        a = self.data(_ROLE_SORT)
        b = other.data(_ROLE_SORT) if other is not None else None
        if a is None:
            return True
        if b is None:
            return False
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


def _fmt_time(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


def _entry_meta(path: Path, is_dir: bool) -> tuple[str, str, str, str, float, float, int]:
    """显示用：修改、创建、类型、大小；排序用：mtime、ctime、size。"""
    try:
        st = path.stat()
        mtime = float(st.st_mtime)
        ctime = float(getattr(st, "st_birthtime", st.st_ctime))
        size = 0 if is_dir else int(st.st_size)
    except OSError:
        return "—", "—", "文件夹" if is_dir else "文件", "—", 0.0, 0.0, 0
    kind = "文件夹" if is_dir else (path.suffix.upper().lstrip(".") or "文件")
    if is_dir:
        size_txt = "—"
    elif size < 1024:
        size_txt = f"{size} B"
    elif size < 1024 * 1024:
        size_txt = f"{size / 1024:.1f} KB"
    else:
        size_txt = f"{size / (1024 * 1024):.1f} MB"
    return _fmt_time(mtime), _fmt_time(ctime), kind, size_txt, mtime, ctime, size


def _list_entries(folder: Path) -> list[tuple[str, Path, bool]]:
    if not folder.is_dir():
        return []
    dirs: list[tuple[str, Path, bool]] = []
    files: list[tuple[str, Path, bool]] = []
    try:
        for p in folder.iterdir():
            if p.name.startswith("."):
                continue
            try:
                is_dir = p.is_dir()
            except OSError:
                continue
            item = (p.name, p, is_dir)
            (dirs if is_dir else files).append(item)
    except OSError:
        return []
    key = lambda t: t[0].casefold()
    return sorted(dirs, key=key) + sorted(files, key=key)


def _read_text_preview(path: Path) -> str:
    data = path.read_bytes()
    truncated = len(data) > _TEXT_MAX_BYTES
    raw = data[:_TEXT_MAX_BYTES]
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            if truncated:
                text += "\n\n…（已截断预览）"
            return text
        except UnicodeDecodeError:
            continue
    return "（无法以文本方式解码）"


def _load_image_as_displayed(path: Path, *, parent=None) -> QPixmap:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        return QPixmap()
    dpr = device_pixel_ratio(parent)
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def _load_pdf_first_page(
    path: Path, *, max_w: int = 960, max_h: int = 1280, parent=None
) -> tuple[QPixmap, int]:
    """渲染 PDF 首页为预览图（Qt Pdf，无 Poppler 依赖）。"""
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument(parent)
    if doc.load(str(path)) != QPdfDocument.Error.None_:
        return QPixmap(), 0
    pages = int(doc.pageCount())
    if pages < 1:
        return QPixmap(), 0
    pt = doc.pagePointSize(0)
    w_pt = max(1.0, float(pt.width()))
    h_pt = max(1.0, float(pt.height()))
    scale = min(max_w / w_pt, max_h / h_pt, 4.0)
    rw = max(160, int(w_pt * scale))
    rh = max(160, int(h_pt * scale))
    img = doc.render(0, QSize(rw, rh))
    if img.isNull():
        return QPixmap(), pages
    dpr = device_pixel_ratio(parent)
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm, pages


def _fit_pixmap(pm: QPixmap, max_w: int, max_h: int, *, parent=None) -> QPixmap:
    if pm.isNull():
        return pm
    dpr = pm.devicePixelRatio() or device_pixel_ratio(parent) or 1.0
    logical_w = max(1, int(pm.width() / dpr))
    logical_h = max(1, int(pm.height() / dpr))
    if logical_w <= max_w and logical_h <= max_h:
        return pm
    scaled = pm.scaled(
        int(max_w * dpr),
        int(max_h * dpr),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


class _ColumnList(ListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FinderColumn")
        self.setFixedWidth(_COL_WIDTH)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(_COL_ICON, _COL_ICON))
        self.setSpacing(0)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)


class _EmptyState(QWidget):
    def __init__(self, title: str, body: str, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 24, 20, 20)
        lay.setSpacing(8)
        lay.addStretch(1)
        t = SectionTitle(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        h = HintLabel(body)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setWordWrap(True)
        lay.addWidget(h)
        lay.addStretch(2)


class ColumnPreviewPage(BasePage):
    page_id = "column_preview"
    page_title = "MACOS风格桌面"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._columns: list[_ColumnList] = []
        self._column_dirs: list[Path] = []
        self._root_path: Path | None = None
        self._cwd: Path | None = None
        self._current_path: Path | None = None
        self._mode = _MODE_COLUMNS
        self._tags: dict[str, str] = load_tags()
        self._tag_filter: str | None = None
        self._tag_filter_btns: dict[str, QToolButton] = {}
        self._kind_filter = _KIND_ALL
        self._format_filter = _FORMAT_ALL
        self._kind_filter_btns: dict[str, QToolButton] = {}
        self._format_filter_btns: dict[str, QToolButton] = {}
        self._updating = False
        self._raw_preview_pm = QPixmap()
        self._mode_btns: dict[str, QToolButton] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # —— 主工具条（精简：操作/标签收进菜单）——
        toolbar = QWidget()
        toolbar.setObjectName("FinderToolbarBar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(6)

        self._btn_up = self._tool_btn("上级", tip="返回上一级", slot=self._go_up)
        bar.addWidget(self._btn_up)

        self._root = LineEdit()
        self._root.setPlaceholderText("根目录路径，回车或点 … 更换")
        self._root.setMinimumHeight(28)
        self._root.returnPressed.connect(self._on_open_root)
        bar.addWidget(self._root, 1)

        bar.addWidget(self._tool_btn("换根", tip="选择新的根目录", slot=self._browse))

        mode_wrap = QWidget()
        mode_wrap.setObjectName("FinderToolbarModeGroup")
        mode_lay = QHBoxLayout(mode_wrap)
        mode_lay.setContentsMargins(0, 0, 0, 0)
        mode_lay.setSpacing(2)
        for key, tip in (
            (_MODE_COLUMNS, "分栏"),
            (_MODE_ICONS, "图标"),
            (_MODE_LIST, "列表"),
            (_MODE_DETAILS, "详细"),
        ):
            btn = QToolButton()
            btn.setObjectName("FinderModeBtn")
            btn.setText(tip)
            btn.setCheckable(True)
            btn.setToolTip(f"浏览模式 · {tip}")
            btn.setMinimumHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=key: self._set_mode(m))
            self._mode_btns[key] = btn
            mode_lay.addWidget(btn)
        self._mode_btns[_MODE_COLUMNS].setChecked(True)
        bar.addWidget(mode_wrap)

        bar.addStretch(1)

        action_wrap = QWidget()
        action_wrap.setObjectName("FinderToolbarActionGroup")
        action_lay = QHBoxLayout(action_wrap)
        action_lay.setContentsMargins(0, 0, 0, 0)
        action_lay.setSpacing(4)
        action_lay.addWidget(self._menu_tool_btn("操作", self._build_ops_menu()))
        action_lay.addWidget(self._menu_tool_btn("标签", self._build_tags_menu()))
        bar.addWidget(action_wrap)
        outer.addWidget(toolbar)

        self._breadcrumb = _BreadcrumbBar()
        self._breadcrumb.navigated.connect(self._navigate_breadcrumb)
        self._breadcrumb.root_change_requested.connect(self._browse)
        self._breadcrumb.setVisible(False)
        outer.addWidget(self._breadcrumb)

        # —— 快筛条：类型 / 格式 / 色标（紧凑芯片）——
        filter_wrap = QWidget()
        filter_wrap.setObjectName("FinderFilterBar")
        filter_bar = QHBoxLayout(filter_wrap)
        filter_bar.setContentsMargins(0, 0, 0, 0)
        filter_bar.setSpacing(3)

        self._kind_filter_group = QButtonGroup(self)
        self._kind_filter_group.setExclusive(True)
        for key, label in _KIND_BTN.items():
            btn = self._quick_filter_btn(label, f"类型 · {_KIND_LABELS[key]}")
            btn.setCheckable(True)
            btn.setChecked(key == _KIND_ALL)
            btn.clicked.connect(lambda _=False, k=key: self._set_kind_filter(k))
            self._kind_filter_group.addButton(btn)
            self._kind_filter_btns[key] = btn
            filter_bar.addWidget(btn)

        filter_bar.addWidget(self._vsep())

        self._format_filter_group = QButtonGroup(self)
        self._format_filter_group.setExclusive(True)
        for key, label in _FORMAT_BTN.items():
            btn = self._quick_filter_btn(label, f"格式 · {_FORMAT_LABELS[key]}")
            btn.setCheckable(True)
            btn.setChecked(key == _FORMAT_ALL)
            btn.clicked.connect(lambda _=False, k=key: self._set_format_filter(k))
            self._format_filter_group.addButton(btn)
            self._format_filter_btns[key] = btn
            filter_bar.addWidget(btn)

        filter_bar.addWidget(self._vsep())

        self._tag_filter_group = QButtonGroup(self)
        self._tag_filter_group.setExclusive(True)
        self._btn_filter_all = self._quick_filter_btn("色·全", "色标 · 全部")
        self._btn_filter_all.setCheckable(True)
        self._btn_filter_all.setChecked(True)
        self._btn_filter_all.clicked.connect(lambda: self._set_tag_filter(None))
        self._tag_filter_group.addButton(self._btn_filter_all)
        filter_bar.addWidget(self._btn_filter_all)
        for key, (name, _hex) in TAG_COLORS.items():
            b = QToolButton()
            b.setObjectName("FinderTagFilterBtn")
            b.setToolTip(f"色标 · {name}色")
            b.setIcon(self._tag_qicon(key))
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(22, 22)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self._set_tag_filter(k))
            self._tag_filter_group.addButton(b)
            self._tag_filter_btns[key] = b
            filter_bar.addWidget(b)

        filter_bar.addStretch(1)
        outer.addWidget(filter_wrap)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(4)

        self._browse_stack = QStackedWidget()
        self._browse_stack.setMinimumHeight(320)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("FinderColumnScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.StyledPanel)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cols_host = QWidget()
        self._cols_host.setObjectName("FinderColumnHost")
        self._cols_layout = QHBoxLayout(self._cols_host)
        self._cols_layout.setContentsMargins(0, 0, 0, 0)
        self._cols_layout.setSpacing(0)
        self._cols_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._cols_host)
        self._browse_stack.addWidget(self._scroll)

        flat_wrap = QWidget()
        flat_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fl = QVBoxLayout(flat_wrap)
        fl.setContentsMargins(0, 0, 0, 0)
        self._flat = ListWidget()
        self._flat.setObjectName("FinderFlatList")
        self._flat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._flat.setMinimumHeight(200)
        self._flat.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._flat.setResizeMode(ListWidget.ResizeMode.Adjust)
        self._flat.setMovement(ListWidget.Movement.Static)
        self._flat.setWordWrap(True)
        self._flat.setWrapping(True)
        self._flat.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._flat.itemClicked.connect(self._on_flat_clicked)
        self._flat.itemDoubleClicked.connect(self._on_flat_double_clicked)
        self._flat.customContextMenuRequested.connect(self._on_flat_context)
        fl.addWidget(self._flat, 1)
        self._browse_stack.addWidget(flat_wrap)

        self._details = DataTable(0, 5)
        self._details.setObjectName("FinderDetailsTable")
        self._details.set_auto_column_layout(False)
        self._details.set_headers(["名称", "修改时间", "创建时间", "类型", "大小"])
        self._details.setSortingEnabled(True)
        self._details.setIconSize(QSize(22, 22))
        self._details.verticalHeader().setVisible(False)
        self._details.verticalHeader().setDefaultSectionSize(34)
        hdr = self._details.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._details.setColumnWidth(1, 148)
        self._details.setColumnWidth(2, 148)
        self._details.setColumnWidth(3, 96)
        self._details.setColumnWidth(4, 80)
        self._details.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._details.itemSelectionChanged.connect(self._on_details_selection)
        self._details.cellDoubleClicked.connect(self._on_details_double)
        self._details.customContextMenuRequested.connect(self._on_details_context)
        self._browse_stack.addWidget(self._details)

        split.addWidget(self._browse_stack)

        preview = QFrame()
        preview.setObjectName("FinderPreviewPane")
        preview.setMinimumWidth(280)
        pl = QVBoxLayout(preview)
        pl.setContentsMargins(8, 8, 8, 8)
        pl.setSpacing(6)
        self._preview_name = SectionTitle("未选择")
        pl.addWidget(self._preview_name)

        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(200)
        self._stack.addWidget(_EmptyState("尚未选择", "点选以预览；右键可复制粘贴文件、重命名或删除。"))
        folder_page = QWidget()
        fpl = QVBoxLayout(folder_page)
        fpl.setContentsMargins(12, 16, 12, 8)
        fpl.addStretch(1)
        self._folder_icon = QLabel()
        self._folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fpl.addWidget(self._folder_icon)
        self._folder_stats = HintLabel("")
        self._folder_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fpl.addWidget(self._folder_stats)
        self._folder_tip = HintLabel("")
        self._folder_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fpl.addWidget(self._folder_tip)
        fpl.addStretch(2)
        self._stack.addWidget(folder_page)

        image_page = QWidget()
        il = QVBoxLayout(image_page)
        il.setContentsMargins(4, 4, 4, 2)
        self._image_scroll = QScrollArea()
        self._image_scroll.setWidgetResizable(True)
        self._image_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image = QLabel()
        self._preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_scroll.setWidget(self._preview_image)
        il.addWidget(self._image_scroll, 1)
        self._stack.addWidget(image_page)

        text_page = QWidget()
        tl = QVBoxLayout(text_page)
        tl.setContentsMargins(0, 0, 0, 0)
        self._preview_text = ReadOnlyPlainTextEdit()
        tl.addWidget(self._preview_text)
        self._stack.addWidget(text_page)
        self._stack.addWidget(_EmptyState("无法内嵌预览", "点「打开」用系统程序查看。"))
        pl.addWidget(self._stack, 1)

        self._preview_meta = HintLabel("")
        pl.addWidget(self._preview_meta)
        btn_row = QHBoxLayout()
        self._btn_open = PrimaryButton("打开")
        self._btn_open.clicked.connect(self._open_current)
        self._btn_open.setEnabled(False)
        btn_row.addWidget(self._btn_open)
        self._btn_reveal = SecondaryButton("显示")
        self._btn_reveal.setToolTip("在资源管理器中显示")
        self._btn_reveal.clicked.connect(self._reveal_current)
        self._btn_reveal.setEnabled(False)
        btn_row.addWidget(self._btn_reveal)
        btn_row.addStretch(1)
        pl.addLayout(btn_row)
        split.addWidget(preview)

        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 2)
        split.setSizes([820, 320])
        outer.addWidget(split, 1)

        self._scroll.viewport().installEventFilter(self)
        self._image_scroll.viewport().installEventFilter(self)

        QShortcut(QKeySequence(Qt.Key.Key_F2), self, activated=self._rename_current)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_current)
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=self._copy_files)
        QShortcut(QKeySequence.StandardKey.Cut, self, activated=self._cut_files)
        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self._paste_files)

        self._update_mode_chrome()
        self._sync_format_filter_enabled()
        self._show_idle()

    def _tool_btn(self, text: str, *, tip: str, slot) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("FinderToolBtn")
        btn.setText(text)
        btn.setToolTip(tip)
        btn.setMinimumHeight(28)
        btn.clicked.connect(slot)
        return btn

    def _quick_filter_btn(self, text: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("FinderQuickFilterBtn")
        btn.setText(text)
        btn.setToolTip(tip)
        btn.setFixedHeight(22)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _menu_tool_btn(self, text: str, menu: QMenu) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("FinderMenuBtn")
        btn.setText(text)
        btn.setToolTip(text)
        btn.setMinimumHeight(28)
        btn.setMaximumHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setProperty("hasMenu", "true")
        btn.setMenu(menu)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        return btn

    def _build_ops_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("新建文件夹", self._create_folder)
        menu.addAction("新建文件", self._create_file)
        menu.addSeparator()
        menu.addAction("重命名 (F2)", self._rename_current)
        menu.addAction("制作副本", self._duplicate_current)
        menu.addAction("复制 (Ctrl+C)", self._copy_files)
        menu.addAction("剪切 (Ctrl+X)", self._cut_files)
        menu.addAction("粘贴 (Ctrl+V)", self._paste_files)
        menu.addAction("复制路径", self._copy_path)
        menu.addSeparator()
        menu.addAction("删除 (Del)", self._delete_current)
        return menu

    def _build_tags_menu(self) -> QMenu:
        menu = QMenu(self)
        for key, (name, _hex) in TAG_COLORS.items():
            menu.addAction(f"设为{name}色标签", lambda _=False, k=key: self._apply_tag(k))
        menu.addSeparator()
        menu.addAction("清除标签", lambda: self._apply_tag(None))
        return menu

    def _vsep(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        return line

    def _tag_qicon(self, key: str):
        from PySide6.QtGui import QIcon

        return QIcon(tag_dot_pixmap(key, size=22, dpr=device_pixel_ratio(self)))

    def _finder_icon(self, name: str):
        from app.app_state import AppState

        pal = AppState.get().palette or {}
        fg = str(pal.get("text_secondary") or pal.get("text_primary") or "#5A6A7E")
        return get_icon(name, color=fg, size=18, parent=self)

    def on_immersive_changed(self, on: bool) -> None:
        self.report_status(
            "沉浸全屏 · F11 / 顶栏按钮退出" if on else "已退出沉浸",
            level=StatusLevel.INFO,
        )

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            if obj is self._scroll.viewport():
                self._sync_column_heights()
            elif obj is self._image_scroll.viewport() and not self._raw_preview_pm.isNull():
                self._relayout_image()
        return super().eventFilter(obj, event)

    def _sync_column_heights(self) -> None:
        h = max(200, self._scroll.viewport().height())
        self._cols_host.setMinimumHeight(h)
        for col in self._columns:
            col.setMinimumHeight(h)

    def _reload_tags(self) -> None:
        self._tags = load_tags()

    def _update_breadcrumb(self, folder: Path) -> None:
        if self._root_path is None:
            self._breadcrumb.setVisible(False)
            return
        self._breadcrumb.setVisible(True)
        self._breadcrumb.set_path(folder, self._root_path)

    def _navigate_breadcrumb(self, path: Path) -> None:
        if not path.is_dir():
            return
        self._current_path = path
        self._cwd = path
        if self._mode == _MODE_COLUMNS:
            self._reload_columns_to(path)
        elif self._mode == _MODE_DETAILS:
            self._load_details(path)
        else:
            self._load_flat(path)
        self._show_folder(path)
        self._btn_open.setEnabled(True)
        self._btn_reveal.setEnabled(True)
        self._update_breadcrumb(path)
        self.report_status(str(path), level=StatusLevel.INFO)

    def _entry_icon(self, path: Path, is_dir: bool, size: int):
        from PySide6.QtGui import QIcon

        dpr = device_pixel_ratio(self)
        allow_thumb = self._mode == _MODE_ICONS and size >= 48
        if is_dir:
            tag = self._tags.get(path_key(path))
            pm = finder_folder_pixmap(size, tag, dpr=dpr)
            return QIcon(pm)
        pm = finder_file_pixmap(
            path, size, dpr=dpr, allow_thumb=allow_thumb, parent=self
        )
        return QIcon(pm)

    def _decorate_item(self, item: QListWidgetItem, path: Path, is_dir: bool) -> None:
        item.setForeground(QBrush())
        item.setBackground(QBrush())
        if not is_dir:
            return
        tag = self._tags.get(path_key(path))
        if tag is not None:
            item.setToolTip(f"{TAG_COLORS[tag][0]}色标签 · {path}")

    def _update_mode_chrome(self) -> None:
        for k, btn in self._mode_btns.items():
            btn.setChecked(k == self._mode)
        flat_like = self._mode in (_MODE_ICONS, _MODE_LIST, _MODE_DETAILS)
        self._btn_up.setEnabled(self._can_go_up())
        if self._cwd is not None:
            self._update_breadcrumb(self._cwd)
        else:
            self._breadcrumb.setVisible(False)
        if self._mode == _MODE_COLUMNS:
            self._browse_stack.setCurrentIndex(0)
        elif self._mode == _MODE_DETAILS:
            self._browse_stack.setCurrentIndex(2)
        else:
            self._browse_stack.setCurrentIndex(1)
            if self._mode == _MODE_ICONS:
                self._flat.setViewMode(ListWidget.ViewMode.IconMode)
                self._flat.setIconSize(QSize(_ICON_VIEW_SIZE, _ICON_VIEW_SIZE))
                self._flat.setGridSize(QSize(_ICON_GRID_W, _ICON_GRID_H))
                self._flat.setSpacing(12)
                self._flat.setFlow(ListWidget.Flow.LeftToRight)
                self._flat.setResizeMode(ListWidget.ResizeMode.Adjust)
                self._flat.setUniformItemSizes(True)
                self._flat.setAlternatingRowColors(False)
                self._flat.setWordWrap(True)
            else:
                self._flat.setViewMode(ListWidget.ViewMode.ListMode)
                self._flat.setIconSize(QSize(22, 22))
                self._flat.setGridSize(QSize())
                self._flat.setSpacing(0)
                self._flat.setFlow(ListWidget.Flow.TopToBottom)
                self._flat.setResizeMode(ListWidget.ResizeMode.Adjust)
                self._flat.setUniformItemSizes(False)
                self._flat.setAlternatingRowColors(True)
                self._flat.setWordWrap(False)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._update_mode_chrome()
        if self._root_path is None:
            return
        self._reload_tags()
        if mode == _MODE_COLUMNS:
            focus = self._cwd or self._root_path
            if self._current_path and self._current_path.is_dir():
                focus = self._current_path
            self._reload_columns_to(focus)
        else:
            target = self._resolve_flat_target()
            if mode == _MODE_DETAILS:
                self._load_details(target)
            else:
                self._load_flat(target)
        labels = {
            "columns": "分栏",
            "icons": "图标",
            "list": "列表",
            "details": "详细",
        }
        self.report_status(f"浏览 · {labels.get(mode, mode)}")

    def _resolve_flat_target(self) -> Path:
        if self._current_path and self._current_path.is_dir():
            return self._current_path.resolve()
        if self._current_path and self._current_path.parent.is_dir():
            return self._current_path.parent.resolve()
        if self._cwd and self._cwd.is_dir():
            return self._cwd.resolve()
        assert self._root_path is not None
        return self._root_path.resolve()

    def _can_go_up(self) -> bool:
        if self._cwd is None or self._root_path is None:
            return False
        try:
            self._cwd.resolve().relative_to(self._root_path.resolve())
        except ValueError:
            return False
        return self._cwd.resolve() != self._root_path.resolve()

    def _go_up(self) -> None:
        if not self._can_go_up() or self._cwd is None:
            return
        parent = self._cwd.parent.resolve()
        self._current_path = parent
        if self._mode == _MODE_COLUMNS:
            self._reload_columns_to(parent)
            self._show_folder(parent)
            self._update_breadcrumb(parent)
        elif self._mode == _MODE_DETAILS:
            self._load_details(parent)
        else:
            self._load_flat(parent)
        self._btn_open.setEnabled(True)
        self._btn_reveal.setEnabled(True)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择根目录")
        if path:
            self._load_root(Path(path))

    def _on_open_root(self) -> None:
        raw = self._root.text().strip()
        if not raw:
            show_warning(self, "请先选择根目录。")
            return
        self._load_root(Path(raw))

    def _load_root(self, root: Path) -> None:
        root = root.resolve()
        if not root.is_dir():
            show_warning(self, f"不是有效目录：\n{root}")
            return
        self._reload_tags()
        self._root_path = root
        self._cwd = root
        self._root.setText(str(root))
        try:
            save_root(root)
        except OSError:
            pass
        self._show_idle()
        if self._mode == _MODE_COLUMNS:
            self._clear_columns()
            self._append_column(root)
        elif self._mode == _MODE_DETAILS:
            self._load_details(root)
        else:
            self._load_flat(root)
        self._update_mode_chrome()
        self.report_status(f"桌面 · {root.name}", level=StatusLevel.INFO)

    def _filter_entries_by_tag(
        self, entries: list[tuple[str, Path, bool]], *, folder: Path | None = None
    ) -> list[tuple[str, Path, bool]]:
        if not self._tag_filter:
            return entries
        inside_tagged = False
        if folder is not None:
            inside_tagged = self._tags.get(path_key(folder)) == self._tag_filter
        out: list[tuple[str, Path, bool]] = []
        for name, path, is_dir in entries:
            if is_dir:
                if self._tags.get(path_key(path)) == self._tag_filter:
                    out.append((name, path, is_dir))
            elif inside_tagged:
                out.append((name, path, is_dir))
        return out

    def _filter_entries_by_kind_format(
        self, entries: list[tuple[str, Path, bool]]
    ) -> list[tuple[str, Path, bool]]:
        if self._kind_filter == _KIND_ALL and self._format_filter == _FORMAT_ALL:
            return entries
        out: list[tuple[str, Path, bool]] = []
        for name, path, is_dir in entries:
            if self._kind_filter == _KIND_DIRS and not is_dir:
                continue
            if self._kind_filter == _KIND_FILES and is_dir:
                continue
            if self._format_filter != _FORMAT_ALL:
                if is_dir:
                    if self._kind_filter == _KIND_FILES:
                        continue
                else:
                    bucket = _entry_format_bucket(path, is_dir)
                    if bucket != self._format_filter:
                        continue
            out.append((name, path, is_dir))
        return out

    def _entries_for_folder(self, folder: Path) -> list[tuple[str, Path, bool]]:
        entries = _list_entries(folder)
        entries = self._filter_entries_by_tag(entries, folder=folder)
        return self._filter_entries_by_kind_format(entries)

    def _empty_folder_message(self) -> str:
        hints: list[str] = []
        if self._tag_filter:
            hints.append(f"{TAG_COLORS[self._tag_filter][0]}色标签")
        if self._kind_filter == _KIND_DIRS:
            hints.append("文件夹")
        elif self._kind_filter == _KIND_FILES:
            hints.append("文件")
        if self._format_filter != _FORMAT_ALL:
            hints.append(_FORMAT_LABELS[self._format_filter])
        if hints:
            return f"无符合条件的 · {' · '.join(hints)}"
        return "此文件夹为空"

    def _sync_format_filter_enabled(self) -> None:
        enabled = self._kind_filter != _KIND_DIRS
        for key, btn in self._format_filter_btns.items():
            btn.setEnabled(enabled)
            if not enabled and key != _FORMAT_ALL:
                btn.setChecked(False)
        if not enabled and self._format_filter != _FORMAT_ALL:
            self._format_filter = _FORMAT_ALL
            self._format_filter_btns[_FORMAT_ALL].setChecked(True)

    def _report_filter_status(self) -> None:
        parts: list[str] = []
        if self._kind_filter != _KIND_ALL:
            parts.append(f"类型·{_KIND_LABELS[self._kind_filter]}")
        if self._format_filter != _FORMAT_ALL:
            parts.append(f"格式·{_FORMAT_LABELS[self._format_filter]}")
        if self._tag_filter:
            parts.append(f"色标·{TAG_COLORS[self._tag_filter][0]}")
        if parts:
            self.report_status("快筛 · " + " · ".join(parts), level=StatusLevel.INFO)
        elif self._cwd is not None:
            self.report_status(f"桌面 · {self._cwd.name}", level=StatusLevel.INFO)

    def _set_kind_filter(self, kind: str) -> None:
        if self._kind_filter == kind:
            return
        self._kind_filter = kind
        for key, btn in self._kind_filter_btns.items():
            btn.setChecked(key == kind)
        self._sync_format_filter_enabled()
        self._refresh_current_views()
        self._report_filter_status()

    def _set_format_filter(self, fmt: str) -> None:
        if self._kind_filter == _KIND_DIRS:
            return
        if self._format_filter == fmt:
            return
        self._format_filter = fmt
        for key, btn in self._format_filter_btns.items():
            btn.setChecked(key == fmt)
        self._refresh_current_views()
        self._report_filter_status()

    def _set_tag_filter(self, color_key: str | None) -> None:
        if self._tag_filter == color_key:
            return
        self._tag_filter = color_key
        self._btn_filter_all.setChecked(color_key is None)
        for key, btn in self._tag_filter_btns.items():
            btn.setChecked(key == color_key)
        self._refresh_current_views()
        self._report_filter_status()

    def _apply_tag(self, color_key: str | None) -> None:
        path = self._current_path
        if path is None or not path.is_dir():
            show_warning(self, "请先选中一个文件夹。")
            return
        key = path_key(path)
        if color_key is None:
            self._tags.pop(key, None)
            tip = "已清除标签"
        else:
            self._tags[key] = color_key
            tip = f"已设为{TAG_COLORS[color_key][0]}色标签"
        try:
            save_tags(self._tags)
        except OSError as e:
            show_warning(self, f"保存标签失败：{e}")
            return
        self._reload_tags()
        self._refresh_current_views()
        if path.is_dir():
            self._show_folder(path)
        self.report_status(f"{tip} · {path.name}", level=StatusLevel.INFO)

    def _clear_columns(self) -> None:
        self._updating = True
        while self._cols_layout.count():
            item = self._cols_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._columns.clear()
        self._column_dirs.clear()
        self._updating = False

    def _make_column(self, folder: Path) -> _ColumnList:
        lw = _ColumnList(self._cols_host)
        entries = self._entries_for_folder(folder)
        if not entries:
            empty = QListWidgetItem(self._empty_folder_message())
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            lw.addItem(empty)
        for name, path, is_dir in entries:
            item = QListWidgetItem(name)
            item.setData(_ROLE_PATH, str(path.resolve()))
            item.setData(_ROLE_IS_DIR, is_dir)
            item.setIcon(self._entry_icon(path, is_dir, _COL_ICON))
            item.setSizeHint(QSize(_COL_WIDTH - 8, 28))
            self._decorate_item(item, path, is_dir)
            lw.addItem(item)
        lw.itemClicked.connect(lambda it, col=lw: self._on_item_clicked(col, it))
        lw.itemDoubleClicked.connect(lambda it, col=lw: self._on_item_double_clicked(col, it))
        lw.customContextMenuRequested.connect(
            lambda pos, col=lw: self._on_column_context(col, pos)
        )
        return lw

    def _append_column(self, folder: Path) -> _ColumnList:
        col = self._make_column(folder)
        self._cols_layout.addWidget(col)
        self._columns.append(col)
        self._column_dirs.append(folder.resolve())
        self._sync_column_heights()
        self._cols_host.setMinimumWidth(max(1, len(self._columns)) * _COL_WIDTH)
        QTimer.singleShot(0, self._scroll_to_end)
        return col

    def _trim_after(self, col: _ColumnList) -> None:
        try:
            idx = self._columns.index(col)
        except ValueError:
            return
        self._updating = True
        while len(self._columns) > idx + 1:
            w = self._columns.pop()
            self._column_dirs.pop()
            self._cols_layout.removeWidget(w)
            w.deleteLater()
        self._updating = False
        self._cols_host.setMinimumWidth(max(1, len(self._columns)) * _COL_WIDTH)

    def _reload_columns_to(self, focus: Path) -> None:
        if self._root_path is None:
            return
        self._reload_tags()
        self._clear_columns()
        self._append_column(self._root_path)
        try:
            rel = focus.resolve().relative_to(self._root_path.resolve())
        except ValueError:
            return
        cur = self._root_path
        for part in rel.parts:
            cur = (cur / part).resolve()
            if not cur.is_dir():
                break
            self._select_path_in_column(self._columns[-1], cur)
            self._append_column(cur)
            self._cwd = cur
        self._update_breadcrumb(focus)

    def _select_path_in_column(self, col: _ColumnList, path: Path) -> None:
        target = path_key(path)
        for i in range(col.count()):
            it = col.item(i)
            if it is None:
                continue
            ps = it.data(_ROLE_PATH)
            if ps and path_key(Path(str(ps))) == target:
                col.setCurrentItem(it)
                return

    def _on_item_clicked(self, col: _ColumnList, item: QListWidgetItem) -> None:
        if self._updating or item is None:
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        path_s = item.data(_ROLE_PATH)
        if not path_s:
            return
        path = Path(str(path_s))
        is_dir = bool(item.data(_ROLE_IS_DIR))
        self._trim_after(col)
        self._select_path(path, is_dir=is_dir, expand_column=True)

    def _on_item_double_clicked(self, col: _ColumnList, item: QListWidgetItem) -> None:
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        path_s = item.data(_ROLE_PATH)
        if not path_s:
            return
        path = Path(str(path_s))
        self._current_path = path
        if path.is_file():
            self._open_path_with_system(path)
        elif path.is_dir():
            self._on_item_clicked(col, item)

    def _load_flat(self, folder: Path) -> None:
        try:
            folder = folder.resolve()
        except OSError:
            return
        if not folder.is_dir():
            return
        self._reload_tags()
        self._cwd = folder
        self._update_breadcrumb(folder)

        self._flat.clear()
        icon_sz = _ICON_VIEW_SIZE if self._mode == _MODE_ICONS else 22
        entries = self._entries_for_folder(folder)
        if not entries:
            empty = QListWidgetItem(self._empty_folder_message())
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._flat.addItem(empty)
        for name, path, is_dir in entries:
            display = _icon_view_label(name) if self._mode == _MODE_ICONS else name
            item = QListWidgetItem(display)
            item.setToolTip(name)
            item.setData(_ROLE_PATH, str(path.resolve()))
            item.setData(_ROLE_IS_DIR, is_dir)
            item.setIcon(self._entry_icon(path, is_dir, icon_sz))
            if self._mode == _MODE_ICONS:
                item.setSizeHint(QSize(_ICON_GRID_W, _ICON_GRID_H))
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                )
            else:
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                )
            self._decorate_item(item, path, is_dir)
            self._flat.addItem(item)
        self._update_mode_chrome()
        self._flat.viewport().update()

    def _on_flat_clicked(self, item: QListWidgetItem) -> None:
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        path_s = item.data(_ROLE_PATH)
        if not path_s:
            return
        path = Path(str(path_s))
        self._select_path(path, is_dir=bool(item.data(_ROLE_IS_DIR)), expand_column=False)

    def _on_flat_double_clicked(self, item: QListWidgetItem) -> None:
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        path_s = item.data(_ROLE_PATH)
        if not path_s:
            return
        path = Path(str(path_s))
        if path.is_dir():
            self._load_flat(path)
            self._current_path = path
            self._show_folder(path)
            self._btn_open.setEnabled(True)
            self._btn_reveal.setEnabled(True)
        elif path.is_file():
            self._open_path_with_system(path)

    def _select_path(self, path: Path, *, is_dir: bool, expand_column: bool) -> None:
        try:
            path = path.resolve()
        except OSError:
            pass
        self._current_path = path
        self._btn_open.setEnabled(path.exists())
        self._btn_reveal.setEnabled(path.exists())
        if is_dir and path.is_dir():
            self._cwd = path
            self._update_breadcrumb(path)
            if expand_column and self._mode == _MODE_COLUMNS:
                self._append_column(path)
            self._show_folder(path)
            self.report_status(str(path), level=StatusLevel.INFO)
        else:
            self._show_file(path)

    def _refresh_current_views(self) -> None:
        self._reload_tags()
        if self._mode == _MODE_COLUMNS and self._root_path:
            focus = self._cwd or self._root_path
            if self._current_path and self._current_path.is_dir():
                focus = self._current_path
            elif self._current_path:
                focus = self._current_path.parent
            self._reload_columns_to(focus)
        elif self._mode == _MODE_DETAILS and self._cwd is not None:
            sel = self._current_path
            self._load_details(self._cwd)
            if sel:
                self._reselect_details(sel)
        elif self._cwd is not None:
            sel = self._current_path
            self._load_flat(self._cwd)
            if sel:
                self._reselect_flat(sel)
        if self._current_path and self._current_path.exists():
            if self._current_path.is_dir():
                self._show_folder(self._current_path)
            else:
                self._show_file(self._current_path)

    def _load_details(self, folder: Path) -> None:
        try:
            folder = folder.resolve()
        except OSError:
            return
        if not folder.is_dir():
            return
        self._reload_tags()
        self._cwd = folder
        self._update_breadcrumb(folder)
        self._details.setSortingEnabled(False)
        self._details.setRowCount(0)
        entries = self._entries_for_folder(folder)
        self._details.setRowCount(len(entries))
        for r, (name, path, is_dir) in enumerate(entries):
            m_txt, c_txt, kind, size_txt, mtime, ctime, size = _entry_meta(path, is_dir)
            for c, (txt, sort_v) in enumerate(
                (
                    (name, name.casefold()),
                    (m_txt, mtime),
                    (c_txt, ctime),
                    (kind, kind),
                    (size_txt, size),
                )
            ):
                it = _SortItem(txt)
                it.setData(_ROLE_SORT, sort_v)
                if c == 0:
                    it.setData(_ROLE_PATH, str(path.resolve()))
                    it.setData(_ROLE_IS_DIR, is_dir)
                    it.setIcon(self._entry_icon(path, is_dir, 22))
                    self._decorate_table_name(it, path, is_dir)
                elif c == 4:
                    it.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._details.setItem(r, c, it)
        self._details.setSortingEnabled(True)
        hdr = self._details.horizontalHeader()
        hdr.resizeSection(3, max(96, hdr.sectionSize(3)))
        self._update_mode_chrome()

    def _decorate_table_name(self, item: QTableWidgetItem, path: Path, is_dir: bool) -> None:
        if not is_dir:
            return
        tag = self._tags.get(path_key(path))
        if tag is not None:
            item.setToolTip(f"{TAG_COLORS[tag][0]}色标签 · {path}")

    def _on_details_selection(self) -> None:
        rows = self._details.selectionModel().selectedRows() if self._details.selectionModel() else []
        if not rows:
            return
        item = self._details.item(rows[0].row(), 0)
        if item is None:
            return
        path_s = item.data(_ROLE_PATH)
        if not path_s:
            return
        path = Path(str(path_s))
        self._select_path(path, is_dir=bool(item.data(_ROLE_IS_DIR)), expand_column=False)

    def _on_details_double(self, row: int, _col: int) -> None:
        item = self._details.item(row, 0)
        if item is None:
            return
        path_s = item.data(_ROLE_PATH)
        if not path_s:
            return
        path = Path(str(path_s))
        if path.is_dir():
            self._load_details(path)
            self._current_path = path
            self._show_folder(path)
            self._btn_open.setEnabled(True)
            self._btn_reveal.setEnabled(True)
        elif path.is_file():
            self._open_path_with_system(path)

    def _on_details_context(self, pos: QPoint) -> None:
        item = self._details.itemAt(pos)
        if item is not None:
            self._details.selectRow(item.row())
            self._on_details_selection()
        self._popup_item_menu(self._details.viewport().mapToGlobal(pos))

    def _reselect_details(self, path: Path) -> None:
        target = path_key(path)
        for r in range(self._details.rowCount()):
            it = self._details.item(r, 0)
            if it is None:
                continue
            ps = it.data(_ROLE_PATH)
            if ps and path_key(Path(str(ps))) == target:
                self._details.selectRow(r)
                return

    def _reselect_flat(self, path: Path) -> None:
        target = path_key(path)
        for i in range(self._flat.count()):
            it = self._flat.item(i)
            if it is None:
                continue
            ps = it.data(_ROLE_PATH)
            if ps and path_key(Path(str(ps))) == target:
                self._flat.setCurrentItem(it)
                return

    def _popup_item_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        has_item = self._current_path is not None and self._current_path.exists()
        if has_item:
            menu.addAction("打开", self._open_current)
            menu.addAction("重命名", self._rename_current)
            menu.addAction("制作副本", self._duplicate_current)
            menu.addAction("复制", self._copy_files)
            menu.addAction("剪切", self._cut_files)
            menu.addAction("复制路径", self._copy_path)
            menu.addSeparator()
            if self._current_path.is_dir():
                tag_menu = menu.addMenu("文件夹标签")
                for key, (name, _) in TAG_COLORS.items():
                    tag_menu.addAction(f"{name}色", lambda k=key: self._apply_tag(k))
                tag_menu.addAction("清除标签", lambda: self._apply_tag(None))
                menu.addSeparator()
            act_del = menu.addAction("删除")
            act_del.triggered.connect(self._delete_current)
        if self._clipboard_has_files() and self._target_dir_for_create() is not None:
            if has_item:
                menu.addSeparator()
            menu.addAction("粘贴", self._paste_files)
        if menu.actions():
            menu.exec(global_pos)

    def _on_column_context(self, col: _ColumnList, pos: QPoint) -> None:
        item = col.itemAt(pos)
        if item and (item.flags() & Qt.ItemFlag.ItemIsEnabled) and item.data(_ROLE_PATH):
            self._on_item_clicked(col, item)
        self._popup_item_menu(col.mapToGlobal(pos))

    def _on_flat_context(self, pos: QPoint) -> None:
        item = self._flat.itemAt(pos)
        if item and (item.flags() & Qt.ItemFlag.ItemIsEnabled) and item.data(_ROLE_PATH):
            self._on_flat_clicked(item)
        self._popup_item_menu(self._flat.mapToGlobal(pos))

    def _target_dir_for_create(self) -> Path | None:
        if self._current_path and self._current_path.is_dir():
            return self._current_path
        if self._mode == _MODE_COLUMNS and self._column_dirs:
            return self._column_dirs[-1]
        if self._cwd is not None:
            return self._cwd
        return self._root_path

    def _create_folder(self) -> None:
        parent = self._target_dir_for_create()
        if parent is None:
            show_warning(self, "请先打开根目录。")
            return
        dlg = FormEditDialog(self, title="新建文件夹", fields=[("名称", "name")], ok_text="创建")
        dlg.set_values({"name": "新建文件夹"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = (dlg.values().get("name") or "").strip()
        if not name:
            show_warning(self, "名称不能为空。")
            return
        dest = parent / name
        if dest.exists():
            show_warning(self, f"已存在：\n{dest}")
            return
        try:
            dest.mkdir(parents=False, exist_ok=False)
        except OSError as e:
            show_warning(self, f"创建失败：{e}")
            return
        self._after_mutate(dest)

    def _create_file(self) -> None:
        parent = self._target_dir_for_create()
        if parent is None:
            show_warning(self, "请先打开根目录。")
            return
        dlg = FormEditDialog(self, title="新建文件", fields=[("文件名", "name")], ok_text="创建")
        dlg.set_values({"name": "新建文稿.txt"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = (dlg.values().get("name") or "").strip()
        if not name or "/" in name or "\\" in name:
            show_warning(self, "请输入合法文件名。")
            return
        dest = parent / name
        if dest.exists():
            show_warning(self, f"已存在：\n{dest}")
            return
        try:
            dest.write_text("", encoding="utf-8")
        except OSError as e:
            show_warning(self, f"创建失败：{e}")
            return
        self._after_mutate(dest)

    def _rename_current(self) -> None:
        path = self._current_path
        if path is None or not path.exists():
            show_warning(self, "请先选中文件或文件夹。")
            return
        dlg = FormEditDialog(self, title="重命名", fields=[("新名称", "name")], ok_text="确定")
        dlg.set_values({"name": path.name})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = (dlg.values().get("name") or "").strip()
        if not name or name == path.name or "/" in name or "\\" in name:
            return
        dest = path.parent / name
        if dest.exists():
            show_warning(self, f"已存在：\n{dest}")
            return
        old_key = path_key(path)
        try:
            path.rename(dest)
        except OSError as e:
            show_warning(self, f"重命名失败：{e}")
            return
        if old_key in self._tags and dest.is_dir():
            self._tags[path_key(dest)] = self._tags.pop(old_key)
            save_tags(self._tags)
        self._after_mutate(dest)

    def _duplicate_current(self) -> None:
        path = self._current_path
        if path is None or not path.exists():
            show_warning(self, "请先选中文件或文件夹。")
            return
        stem = path.stem if path.is_file() else path.name
        suffix = path.suffix if path.is_file() else ""
        n = 1
        while True:
            cand = path.parent / f"{stem} 副本{'' if n == 1 else f' {n}'}{suffix}"
            if not cand.exists():
                break
            n += 1
        try:
            if path.is_dir():
                shutil.copytree(path, cand)
            else:
                shutil.copy2(path, cand)
        except OSError as e:
            show_warning(self, f"复制失败：{e}")
            return
        self._after_mutate(cand)
        show_saved(self, f"已制作副本：\n{cand.name}", cand)

    def _clipboard_has_files(self) -> bool:
        cb = QApplication.clipboard()
        mime = cb.mimeData() if cb is not None else None
        return bool(mime and _local_paths_from_mime(mime))

    def _set_files_on_clipboard(self, paths: list[Path], *, cut: bool) -> None:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p.resolve())) for p in paths])
        mime.setText("\n".join(str(p) for p in paths))
        effect = _DROPEFFECT_MOVE if cut else _DROPEFFECT_COPY
        mime.setData(_WIN_DROP_EFFECT_MIME, QByteArray(struct.pack("<I", effect)))
        QApplication.clipboard().setMimeData(mime)

    def _copy_files(self) -> None:
        path = self._current_path
        if path is None or not path.exists():
            show_warning(self, "请先选中文件或文件夹。")
            return
        self._set_files_on_clipboard([path], cut=False)
        kind = "文件夹" if path.is_dir() else "文件"
        self.report_status(f"已复制{kind} · 可在本页或资源管理器粘贴", level=StatusLevel.SUCCESS)

    def _cut_files(self) -> None:
        path = self._current_path
        if path is None or not path.exists():
            show_warning(self, "请先选中文件或文件夹。")
            return
        self._set_files_on_clipboard([path], cut=True)
        kind = "文件夹" if path.is_dir() else "文件"
        self.report_status(f"已剪切{kind} · 粘贴后将移动", level=StatusLevel.SUCCESS)

    def _paste_files(self) -> None:
        dest_dir = self._target_dir_for_create()
        if dest_dir is None:
            show_warning(self, "请先打开根目录。")
            return
        if not dest_dir.is_dir():
            show_warning(self, "当前目标不是文件夹，无法粘贴。")
            return
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            show_warning(self, "剪贴板中没有可粘贴的文件或文件夹。")
            return
        sources = _local_paths_from_mime(mime)
        if not sources:
            show_warning(self, "剪贴板中没有可粘贴的文件或文件夹。")
            return
        is_cut = _clipboard_drop_is_move(mime)
        last: Path | None = None
        errors: list[str] = []
        moved_any = False
        for src in sources:
            if not src.exists():
                errors.append(f"源已不存在：{src.name}")
                continue
            if src.is_dir() and _is_nested_under(dest_dir, src):
                errors.append(f"不能粘贴到自身或其子目录：{src.name}")
                continue
            same_parent = path_key(src.parent) == path_key(dest_dir)
            if is_cut and same_parent:
                last = src
                continue
            try:
                if is_cut:
                    target = dest_dir / src.name
                    if target.exists() and path_key(target) != path_key(src):
                        target = _unique_paste_dest(dest_dir, src.name, is_dir=src.is_dir())
                    old_key = path_key(src)
                    shutil.move(str(src), str(target))
                    moved_any = True
                    if old_key in self._tags and target.is_dir():
                        self._tags[path_key(target)] = self._tags.pop(old_key)
                        save_tags(self._tags)
                else:
                    target = _unique_paste_dest(dest_dir, src.name, is_dir=src.is_dir())
                    if src.is_dir():
                        shutil.copytree(src, target)
                    else:
                        shutil.copy2(src, target)
                last = target
            except OSError as e:
                errors.append(f"{src.name}：{e}")
        if moved_any:
            QApplication.clipboard().clear()
        if last is not None:
            self._after_mutate(last)
            verb = "已移动" if is_cut else "已粘贴"
            self.report_status(f"{verb} → {dest_dir.name}", level=StatusLevel.SUCCESS)
        if errors:
            show_warning(self, "部分粘贴失败：\n" + "\n".join(errors[:5]))
        elif last is None and is_cut:
            self.report_status("已在目标位置，无需移动", level=StatusLevel.INFO)

    def _copy_path(self) -> None:
        path = self._current_path
        if path is None:
            show_warning(self, "请先选中文件或文件夹。")
            return
        QApplication.clipboard().setText(str(path))
        self.report_status("已复制路径", level=StatusLevel.SUCCESS)

    def _delete_current(self) -> None:
        path = self._current_path
        if path is None or not path.exists():
            show_warning(self, "请先选中文件或文件夹。")
            return
        kind = "文件夹" if path.is_dir() else "文件"
        if not ask_confirm(self, f"确定删除{kind}？\n{path.name}\n\n此操作不可恢复。"):
            return
        parent = path.parent
        key = path_key(path)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as e:
            show_warning(self, f"删除失败：{e}")
            return
        self._tags.pop(key, None)
        save_tags(self._tags)
        self._current_path = None
        self._show_idle()
        if self._mode == _MODE_COLUMNS:
            self._reload_columns_to(parent if parent.is_dir() else self._root_path)  # type: ignore[arg-type]
        elif self._mode == _MODE_DETAILS:
            self._load_details(parent if parent.is_dir() else self._cwd or self._root_path)  # type: ignore[arg-type]
        else:
            self._load_flat(parent if parent.is_dir() else self._cwd or self._root_path)  # type: ignore[arg-type]
        self.report_status(f"已删除 · {path.name}", level=StatusLevel.SUCCESS)

    def _after_mutate(self, path: Path) -> None:
        self._current_path = path
        parent = path.parent
        if self._mode == _MODE_COLUMNS:
            focus = path if path.is_dir() else parent
            self._reload_columns_to(focus)
        elif self._mode == _MODE_DETAILS:
            self._load_details(parent)
            self._reselect_details(path)
        else:
            self._load_flat(parent)
            self._reselect_flat(path)
        if path.is_dir():
            self._show_folder(path)
        else:
            self._show_file(path)
        self._btn_open.setEnabled(True)
        self._btn_reveal.setEnabled(True)

    def _open_path_with_system(self, path: Path) -> None:
        import os
        import sys

        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            else:
                open_in_file_manager(path, select=path.is_file())
        except Exception as e:
            show_warning(self, f"无法打开：{e}")

    def _scroll_to_end(self) -> None:
        bar = self._scroll.horizontalScrollBar()
        bar.setValue(bar.maximum())

    def _show_idle(self) -> None:
        self._current_path = None
        self._raw_preview_pm = QPixmap()
        self._preview_name.setText("未选择")
        self._preview_meta.setText("")
        self._stack.setCurrentIndex(_PAGE_IDLE)
        self._btn_open.setEnabled(False)
        self._btn_reveal.setEnabled(False)

    def _show_folder(self, path: Path) -> None:
        self._raw_preview_pm = QPixmap()
        tag = self._tags.get(path_key(path))
        tag_txt = f" · {TAG_COLORS[tag][0]}色" if tag else ""
        dpr = device_pixel_ratio(self)
        pm = finder_folder_pixmap(64, tag, dpr=dpr)
        self._folder_icon.setPixmap(pm)
        try:
            all_entries = _list_entries(path)
            entries = self._entries_for_folder(path)
            n_dirs = sum(1 for _, _, d in entries if d)
            n_files = len(entries) - n_dirs
            empty = not entries
            filtered = len(entries) != len(all_entries)
        except OSError as e:
            self._preview_name.setText(path.name)
            self._folder_stats.setText(f"无法读取：{e}")
            self._folder_tip.setText("")
            self._stack.setCurrentIndex(_PAGE_FOLDER)
            self._preview_meta.setText(str(path))
            return
        self._preview_name.setText(f"{path.name}{tag_txt}")
        if empty:
            if filtered or self._tag_filter or self._kind_filter != _KIND_ALL or self._format_filter != _FORMAT_ALL:
                self._folder_stats.setText(self._empty_folder_message())
                self._folder_tip.setText("调整快筛或点「全部」恢复。")
            else:
                self._folder_stats.setText("空文件夹")
                self._folder_tip.setText("可新建，或右键粘贴 / 管理。")
        else:
            stat = f"{n_dirs} 个文件夹 · {n_files} 个文件"
            if filtered:
                stat += f"（已筛 {len(entries)}/{len(all_entries)}）"
            self._folder_stats.setText(stat)
            self._folder_tip.setText("右键：复制 / 剪切 / 粘贴 / 删除")
        self._stack.setCurrentIndex(_PAGE_FOLDER)
        self._preview_meta.setText(str(path))

    def _show_file(self, path: Path) -> None:
        self._preview_name.setText(path.name)
        ext = path.suffix.lower()
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        size_txt = f"{size:,} 字节" if size < 1024 else f"{size / 1024:.1f} KB"
        self._preview_meta.setText(f"{ext or '无扩展名'} · {size_txt}\n{path}")

        if ext in _IMAGE_EXT and path.is_file():
            pm = _load_image_as_displayed(path, parent=self)
            if pm.isNull():
                self._stack.setCurrentIndex(_PAGE_OTHER)
                return
            self._raw_preview_pm = pm
            self._stack.setCurrentIndex(_PAGE_IMAGE)
            QTimer.singleShot(0, self._relayout_image)
            return
        if ext in _PDF_EXT and path.is_file():
            pm, pages = _load_pdf_first_page(path, parent=self)
            if pm.isNull():
                self._stack.setCurrentIndex(_PAGE_OTHER)
                return
            self._raw_preview_pm = pm
            page_tip = f" · 预览第 1/{pages} 页" if pages > 1 else " · 预览"
            self._preview_meta.setText(f"PDF{page_tip} · {size_txt}\n{path}")
            self._stack.setCurrentIndex(_PAGE_IMAGE)
            QTimer.singleShot(0, self._relayout_image)
            return
        if is_office_preview_path(path) and path.is_file():
            self._raw_preview_pm = QPixmap()
            kind = office_kind_label(path)
            try:
                kind, text = read_office_preview(path)
                self._preview_text.setPlainText(text)
                self._preview_meta.setText(f"{kind} · {size_txt}\n{path}")
            except OSError as e:
                self._preview_text.setPlainText(f"读取失败：{e}")
                self._preview_meta.setText(f"{kind} · {size_txt}\n{path}")
            except Exception as e:
                self._preview_text.setPlainText(f"预览失败：{e}\n\n请点「打开」用系统程序查看。")
                self._preview_meta.setText(f"{kind} · {size_txt}\n{path}")
            self._stack.setCurrentIndex(_PAGE_TEXT)
            return
        if ext in _TEXT_EXT and path.is_file():
            self._raw_preview_pm = QPixmap()
            try:
                self._preview_text.setPlainText(_read_text_preview(path))
            except OSError as e:
                self._preview_text.setPlainText(f"读取失败：{e}")
            self._stack.setCurrentIndex(_PAGE_TEXT)
            return
        self._raw_preview_pm = QPixmap()
        self._stack.setCurrentIndex(_PAGE_OTHER)

    def _relayout_image(self) -> None:
        if self._raw_preview_pm.isNull():
            return
        vp = self._image_scroll.viewport()
        fitted = _fit_pixmap(
            self._raw_preview_pm, max(120, vp.width() - 16), max(120, vp.height() - 16), parent=self
        )
        self._preview_image.setPixmap(fitted)
        dpr = fitted.devicePixelRatio() or 1.0
        self._preview_image.setFixedSize(int(fitted.width() / dpr), int(fitted.height() / dpr))

    def _open_current(self) -> None:
        if self._current_path is None or not self._current_path.exists():
            return
        self._open_path_with_system(self._current_path)

    def _reveal_current(self) -> None:
        if self._current_path is None:
            return
        open_in_file_manager(self._current_path, select=self._current_path.is_file())

    def on_enter(self) -> None:
        if self._root_path is None:
            saved = load_saved_root()
            if saved is not None:
                self._load_root(saved)
            else:
                desktop = Path(
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
                )
                if desktop.is_dir():
                    self._load_root(desktop)
        else:
            self._reload_tags()
            self._refresh_current_views()
        self._sync_column_heights()
        self.report_status("MACOS风格桌面 · ←/→ 子模块 · ↑/↓ 功能模块 · F11 框架全屏")

    def on_leave(self) -> None:
        w = self.window()
        if w is not None and hasattr(w, "is_immersive") and w.is_immersive():
            w.set_immersive(False)
