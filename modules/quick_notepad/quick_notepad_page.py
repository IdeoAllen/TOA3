# -*- coding: utf-8 -*-
"""快速记事本：Outline 风格大纲（Tab 升降级 · Enter 新建 · 拖拽挂子项）。"""
from __future__ import annotations

import re
from datetime import datetime

from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QMimeData,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.app_state import AppState
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher
from modules.clipboard_history.history_store import push_text
from modules.quick_notepad.note_store import (
    add_note,
    children_of,
    delete_node,
    find_note,
    indent_node,
    insert_note_after,
    load_nodes,
    load_settings,
    move_node,
    outdent_node,
    sanitize_tree,
    save_settings,
    update_note,
)
from modules.quick_notepad.rich_body import (
    export_body_from,
    insert_image,
    insert_qimage,
    load_body_into,
    looks_like_html,
    markdown_demo_template,
    refresh_editor_preview,
    rich_has_images,
    sync_design_to_markdown,
    sync_markdown_to_design,
)
from modules.quick_notepad.markdown_highlighter import MarkdownHighlighter
from services.icon_registry import device_pixel_ratio, get_icon
from widgets import (
    ComboBox,
    DangerButton,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    SemanticLabel,
    PlainTextEdit,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SectionTitle,
    TextEdit,
    TreeWidget,
)
from widgets.list_edit import FormEditDialog, confirm_delete
from widgets.metrics import BUTTON_MIN_HEIGHT

# 正文内容色板（富文本排版用，非壳层主题色）
_TEXT_SWATCHES: tuple[tuple[str, str], ...] = (
    ("#1D1D1F", "黑"),
    ("#6B7280", "灰"),
    ("#DC2626", "红"),
    ("#EA580C", "橙"),
    ("#CA8A04", "金"),
    ("#16A34A", "绿"),
    ("#0891B2", "青"),
    ("#2563EB", "蓝"),
    ("#7C3AED", "紫"),
    ("#DB2777", "粉"),
)
_HIGHLIGHT_SWATCHES: tuple[tuple[str | None, str], ...] = (
    (None, "无高亮"),
    ("#FEF08A", "黄底"),
    ("#BBF7D0", "绿底"),
    ("#BAE6FD", "蓝底"),
    ("#FBCFE8", "粉底"),
    ("#FDE68A", "琥珀"),
    ("#E9D5FF", "紫底"),
)
_HEADING_COLORS = {1: "#1D4ED8", 2: "#0F766E", 3: "#B45309"}
_VIEW_MODES = ("edit", "design", "preview")
_VIEW_TAB_LABELS = ("源码", "设计", "预览")


class _ColorPalettePopup(QFrame):
    """字色 / 高亮色板：独立 Qt.Popup，避免 QMenu+QWidgetAction 在 Win/Qt6 下零尺寸白块。"""

    def __init__(
        self,
        anchor: QWidget,
        *,
        title: str,
        swatches: tuple,
        on_pick,
        more_slot,
        dpr: float,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("ColorPalettePopup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setAutoFillBackground(True)
        pal = self.palette()
        win = QApplication.palette().color(pal.ColorRole.Window)
        text = QApplication.palette().color(pal.ColorRole.WindowText)
        pal.setColor(pal.ColorRole.Window, win)
        pal.setColor(pal.ColorRole.WindowText, text)
        self.setPalette(pal)

        self._anchor = anchor
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        root.addWidget(HintLabel(title))

        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        cols = 5
        for i, (hex_c, name) in enumerate(swatches):
            cell = QToolButton(grid_host)
            cell.setObjectName("FinderToolBtn")
            cell.setToolTip(name)
            cell.setIcon(_swatch_icon(hex_c, size=24, dpr=dpr))
            cell.setIconSize(QSize(24, 24))
            cell.setFixedSize(34, 34)
            cell.setAutoRaise(True)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            def _bind(color: str | None):
                def _on(_checked: bool = False) -> None:
                    on_pick(color)
                    self.close()

                return _on

            cell.clicked.connect(_bind(hex_c))
            grid.addWidget(cell, i // cols, i % cols)
        root.addWidget(grid_host)

        more = SecondaryButton("更多颜色…")
        more.setMinimumHeight(BUTTON_MIN_HEIGHT)

        def _more() -> None:
            self.close()
            more_slot()

        more.clicked.connect(_more)
        root.addWidget(more)

        # 显式尺寸：布局激活后再按 sizeHint 收紧，避免空面板
        self.adjustSize()
        hint = self.sizeHint()
        self.setMinimumSize(max(hint.width(), 200), max(hint.height(), 80))
        self.resize(self.minimumSize())

    def popup_below(self) -> None:
        anchor = self._anchor
        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            w, h = self.width(), self.height()
            x = min(max(pos.x(), geo.left()), geo.right() - w)
            y = pos.y()
            if y + h > geo.bottom():
                y = max(geo.top(), anchor.mapToGlobal(QPoint(0, 0)).y() - h)
            pos = QPoint(x, y)
        self.move(pos)
        self.show()
        self.raise_()

    def closeEvent(self, event) -> None:  # noqa: N802
        # 点回锚点按钮时：Popup 先关再触发 clicked，需吞掉一次以免立刻重开
        btn = self._anchor
        if isinstance(btn, QToolButton):
            btn.setProperty("_color_popup_suppress", True)

            def _clear() -> None:
                btn.setProperty("_color_popup_suppress", False)

            QTimer.singleShot(0, _clear)
        super().closeEvent(event)


def _swatch_icon(hex_color: str | None, *, size: int = 22, dpr: float = 1.0) -> QIcon:
    """色板方块；物理像素绘制，避免小色点难点、发糊。"""
    px = max(16, int(size * max(dpr, 1.0)))
    pm = QPixmap(px, px)
    pm.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = max(1, int(px * 0.08))
    r = max(2, int(px * 0.18))
    if hex_color:
        painter.setBrush(QBrush(QColor(hex_color)))
        painter.setPen(QPen(QColor("#94A3B8"), max(1, int(dpr))))
        painter.drawRoundedRect(m, m, px - 2 * m, px - 2 * m, r, r)
    else:
        painter.setPen(QPen(QColor("#94A3B8"), max(1, int(dpr)), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(m, m, px - 2 * m, px - 2 * m, r, r)
        painter.setPen(QPen(QColor("#EF4444"), max(2, int(1.5 * dpr))))
        painter.drawLine(m + 2, px - m - 2, px - m - 2, m + 2)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def _text_color_tool_icon(hex_color: str, *, size: int = 20, dpr: float = 1.0) -> QIcon:
    """Word 式「A + 底色条」字色按钮图标。"""
    px = max(16, int(size * max(dpr, 1.0)))
    pm = QPixmap(px, px)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    from PySide6.QtGui import QFont as _QFont

    font = _QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(max(10, int(px * 0.62)))
    p.setFont(font)
    p.setPen(QColor("#1D1D1F"))
    p.drawText(0, 0, px, int(px * 0.78), int(Qt.AlignmentFlag.AlignCenter), "A")
    bar_h = max(3, int(px * 0.16))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(hex_color)))
    p.drawRoundedRect(int(px * 0.12), px - bar_h - 1, int(px * 0.76), bar_h, 1, 1)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def _highlight_tool_icon(hex_color: str | None, *, size: int = 20, dpr: float = 1.0) -> QIcon:
    """马克笔式高亮按钮：笔头 + 色条。"""
    px = max(16, int(size * max(dpr, 1.0)))
    pm = QPixmap(px, px)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#64748B")))
    p.drawRoundedRect(int(px * 0.28), int(px * 0.08), int(px * 0.44), int(px * 0.42), 2, 2)
    tip = QColor(hex_color) if hex_color else QColor("#E2E8F0")
    p.setBrush(QBrush(tip))
    p.drawRoundedRect(int(px * 0.22), int(px * 0.48), int(px * 0.56), int(px * 0.22), 2, 2)
    bar = QColor(hex_color) if hex_color else QColor("#CBD5E1")
    p.setBrush(QBrush(bar))
    bar_h = max(3, int(px * 0.14))
    p.drawRoundedRect(int(px * 0.1), px - bar_h - 1, int(px * 0.8), bar_h, 1, 1)
    if not hex_color:
        p.setPen(QPen(QColor("#EF4444"), max(2, int(1.2 * dpr))))
        p.drawLine(int(px * 0.2), px - 2, int(px * 0.8), int(px * 0.55))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


class _OutlineTree(TreeWidget):
    """Outline：拖放只发意图，由存储落盘后重载；Tab / Enter 交给页面。"""

    drop_resolved = Signal(str, object, int)  # nid, parent_id|None, order
    indent_requested = Signal()
    outdent_requested = Signal()
    create_below_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("OutlineTree")
        self.setAlternatingRowColors(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # 自绘投放指示：避免系统粗蓝底 + 虚线框
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)
        self.setIndentation(22)
        self.setItemsExpandable(True)
        self.setExpandsOnDoubleClick(False)
        self.setAnimated(False)
        self.setAllColumnsShowFocus(True)
        self._dragging = False
        self._drop_item: QTreeWidgetItem | None = None
        self._drop_where = QAbstractItemView.DropIndicatorPosition.OnViewport

    def focusNextPrevChild(self, _next: bool) -> bool:  # noqa: N802
        return False

    @staticmethod
    def _nid(item: QTreeWidgetItem | None) -> str:
        if item is None:
            return ""
        return str(item.data(0, Qt.ItemDataRole.UserRole) or "")

    @staticmethod
    def _is_under(ancestor: QTreeWidgetItem, maybe: QTreeWidgetItem) -> bool:
        cur: QTreeWidgetItem | None = maybe
        while cur is not None:
            if cur is ancestor:
                return True
            cur = cur.parent()
        return False

    def _parent_id_of(self, item: QTreeWidgetItem) -> str | None:
        p = item.parent()
        if p is None:
            return None
        pid = self._nid(p)
        return pid or None

    def _sibling_index(self, item: QTreeWidgetItem) -> int:
        p = item.parent()
        if p is None:
            return self.indexOfTopLevelItem(item)
        return p.indexOfChild(item)

    def _accent(self) -> QColor:
        from app.app_state import AppState

        pal = AppState.get().palette or {}
        return QColor(str(pal.get("primary") or pal.get("nav_indicator") or "#2563EB"))

    def _make_drag_pixmap(self, item: QTreeWidgetItem) -> QPixmap:
        """半透明轻卡片，不挡背后投放位置。"""
        vr = self.visualItemRect(item)
        w = max(72, min(220, vr.width() + 8))
        h = max(28, vr.height())
        dpr = float(self.devicePixelRatioF() or 1.0)
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(dpr)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        # 整体偏淡，能看清底下列表
        p.setOpacity(0.72)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, w - 1, h - 1, 6, 6)
        p.setPen(QPen(QColor(37, 99, 235, 90), 1.0))
        p.setBrush(QColor(255, 255, 255, 210))
        p.drawPath(path)
        icon = item.icon(0)
        x = 8
        if not icon.isNull():
            icon.paint(p, x, (h - 16) // 2, 16, 16)
            x += 22
        p.setPen(QColor(30, 41, 59, 220))
        font = QFont(self.font())
        font.setPointSize(max(9, font.pointSize()))
        p.setFont(font)
        text = item.text(0) or "记事"
        p.drawText(
            QRect(x, 0, w - x - 8, h),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            text,
        )
        p.end()
        return pm

    def startDrag(self, supportedActions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        nid = self._nid(item)
        if not nid:
            return
        mime = QMimeData()
        mime.setData("application/x-toa-outline-note", QByteArray(nid.encode("utf-8")))
        mime.setText(nid)
        drag = QDrag(self)
        drag.setMimeData(mime)
        pm = self._make_drag_pixmap(item)
        drag.setPixmap(pm)
        vr = self.visualItemRect(item)
        hot = self.mapFromGlobal(self.cursor().pos()) - vr.topLeft()
        # hotspot 用逻辑像素（与 pixmap 显示尺寸一致）
        lw = max(1, int(pm.width() / max(pm.devicePixelRatio(), 1.0)))
        lh = max(1, int(pm.height() / max(pm.devicePixelRatio(), 1.0)))
        drag.setHotSpot(
            QPoint(max(8, min(lw - 8, hot.x())), max(4, min(lh - 4, hot.y())))
        )
        self._dragging = True
        self._drop_item = None
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._dragging = False
            self._drop_item = None
            self._drop_where = QAbstractItemView.DropIndicatorPosition.OnViewport
            self.viewport().update()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat("application/x-toa-outline-note") or event.source() is self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if not (
            event.mimeData().hasFormat("application/x-toa-outline-note") or event.source() is self
        ):
            event.ignore()
            return
        event.acceptProposedAction()
        pos = event.position().toPoint()
        target = self.itemAt(pos)
        dragged = self.currentItem()
        if target is None or target is dragged or (
            dragged is not None and self._is_under(dragged, target)
        ):
            self._drop_item = None
            self._drop_where = QAbstractItemView.DropIndicatorPosition.OnViewport
            self.viewport().update()
            return
        rect = self.visualItemRect(target)
        y = pos.y()
        top = rect.top()
        bot = rect.bottom()
        band = max(8, rect.height() // 3)
        if y <= top + band:
            where = QAbstractItemView.DropIndicatorPosition.AboveItem
        elif y >= bot - band:
            where = QAbstractItemView.DropIndicatorPosition.BelowItem
        else:
            where = QAbstractItemView.DropIndicatorPosition.OnItem
        if self._drop_item is not target or self._drop_where != where:
            self._drop_item = target
            self._drop_where = where
            self.viewport().update()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._drop_item = None
        self._drop_where = QAbstractItemView.DropIndicatorPosition.OnViewport
        self.viewport().update()
        super().dragLeaveEvent(event)

    def viewportEvent(self, event) -> bool:  # noqa: N802
        handled = super().viewportEvent(event)
        if event.type() == QEvent.Type.Paint and self._dragging:
            self._paint_drop_hint()
        return handled

    def _paint_drop_hint(self) -> None:
        """浅色插线 / 嵌套高亮 + 松手说明，不挡背后。"""
        item = self._drop_item
        if item is None:
            return
        rect = self.visualItemRect(item)
        if not rect.isValid():
            return
        accent = self._accent()
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        where = self._drop_where
        if where == QAbstractItemView.DropIndicatorPosition.OnItem:
            fill = QColor(accent)
            fill.setAlpha(38)
            border = QColor(accent)
            border.setAlpha(160)
            p.setPen(QPen(border, 1.5))
            p.setBrush(fill)
            p.drawRoundedRect(rect.adjusted(2, 1, -2, -1), 5, 5)
            tip = "松手：挂到此项下"
        else:
            y = rect.top() if where == QAbstractItemView.DropIndicatorPosition.AboveItem else rect.bottom()
            p.setPen(QPen(accent, 2.0))
            p.drawLine(rect.left() + 6, y, rect.right() - 4, y)
            p.setBrush(accent)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPoint(rect.left() + 8, y), 3, 3)
            tip = (
                "松手：插到上方"
                if where == QAbstractItemView.DropIndicatorPosition.AboveItem
                else "松手：插到下方"
            )
        # 轻提示条
        font = QFont(self.font())
        font.setPointSize(max(8, font.pointSize() - 1))
        p.setFont(font)
        metrics = p.fontMetrics()
        tw = metrics.horizontalAdvance(tip) + 12
        th = metrics.height() + 6
        tip_x = min(rect.left() + 20, self.viewport().width() - tw - 6)
        tip_y = rect.bottom() + 4
        if tip_y + th > self.viewport().height():
            tip_y = max(2, rect.top() - th - 4)
        tip_rect = QRect(tip_x, tip_y, tw, th)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 200))
        p.drawRoundedRect(tip_rect, 4, 4)
        p.setPen(QColor("#F8FAFC"))
        p.drawText(tip_rect, int(Qt.AlignmentFlag.AlignCenter), tip)
        p.end()

    def dropEvent(self, event) -> None:  # noqa: N802
        dragged = self.currentItem()
        if dragged is None:
            event.ignore()
            return
        nid = self._nid(dragged)
        if not nid:
            event.ignore()
            return
        pos = event.position().toPoint()
        target = self.itemAt(pos)
        # 禁止 Qt InternalMove 改树：否则会在我们重载之后再删掉被拖行 → 条目「消失」
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()

        # 优先用拖动过程中算好的投放位（与指示一致）
        if self._drop_item is not None:
            target = self._drop_item
            indicator = self._drop_where
        else:
            indicator = QAbstractItemView.DropIndicatorPosition.OnViewport

        self._drop_item = None
        self._dragging = False
        self.viewport().update()

        if target is None:
            self.drop_resolved.emit(nid, None, self.topLevelItemCount())
            return
        if target is dragged or self._is_under(dragged, target):
            return

        tid = self._nid(target)
        nest_under = indicator == QAbstractItemView.DropIndicatorPosition.OnItem
        outdent_after_parent = (
            not nest_under
            and pos.x() < self.visualItemRect(target).left() - 4
            and target.parent() is not None
        )

        if nest_under:
            self.drop_resolved.emit(nid, tid, max(0, target.childCount()))
        elif outdent_after_parent:
            parent = target.parent()
            assert parent is not None
            gp_id = self._parent_id_of(parent)
            self.drop_resolved.emit(nid, gp_id, self._sibling_index(parent) + 1)
        elif indicator == QAbstractItemView.DropIndicatorPosition.AboveItem:
            self.drop_resolved.emit(nid, self._parent_id_of(target), self._sibling_index(target))
        else:
            self.drop_resolved.emit(
                nid, self._parent_id_of(target), self._sibling_index(target) + 1
            )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Tab and not mods & Qt.KeyboardModifier.ShiftModifier:
            self.indent_requested.emit()
            event.accept()
            return
        if key in (Qt.Key.Key_Backtab,) or (
            key == Qt.Key.Key_Tab and mods & Qt.KeyboardModifier.ShiftModifier
        ):
            self.outdent_requested.emit()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            mods & Qt.KeyboardModifier.ControlModifier
        ):
            self.create_below_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _OutlineKeyFilter(QObject):
    """树有焦点时兜底 Tab / Shift+Tab（部分平台不进 keyPressEvent）。"""

    def __init__(self, tree: _OutlineTree, parent=None) -> None:
        super().__init__(parent)
        self._tree = tree

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is not self._tree or event.type() != QEvent.Type.KeyPress:
            return False
        assert isinstance(event, QKeyEvent)
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Tab and not mods & Qt.KeyboardModifier.ShiftModifier:
            self._tree.indent_requested.emit()
            return True
        if key in (Qt.Key.Key_Backtab,) or (
            key == Qt.Key.Key_Tab and mods & Qt.KeyboardModifier.ShiftModifier
        ):
            self._tree.outdent_requested.emit()
            return True
        return False


class QuickNotepadPage(BasePage):
    page_id = "quick_notepad"
    page_title = "快速记事"

    _incoming: tuple[str, str, str | None] | None = None  # title, body, image_path

    @classmethod
    def stash_incoming(
        cls,
        body: str = "",
        *,
        title: str = "来自剪贴板",
        image_path: str | None = None,
    ) -> None:
        cls._incoming = (title, body or "", image_path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_id: str | None = None
        self._shortcuts: list[QShortcut] = []
        self._rebuilding_tree = False
        self._loading_body = False
        self._using_wysiwyg = False
        self._view_mode = "edit"
        self._editor_fullscreen = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(800)
        self._autosave_timer.timeout.connect(self._on_autosave)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        header = PageHeader(
            "快速记事", "大纲速记 · 源码/设计/预览 · 剪贴板/截图可一键落入正文"
        )
        scroll.add_widget(header)
        self._page_header = header
        hint = SemanticLabel(
            "Tab / Shift+Tab 升降级 · Enter 新建同级 · 右侧正文支持源码、所见即所得设计与预览页签。",
            kind="info",
            compact=True,
        )
        scroll.add_widget(hint)
        self._hint_label = hint

        tools = QHBoxLayout()
        self._tools_host = QWidget()
        self._tools_host.setObjectName("NotepadToolbar")
        self._tools_host.setLayout(tools)
        tools.setContentsMargins(12, 8, 12, 8)
        tools.setSpacing(10)
        self._search = LineEdit()
        self._search.setObjectName("NotepadSearchEdit")
        self._search.setPlaceholderText("搜索标题/正文…")
        self._search.textChanged.connect(lambda _t: self._reload_tree())
        tools.addWidget(self._search, 1)
        tools.addWidget(HintLabel("模式"))
        self._mode = ComboBox()
        self._mode.setMinimumWidth(168)
        self._mode.setMinimumContentsLength(12)
        self._mode.setSizeAdjustPolicy(
            ComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._mode.addItem("简约 · 纯文本", "simple")
        self._mode.addItem("多功能 · 源码/设计/预览", "rich")
        self._mode.setCurrentIndex(1)
        self._mode.currentIndexChanged.connect(self._on_mode_changed)
        tools.addWidget(self._mode)
        scroll.add_widget(self._tools_host)

        body = QHBoxLayout()
        body.setSpacing(14)
        self._body_host = QWidget()
        self._body_host.setLayout(body)
        tree_box = FormSection("大纲")
        tree_box.setMaximumWidth(360)
        self._tree_box = tree_box
        self._tree_panel = QWidget()
        self._tree_panel.setObjectName("OutlineTreePanel")
        tree_panel_lay = QVBoxLayout(self._tree_panel)
        tree_panel_lay.setContentsMargins(8, 8, 8, 8)
        tree_panel_lay.setSpacing(8)
        tree_head_host = QWidget()
        tree_head_host.setObjectName("OutlineTreeHeader")
        tree_head = QHBoxLayout(tree_head_host)
        tree_head.setContentsMargins(4, 0, 4, 0)
        tree_head.addWidget(HintLabel("目录"))
        tree_head.addStretch(1)
        self._outline_count = SemanticLabel("", kind="info", compact=True)
        tree_head.addWidget(self._outline_count)
        tree_panel_lay.addWidget(tree_head_host)
        self._tree = _OutlineTree()
        self._tree.setMinimumHeight(280)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.currentItemChanged.connect(self._on_tree_select)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self._tree.drop_resolved.connect(self._on_drop_resolved)
        self._tree.indent_requested.connect(self._on_indent)
        self._tree.outdent_requested.connect(self._on_outdent)
        self._tree.create_below_requested.connect(self._on_new_below)
        self._key_filter = _OutlineKeyFilter(self._tree, self)
        self._tree.installEventFilter(self._key_filter)
        tree_panel_lay.addWidget(self._tree, 1)
        tree_box.add_widget(self._tree_panel, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        btn_new = PrimaryButton("新建")
        btn_new.setToolTip("Ctrl+N / Enter")
        btn_new.clicked.connect(self._on_new_note)
        row.addWidget(btn_new)
        row.addWidget(
            self._outline_tool_btn(
                "right",
                "缩进",
                "降级 · 成为上一条的子项（Tab / Ctrl+]）",
                self._on_indent,
            )
        )
        row.addWidget(
            self._outline_tool_btn(
                "left",
                "升级",
                "升级 · 提到与父级同级（Shift+Tab / Ctrl+[）",
                self._on_outdent,
            )
        )
        btn_edit = SecondaryButton("标题")
        btn_edit.setToolTip("F2 或双击条目修改标题")
        btn_edit.clicked.connect(self._on_edit_title)
        row.addWidget(btn_edit)
        btn_del = DangerButton("删除")
        btn_del.clicked.connect(self._on_delete)
        row.addWidget(btn_del)
        row.addStretch(1)
        tree_box.add_layout(row)
        body.addWidget(tree_box)

        editor = FormSection("正文")
        self._editor_box = editor
        self._editor_chrome = QWidget()
        self._editor_chrome.setObjectName("NotepadEditorChrome")
        title_row = QHBoxLayout(self._editor_chrome)
        title_row.setContentsMargins(10, 6, 10, 6)
        title_row.setSpacing(10)
        self._title_label = SectionTitle("未选择")
        title_row.addWidget(self._title_label, 1)

        self._view_tabs_host = QFrame()
        self._view_tabs_host.setObjectName("EditorViewTabs")
        tabs_lay = QHBoxLayout(self._view_tabs_host)
        tabs_lay.setContentsMargins(3, 3, 3, 3)
        tabs_lay.setSpacing(0)
        self._view_tab_bar = QTabBar()
        self._view_tab_bar.setObjectName("EditorViewTabBar")
        self._view_tab_bar.setDrawBase(False)
        self._view_tab_bar.setExpanding(False)
        self._view_tab_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label in _VIEW_TAB_LABELS:
            self._view_tab_bar.addTab(label)
        self._view_tab_bar.currentChanged.connect(self._on_view_tab_changed)
        tabs_lay.addWidget(self._view_tab_bar)
        title_row.addWidget(self._view_tabs_host)

        self._btn_fullscreen = SecondaryButton("全屏")
        self._btn_fullscreen.setObjectName("NotepadFullscreenBtn")
        self._btn_fullscreen.setToolTip("隐藏大纲，专注正文 · Esc 退出")
        self._btn_fullscreen.clicked.connect(self._toggle_editor_fullscreen)
        title_row.addWidget(self._btn_fullscreen)
        self._save_hint = SemanticLabel("", kind="success", compact=True)
        self._save_hint.setVisible(False)
        title_row.addWidget(self._save_hint)
        editor.add_widget(self._editor_chrome)

        self._fmt_toolbar_host = QWidget()
        self._fmt_toolbar_host.setObjectName("NotepadFmtToolbar")
        self._fmt_toolbar = QHBoxLayout(self._fmt_toolbar_host)
        self._fmt_toolbar.setContentsMargins(8, 6, 8, 6)
        self._fmt_toolbar.setSpacing(4)
        self._fmt_btns: list = []
        for label, tip, fn in (
            ("H1", "标题 1（蓝）", lambda: self._fmt_heading(1)),
            ("H2", "标题 2（青）", lambda: self._fmt_heading(2)),
            ("H3", "标题 3（琥珀）", lambda: self._fmt_heading(3)),
            ("B", "加粗", lambda: self._fmt_toggle_bold()),
            ("I", "斜体", lambda: self._fmt_toggle_italic()),
            ("U", "下划线", lambda: self._fmt_toggle_underline()),
            ("S", "删除线", lambda: self._fmt_toggle_strike()),
            ("•", "项目符号", lambda: self._fmt_list(False)),
            ("1.", "编号列表", lambda: self._fmt_list(True)),
            ("链接", "插入超链接", self._fmt_link),
            ("图片", "插入本地图片", self._fmt_image),
            ("清除", "清除选区文字样式", self._fmt_clear),
        ):
            btn = SecondaryButton(label)
            btn.setToolTip(tip)
            btn.setMaximumWidth(56 if len(label) <= 2 else 64)
            btn.clicked.connect(fn)
            self._fmt_toolbar.addWidget(btn)
            self._fmt_btns.append(btn)

        self._fg_color = "#1D1D1F"
        self._hl_color: str | None = "#FEF08A"
        self._btn_fg = self._make_color_menu_btn(
            kind="fg",
            tip="文字颜色 · 点开选色",
            swatches=_TEXT_SWATCHES,
            on_pick=self._fmt_foreground,
            more_slot=self._fmt_pick_foreground,
        )
        self._btn_hl = self._make_color_menu_btn(
            kind="hl",
            tip="背景高亮 · 点开选色",
            swatches=_HIGHLIGHT_SWATCHES,
            on_pick=self._fmt_highlight,
            more_slot=self._fmt_pick_highlight,
        )
        self._fmt_toolbar.addWidget(self._btn_fg)
        self._fmt_toolbar.addWidget(self._btn_hl)
        self._fmt_btns.extend([self._btn_fg, self._btn_hl])
        self._fmt_toolbar.addStretch(1)
        editor.add_widget(self._fmt_toolbar_host)
        self._color_chrome: list = []

        self._editor_surface = QWidget()
        self._editor_surface.setObjectName("NotepadEditorSurface")
        surface_lay = QVBoxLayout(self._editor_surface)
        surface_lay.setContentsMargins(6, 6, 6, 6)
        surface_lay.setSpacing(0)
        self._view_stack = QStackedWidget()
        self._view_stack.setMinimumHeight(320)
        self._view_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plain = PlainTextEdit()
        self._plain.setMinimumHeight(320)
        self._view_stack.addWidget(self._plain)

        self._rich = TextEdit()
        self._rich.setObjectName("MarkdownDesignEdit")
        self._rich.setMinimumHeight(320)
        self._rich.setAcceptRichText(True)
        self._rich.setAutoFormatting(TextEdit.AutoFormattingFlag.AutoBulletList)
        self._view_stack.addWidget(self._rich)

        self._md_source = PlainTextEdit()
        self._md_source.setObjectName("MarkdownSourceEdit")
        self._md_source.setPlaceholderText("Markdown 源码…")
        self._view_stack.addWidget(self._md_source)

        self._md_preview = TextEdit()
        self._md_preview.setObjectName("MarkdownPreviewEdit")
        self._md_preview.setReadOnly(True)
        self._view_stack.addWidget(self._md_preview)

        self._md_highlighter = MarkdownHighlighter(
            self._md_source.document(), AppState.get().palette or {}
        )
        surface_lay.addWidget(self._view_stack, 1)
        editor.add_widget(self._editor_surface, 1)

        self._body = self._md_source

        self._editor_footer = QWidget()
        self._editor_footer.setObjectName("NotepadEditorFooter")
        footer_lay = QVBoxLayout(self._editor_footer)
        footer_lay.setContentsMargins(0, 8, 0, 0)
        footer_lay.setSpacing(8)
        self._rich_bar = QHBoxLayout()
        self._word_count = HintLabel("")
        self._rich_bar.addWidget(self._word_count, 1)
        btn_time = SecondaryButton("插入时间")
        btn_time.clicked.connect(self._insert_timestamp)
        self._btn_time = btn_time
        self._rich_bar.addWidget(btn_time)
        footer_lay.addLayout(self._rich_bar)
        act = QHBoxLayout()
        self._btn_save = SecondaryButton("立即保存")
        self._btn_save.setToolTip("Ctrl+S · 平时自动保存")
        self._btn_save.clicked.connect(self._on_save_body)
        act.addWidget(self._btn_save)
        btn_import = SecondaryButton("导入 MD")
        btn_import.setToolTip("从 .md 导入并转为所见即所得正文")
        btn_import.clicked.connect(self._on_import_md)
        act.addWidget(btn_import)
        self._btn_import = btn_import
        btn_from_cb = SecondaryButton("从剪贴板")
        btn_from_cb.setToolTip("Ctrl+Shift+V · 文本或图片（含截图）")
        btn_from_cb.clicked.connect(self._from_clipboard)
        act.addWidget(btn_from_cb)
        btn_from_hist = SecondaryButton("最近历史")
        btn_from_hist.setToolTip("把剪贴板历史最新一条落入当前记事")
        btn_from_hist.clicked.connect(self._from_clipboard_history)
        act.addWidget(btn_from_hist)
        btn_to_cb = SecondaryButton("复制正文")
        btn_to_cb.setToolTip("Ctrl+Shift+C · 富文本带 HTML")
        btn_to_cb.clicked.connect(self._to_clipboard)
        act.addWidget(btn_to_cb)
        self._btn_from_cb = btn_from_cb
        self._btn_from_hist = btn_from_hist
        self._btn_to_cb = btn_to_cb
        act.addStretch(1)
        footer_lay.addLayout(act)
        editor.add_widget(self._editor_footer)
        body.addWidget(editor, 1)

        scroll.add_widget(self._body_host)
        self._plain.textChanged.connect(self._on_body_changed)
        self._rich.textChanged.connect(self._on_body_changed)
        self._md_source.textChanged.connect(self._on_md_source_changed)
        self._fullscreen_hide = (
            self._page_header,
            self._hint_label,
            self._tools_host,
            self._tree_box,
        )
        self._fs_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._fs_esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._fs_esc.activated.connect(self._exit_editor_fullscreen)
        sanitize_tree()
        self._reload_tree()
        self.apply_page_focus_policy()
        self._load_mode_from_settings()

    def _set_save_badge(self, state: str) -> None:
        """saved | editing | empty"""
        label = self._save_hint
        if state == "empty":
            label.setVisible(False)
            label.setText("")
            return
        label.setVisible(True)
        if state == "editing":
            label.setText("编辑中…")
            label.setProperty("class", "semantic-warning")
        else:
            label.setText("已保存")
            label.setProperty("class", "semantic-success")
        label.setProperty("compact", "true")
        st = label.style()
        if st is not None:
            st.unpolish(label)
            st.polish(label)

    def _icon_fg(self) -> str:
        pal = AppState.get().palette or {}
        return str(pal.get("text_primary") or pal.get("text") or "#1F2937")

    def _outline_tool_btn(self, icon_name: str, text: str, tip: str, slot) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("FinderToolBtn")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setIcon(get_icon(icon_name, color=self._icon_fg(), size=16, parent=self))
        btn.setIconSize(QSize(16, 16))
        btn.setText(text)
        btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(slot)
        return btn

    def _make_color_menu_btn(
        self,
        *,
        kind: str,
        tip: str,
        swatches: tuple,
        on_pick,
        more_slot,
    ) -> QToolButton:
        """字色 / 高亮：工具栏按钮 → Qt.Popup 色板（不用 QMenu+QWidgetAction）。"""
        btn = QToolButton(self)
        btn.setObjectName("FinderToolBtn")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setText("字色" if kind == "fg" else "高亮")
        btn.setToolTip(tip)
        btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        btn.setMinimumWidth(72)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        title = "文字颜色" if kind == "fg" else "背景高亮"

        def _toggle_palette() -> None:
            if btn.property("_color_popup_suppress"):
                return
            existing = getattr(btn, "_color_popup", None)
            if existing is not None:
                try:
                    if existing.isVisible():
                        existing.close()
                        return
                except RuntimeError:
                    pass
            pop = _ColorPalettePopup(
                btn,
                title=title,
                swatches=swatches,
                on_pick=on_pick,
                more_slot=more_slot,
                dpr=device_pixel_ratio(self),
            )
            btn._color_popup = pop
            pop.popup_below()

        btn.clicked.connect(_toggle_palette)
        if kind == "fg":
            self._refresh_fg_btn_icon(btn)
        else:
            self._refresh_hl_btn_icon(btn)
        return btn

    def _refresh_fg_btn_icon(self, btn: QToolButton | None = None) -> None:
        target = btn or getattr(self, "_btn_fg", None)
        if target is None:
            return
        dpr = device_pixel_ratio(self)
        target.setIcon(_text_color_tool_icon(self._fg_color, size=18, dpr=dpr))
        target.setIconSize(QSize(18, 18))

    def _refresh_hl_btn_icon(self, btn: QToolButton | None = None) -> None:
        target = btn or getattr(self, "_btn_hl", None)
        if target is None:
            return
        dpr = device_pixel_ratio(self)
        target.setIcon(_highlight_tool_icon(self._hl_color, size=18, dpr=dpr))
        target.setIconSize(QSize(18, 18))

    def _load_mode_from_settings(self) -> None:
        st = load_settings()
        mode = str(st.get("editor_mode") or "rich")
        if mode not in ("simple", "rich"):
            mode = "rich"
        idx = self._mode.findData(mode)
        if idx < 0:
            idx = self._mode.findData("rich")
        if idx < 0:
            idx = 0
        self._mode.blockSignals(True)
        self._mode.setCurrentIndex(idx)
        self._mode.blockSignals(False)
        self._mode.setItemText(0, "简约 · 纯文本")
        self._mode.setItemText(1, "多功能 · 源码/设计/预览")
        view = str(st.get("view_mode") or "edit")
        if view not in _VIEW_MODES:
            view = "edit"
        self._view_mode = view
        self._apply_editor_mode(str(self._mode.itemData(idx) or "rich"))

    def _view_mode_index(self, mode: str) -> int:
        try:
            return _VIEW_MODES.index(mode)
        except ValueError:
            return 0

    def _on_view_tab_changed(self, index: int) -> None:
        if index < 0 or index >= len(_VIEW_MODES):
            return
        self._set_view_mode(_VIEW_MODES[index])

    def _set_view_mode(self, mode: str) -> None:
        if str(self._mode.currentData() or "") != "rich":
            return
        if mode not in _VIEW_MODES:
            mode = "edit"
        if mode != self._view_mode:
            self._sync_on_view_mode_leave(self._view_mode)
        self._view_mode = mode
        save_settings({"view_mode": mode})
        self._apply_view_mode(mode)
        self.schedule_primary_focus()

    def _sync_on_view_mode_leave(self, old_mode: str) -> None:
        if self._loading_body:
            return
        if old_mode == "design":
            self._sync_source_from_design()
        elif old_mode == "edit":
            self._sync_design_from_source()

    def _sync_design_from_source(self) -> None:
        if self._loading_body:
            return
        sync_markdown_to_design(self._md_source, self._rich)

    def _sync_source_from_design(self) -> None:
        if self._loading_body:
            return
        sync_design_to_markdown(self._rich, self._md_source)

    def _refresh_current_preview(self) -> None:
        prefer_design = self._using_wysiwyg or rich_has_images(self._rich)
        refresh_editor_preview(
            source=self._md_source,
            preview=self._md_preview,
            design=self._rich,
            prefer_design=prefer_design,
        )

    def _apply_view_mode(self, mode: str) -> None:
        if str(self._mode.currentData() or "") != "rich":
            return
        self._view_tab_bar.blockSignals(True)
        self._view_tab_bar.setCurrentIndex(self._view_mode_index(mode))
        self._view_tab_bar.blockSignals(False)
        if mode == "preview":
            self._refresh_current_preview()
            self._view_stack.setCurrentWidget(self._md_preview)
            self._body = self._md_preview
        elif mode == "design":
            self._sync_design_from_source()
            self._view_stack.setCurrentWidget(self._rich)
            self._body = self._rich
        else:
            self._view_stack.setCurrentWidget(self._md_source)
            self._body = self._md_source
        self._sync_view_chrome()

    def _on_md_source_changed(self) -> None:
        if self._loading_body:
            return
        if not self._using_wysiwyg or not rich_has_images(self._rich):
            self._using_wysiwyg = False
        self._on_body_changed()
        if self._view_mode == "preview":
            self._refresh_current_preview()

    def _load_note_body(self, body: str) -> None:
        mode = str(self._mode.currentData() or "")
        self._loading_body = True
        try:
            if mode != "rich":
                self._using_wysiwyg = False
                self._plain.setPlainText(body)
                return
            if looks_like_html(body):
                self._using_wysiwyg = True
                load_body_into(self._rich, body)
                sync_design_to_markdown(self._rich, self._md_source)
            else:
                self._using_wysiwyg = False
                self._md_source.setPlainText(body)
                sync_markdown_to_design(self._md_source, self._rich)
            self._apply_view_mode(self._view_mode)
        finally:
            self._loading_body = False

    def _toggle_editor_fullscreen(self) -> None:
        self._editor_fullscreen = not self._editor_fullscreen
        for w in self._fullscreen_hide:
            if w is not None:
                w.setVisible(not self._editor_fullscreen)
        self._btn_fullscreen.setText("退出全屏" if self._editor_fullscreen else "全屏")
        self.report_status(
            "编辑区全屏 · Esc 退出" if self._editor_fullscreen else "已退出全屏",
            level=StatusLevel.INFO,
        )
        self.schedule_primary_focus()

    def _exit_editor_fullscreen(self) -> None:
        if self._editor_fullscreen:
            self._toggle_editor_fullscreen()

    def _sync_view_chrome(self) -> None:
        rich = str(self._mode.currentData() or "") == "rich"
        self._view_tabs_host.setVisible(rich)
        design = rich and self._view_mode == "design"
        for btn in self._fmt_btns:
            btn.setVisible(design)
        for w in getattr(self, "_color_chrome", []):
            w.setVisible(design)
        self._btn_import.setVisible(rich)
        self._btn_time.setVisible(design)

    def _on_mode_changed(self, _index: int) -> None:
        mode = str(self._mode.currentData() or "rich")
        if mode not in ("simple", "rich"):
            mode = "rich"
        self._flush_autosave()
        if mode == "rich":
            plain = self._plain.toPlainText()
            self._md_source.setPlainText(plain)
            sync_markdown_to_design(self._md_source, self._rich)
            self._using_wysiwyg = False
        else:
            if self._view_mode == "design" or self._using_wysiwyg:
                self._plain.setPlainText(self._rich.toPlainText())
            else:
                self._plain.setPlainText(self._md_source.toPlainText())
            self.report_status(
                "已切到简约：仅保留纯文本（排版不保留）",
                level=StatusLevel.WARNING,
            )
        save_settings({"editor_mode": mode})
        self._apply_editor_mode(mode)
        self.schedule_primary_focus()

    def _apply_editor_mode(self, mode: str) -> None:
        rich = mode == "rich"
        self._word_count.setVisible(True)
        for btn in (self._btn_from_cb, self._btn_from_hist, self._btn_to_cb):
            btn.setVisible(True)
        font = QFont("Microsoft YaHei UI")
        font.setPointSize(10)
        if rich:
            self._rich.setFont(font)
            self._md_source.setFont(font)
            self._md_preview.setFont(font)
            self._apply_view_mode(self._view_mode)
            self._md_source.setPlaceholderText("Markdown 源码…")
        else:
            self._plain.setFont(font)
            self._plain.setPlaceholderText("在此输入纯文本…")
            self._body = self._plain
            self._view_stack.setCurrentWidget(self._plain)
        self._sync_view_chrome()
        self._update_word_count()

    def _fmt_merge(self, fmt: QTextCharFormat, *, select_word_if_empty: bool = True) -> None:
        cur = self._rich.textCursor()
        if select_word_if_empty and not cur.hasSelection():
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
        if cur.hasSelection():
            cur.mergeCharFormat(fmt)
        self._rich.mergeCurrentCharFormat(fmt)
        self._rich.setTextCursor(cur)
        self.schedule_primary_focus(move_cursor_end=False)

    def _fmt_heading(self, level: int) -> None:
        sizes = {1: 22, 2: 18, 3: 15}
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontPointSize(sizes.get(level, 14))
        hex_c = _HEADING_COLORS.get(level)
        if hex_c:
            fmt.setForeground(QBrush(QColor(hex_c)))
        self._fmt_merge(fmt)

    def _fmt_toggle_bold(self) -> None:
        cur = self._rich.textCursor()
        weight = cur.charFormat().fontWeight()
        fmt = QTextCharFormat()
        fmt.setFontWeight(
            QFont.Weight.Normal if weight > QFont.Weight.Normal else QFont.Weight.Bold
        )
        self._fmt_merge(fmt)

    def _fmt_toggle_italic(self) -> None:
        cur = self._rich.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cur.charFormat().fontItalic())
        self._fmt_merge(fmt)

    def _fmt_toggle_underline(self) -> None:
        cur = self._rich.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not cur.charFormat().fontUnderline())
        self._fmt_merge(fmt)

    def _fmt_toggle_strike(self) -> None:
        cur = self._rich.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not cur.charFormat().fontStrikeOut())
        self._fmt_merge(fmt)

    def _fmt_foreground(self, hex_color: str) -> None:
        self._fg_color = hex_color
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(QColor(hex_color)))
        self._fmt_merge(fmt, select_word_if_empty=True)
        self._refresh_fg_btn_icon()
        self.report_status("已设字色", level=StatusLevel.INFO)

    def _fmt_highlight(self, hex_color: str | None) -> None:
        self._hl_color = hex_color
        fmt = QTextCharFormat()
        if hex_color:
            fmt.setBackground(QBrush(QColor(hex_color)))
        else:
            fmt.setBackground(QBrush())
        self._fmt_merge(fmt, select_word_if_empty=True)
        self._refresh_hl_btn_icon()
        self.report_status("已设高亮" if hex_color else "已取消高亮", level=StatusLevel.INFO)

    def _fmt_pick_foreground(self) -> None:
        cur = self._rich.textCursor().charFormat().foreground().color()
        color = QColorDialog.getColor(cur if cur.isValid() else QColor("#1D1D1F"), self, "选择字色")
        if color.isValid():
            self._fmt_foreground(color.name())

    def _fmt_pick_highlight(self) -> None:
        cur = self._rich.textCursor().charFormat().background().color()
        color = QColorDialog.getColor(
            cur if cur.isValid() else QColor("#FEF08A"), self, "选择高亮色"
        )
        if color.isValid():
            self._fmt_highlight(color.name())

    def _fmt_clear(self) -> None:
        cur = self._rich.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
        plain = QTextCharFormat()
        cur.setCharFormat(plain)
        self._rich.setCurrentCharFormat(plain)
        self._rich.setTextCursor(cur)
        self.schedule_primary_focus(move_cursor_end=False)
        self.report_status("已清除样式", level=StatusLevel.INFO)

    def _fmt_list(self, numbered: bool) -> None:
        cur = self._rich.textCursor()
        style = (
            QTextListFormat.Style.ListDecimal
            if numbered
            else QTextListFormat.Style.ListDisc
        )
        cur.createList(style)
        self._rich.setTextCursor(cur)
        self.schedule_primary_focus()

    def _fmt_link(self) -> None:
        cur = self._rich.textCursor()
        selected = cur.selectedText().replace("\u2029", " ") or "链接文字"
        dlg = FormEditDialog(
            self,
            title="插入链接",
            fields=[("显示文字", "text"), ("网址", "url")],
        )
        dlg.set_values({"text": selected, "url": "https://"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        text = (vals.get("text") or "链接").strip()
        url = (vals.get("url") or "").strip()
        if not url:
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QBrush(QColor("#2563EB")))
        fmt.setFontUnderline(True)
        cur.insertText(text, fmt)
        self._rich.setTextCursor(cur)
        self.schedule_primary_focus()

    def _fmt_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "插入图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;所有文件 (*.*)",
        )
        if not path:
            return
        if not insert_image(self._rich, Path(path)):
            show_warning(self, "无法插入该图片。")
            return
        self.report_status("已插入图片", level=StatusLevel.SUCCESS)
        self.schedule_primary_focus()

    def _active_plain_text(self) -> str:
        if str(self._mode.currentData() or "") == "rich":
            if self._view_mode == "design" or self._using_wysiwyg:
                return self._rich.toPlainText()
            return self._md_source.toPlainText()
        return self._plain.toPlainText()

    def _on_body_changed(self) -> None:
        if (
            not self._loading_body
            and str(self._mode.currentData() or "") == "rich"
            and self._view_mode == "design"
        ):
            self._using_wysiwyg = True
        self._update_word_count()
        if self._loading_body or self._rebuilding_tree:
            return
        self._set_save_badge("editing")
        self._autosave_timer.start()

    def _update_word_count(self) -> None:
        text = self._active_plain_text()
        chars = len(text)
        lines = 0 if not text else len(text.splitlines())
        self._word_count.setText(f"{chars} 字 · {lines} 行")

    def _flush_autosave(self) -> None:
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
        if self._current_id is None and not self._active_plain_text().strip():
            return
        self._on_save_body(silent=True)

    def _on_autosave(self) -> None:
        self._on_save_body(silent=True)

    def _insert_timestamp(self) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        if str(self._mode.currentData() or "") == "rich":
            if self._view_mode == "design":
                cur = self._rich.textCursor()
                cur.insertText(stamp)
                self._rich.setTextCursor(cur)
            else:
                cur = self._md_source.textCursor()
                cur.insertText(stamp)
                self._md_source.setTextCursor(cur)
        else:
            cur = self._plain.textCursor()
            cur.insertText(stamp)
            self._plain.setTextCursor(cur)
        self.schedule_primary_focus()

    def primary_focus_widget(self):
        mode = str(self._mode.currentData() or "")
        if mode == "rich":
            if self._view_mode == "design":
                return self._rich
            if self._view_mode == "preview":
                return self._view_tab_bar
            return self._md_source
        return self._plain

    def focus_tab_widgets(self) -> list:
        mode = str(self._mode.currentData() or "")
        if mode == "rich":
            if self._view_mode == "design":
                editor = self._rich
            elif self._view_mode == "preview":
                editor = self._view_tab_bar
            else:
                editor = self._md_source
        else:
            editor = self._plain
        chain = [self._search, self._tree, editor, self._btn_save]
        if self._btn_from_cb.isVisible():
            chain.extend([self._btn_from_cb, self._btn_from_hist, self._btn_to_cb])
        return chain

    def _ensure_shortcuts(self) -> None:
        if self._shortcuts:
            return
        win = self.window()
        if win is None:
            return
        for seq, slot in (
            ("Ctrl+S", self._on_save_body),
            ("Ctrl+N", self._on_new_note),
            ("F2", self._on_edit_title),
            ("Ctrl+]", self._on_indent),
            ("Ctrl+[", self._on_outdent),
            ("Alt+Right", self._on_indent),
            ("Alt+Left", self._on_outdent),
            ("Ctrl+Shift+V", self._from_clipboard),
            ("Ctrl+Shift+C", self._to_clipboard),
        ):
            sc = QShortcut(QKeySequence(seq), win)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)
            sc.setEnabled(False)
            self._shortcuts.append(sc)

    def _set_shortcuts_active(self, on: bool) -> None:
        self._ensure_shortcuts()
        for sc in self._shortcuts:
            sc.setEnabled(on)

    def _sibling_parent_id(self) -> str | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        nid = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        node = find_note(nid)
        if not node:
            return None
        pid = node.get("parent_id")
        return str(pid) if pid else None

    def _node_matches_filter(self, node: dict, q: str, by_id: dict[str, dict]) -> bool:
        if not q:
            return True
        blob = f"{node.get('title') or ''} {node.get('body') or ''}".lower()
        if q in blob:
            return True
        for child in by_id.values():
            if str(child.get("parent_id") or "") == str(node.get("id")):
                if self._node_matches_filter(child, q, by_id):
                    return True
        return False

    def _filtered_nodes(self) -> list[dict]:
        q = (self._search.text() or "").strip().lower()
        nodes = load_nodes()
        if not q:
            return nodes
        by_id = {str(n.get("id")): n for n in nodes}
        return [n for n in nodes if self._node_matches_filter(n, q, by_id)]

    def _make_tree_item(self, node: dict, *, has_children: bool = False) -> QTreeWidgetItem:
        title = str(node.get("title") or "无标题")
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.ItemDataRole.UserRole, str(node.get("id")))
        item.setToolTip(0, f"{node.get('updated', '')} · {title}\n双击改标题")
        icon_name = "folder" if has_children else "file-text"
        item.setIcon(0, get_icon(icon_name, color=self._icon_fg(), size=16, parent=self))
        item.setFlags(
            (item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
             | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            & ~Qt.ItemFlag.ItemIsEditable
        )
        item.setExpanded(True)
        return item

    def _populate_tree(
        self,
        parent_item: QTreeWidgetItem | None,
        parent_id: str | None,
        visible_ids: set[str],
    ) -> None:
        for node in children_of(parent_id):
            nid = str(node.get("id"))
            if nid not in visible_ids:
                continue
            kids = [c for c in children_of(nid) if str(c.get("id")) in visible_ids]
            item = self._make_tree_item(node, has_children=bool(kids))
            if parent_item is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            self._populate_tree(item, nid, visible_ids)

    def _reload_tree(self, *, keep_selection: str | None = None) -> None:
        sel = keep_selection or self._current_id
        self._rebuilding_tree = True
        self._tree.clear()
        nodes = self._filtered_nodes()
        visible_ids = {str(n.get("id")) for n in nodes}
        # 保证父链也在可见集中，否则子项无法挂载而「消失」
        by_id = {str(n.get("id")): n for n in load_nodes()}
        for nid in list(visible_ids):
            cur = by_id.get(nid)
            while cur is not None:
                pid = cur.get("parent_id")
                if not pid:
                    break
                pid_s = str(pid)
                visible_ids.add(pid_s)
                cur = by_id.get(pid_s)
        self._populate_tree(None, None, visible_ids)
        self._tree.expandAll()
        self._rebuilding_tree = False
        self.report_status(f"共 {len(nodes)} 条记事")
        self._outline_count.setText(f"{len(nodes)} 条")
        if sel:
            self._select_tree_id(sel)
        elif self._tree.topLevelItemCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _select_tree_id(self, node_id: str) -> None:
        target = str(node_id)

        def walk(item: QTreeWidgetItem | None) -> QTreeWidgetItem | None:
            if item is None:
                for i in range(self._tree.topLevelItemCount()):
                    found = walk(self._tree.topLevelItem(i))
                    if found is not None:
                        return found
                return None
            if str(item.data(0, Qt.ItemDataRole.UserRole)) == target:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        item = walk(None)
        if item is not None:
            # 展开整条父链，避免子项被折叠后「像消失」
            p = item.parent()
            while p is not None:
                p.setExpanded(True)
                p = p.parent()
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item)

    def _on_drop_resolved(self, nid: str, parent_id: object, order: int) -> None:
        pid = None if parent_id in (None, "") else str(parent_id)

        def apply() -> None:
            ok = move_node(nid, pid, int(order))
            # 无论成败都从存储重载，抵消 Qt 拖放对视图的破坏
            self._reload_tree(keep_selection=nid)
            self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
            if ok:
                parent = find_note(pid) if pid else None
                if parent:
                    self.report_status(
                        f"已挂到「{parent.get('title') or pid}」下",
                        level=StatusLevel.INFO,
                    )
                else:
                    self.report_status("已更新大纲层级", level=StatusLevel.INFO)
            else:
                self.report_status("无法移动到该位置，已恢复列表", level=StatusLevel.WARNING)

        # 等 Qt 拖放收尾后再重载，避免刚建好的行被框架删掉
        QTimer.singleShot(0, apply)

    def _on_indent(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        nid = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if not nid:
            return
        if indent_node(nid):
            self._reload_tree(keep_selection=nid)
            self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.report_status("已降级（成为上一条的子项）", level=StatusLevel.INFO)
        else:
            self.report_status("无法降级：需有上一条同级记事", level=StatusLevel.WARNING)

    def _on_outdent(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        nid = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if not nid:
            return
        if outdent_node(nid):
            self._reload_tree(keep_selection=nid)
            self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.report_status("已升级（提到与父级同级）", level=StatusLevel.INFO)
        else:
            self.report_status("已在顶层，无法再升级", level=StatusLevel.WARNING)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item is None:
            return
        self._tree.setCurrentItem(item)
        self._on_edit_title()

    def _on_tree_select(self, current: QTreeWidgetItem | None, _previous) -> None:
        if self._rebuilding_tree or current is None:
            return
        self._flush_autosave()
        nid = str(current.data(0, Qt.ItemDataRole.UserRole) or "")
        n = find_note(nid)
        if n:
            self._current_id = nid
            self._title_label.setText(str(n.get("title") or ""))
            self._load_note_body(str(n.get("body") or ""))
            self._set_save_badge("saved")
            self._update_word_count()
            self._sync_view_chrome()

    def _consume_stash(self) -> None:
        stash = QuickNotepadPage._incoming
        if not stash:
            return
        QuickNotepadPage._incoming = None
        title, body, image_path = stash
        entry = add_note(title or "来自投喂", body or "", parent_id=self._sibling_parent_id())
        self._current_id = entry["id"]
        self._search.clear()
        self._reload_tree(keep_selection=self._current_id)
        self._on_tree_select(self._tree.currentItem(), None)
        if image_path and Path(image_path).is_file():
            if str(self._mode.currentData() or "") != "rich":
                idx = self._mode.findData("rich")
                if idx >= 0:
                    self._mode.setCurrentIndex(idx)
            if insert_image(self._rich, Path(image_path)):
                self._flush_autosave()
        self.report_status("已写入记事", level=StatusLevel.SUCCESS)

    def _ensure_current_note(self) -> bool:
        if self._current_id:
            return True
        entry = add_note("新记事", "", parent_id=self._sibling_parent_id())
        self._current_id = entry["id"]
        self._title_label.setText(entry["title"])
        self._reload_tree(keep_selection=self._current_id)
        return True

    def _insert_text_at_cursor(self, text: str) -> None:
        text = text or ""
        if not text:
            return
        if str(self._mode.currentData() or "") == "rich":
            if self._view_mode == "design" or self._using_wysiwyg:
                cur = self._rich.textCursor()
                prefix = "\n" if self._rich.toPlainText() and not text.startswith("\n") else ""
                cur.insertText(prefix + text)
                self._rich.setTextCursor(cur)
            else:
                cur = self._md_source.textCursor()
                prefix = "\n" if self._md_source.toPlainText() and not text.startswith("\n") else ""
                cur.insertText(prefix + text)
                self._md_source.setTextCursor(cur)
        else:
            cur = self._plain.toPlainText()
            self._plain.setPlainText((cur + ("\n" if cur else "") + text).strip())

    def _from_clipboard(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is None:
            show_warning(self, "无法访问系统剪贴板。")
            return
        mime = cb.mimeData()
        has_image = bool(mime and mime.hasImage())
        text = ((cb.text() if cb else "") or "").strip()
        if not text and not has_image:
            show_warning(self, "系统剪贴板没有文本或图片。")
            return
        self._ensure_current_note()
        if has_image and str(self._mode.currentData() or "") == "rich":
            from PySide6.QtGui import QImage

            self._using_wysiwyg = True
            if self._view_mode != "design":
                self._set_view_mode("design")
            img = QImage(cb.image())
            if not img.isNull() and insert_qimage(self._rich, img):
                if text:
                    self._insert_text_at_cursor(text)
                self._flush_autosave()
                self.report_status("已粘贴图片到当前正文", level=StatusLevel.SUCCESS)
                self.schedule_primary_focus()
                return
            if not text:
                show_warning(self, "剪贴板图片无法插入。")
                return
        if text:
            self._insert_text_at_cursor(text)
            self._flush_autosave()
            self.report_status("已粘贴到当前正文", level=StatusLevel.SUCCESS)
            self.schedule_primary_focus()

    def _from_clipboard_history(self) -> None:
        from modules.clipboard_history.history_store import image_abs_path, load_history

        items = load_history()
        if not items:
            show_warning(self, "剪贴板历史为空。")
            return
        item = items[0]
        kind = str(item.get("kind") or "text")
        self._ensure_current_note()
        if kind == "image":
            path = image_abs_path(item)
            if path is None:
                show_warning(self, "该历史项没有图片。")
                return
            if str(self._mode.currentData() or "") != "rich":
                idx = self._mode.findData("rich")
                if idx >= 0:
                    self._mode.setCurrentIndex(idx)
            self._set_view_mode("design")
            self._using_wysiwyg = True
            if not insert_image(self._rich, path):
                show_warning(self, "无法插入历史图片。")
                return
            self._flush_autosave()
            self.report_status("已从剪贴板历史插入图片", level=StatusLevel.SUCCESS)
        else:
            text = str(item.get("text") or "").strip()
            if not text:
                show_warning(self, "该历史项没有文本。")
                return
            self._insert_text_at_cursor(text)
            self._flush_autosave()
            self.report_status("已从剪贴板历史写入正文", level=StatusLevel.SUCCESS)
        self.schedule_primary_focus()

    def _to_clipboard(self) -> None:
        text = (self._active_plain_text() or "").strip()
        if not text:
            show_warning(self, "正文为空。")
            return
        get_clipboard_watcher().suppress_once()
        cb = QGuiApplication.clipboard()
        if str(self._mode.currentData() or "") == "rich" and self._using_wysiwyg:
            from PySide6.QtCore import QMimeData

            mime = QMimeData()
            mime.setText(text)
            mime.setHtml(self._rich.toHtml())
            cb.setMimeData(mime)
        else:
            cb.setText(text)
        push_text(text, source="manual")
        self.report_status("正文已复制并写入剪贴板历史", level=StatusLevel.SUCCESS)

    @staticmethod
    def _title_from_md(path: Path, body: str) -> str:
        for line in body.splitlines():
            m = re.match(r"^#\s+(.+?)\s*$", line.strip())
            if m:
                return m.group(1).strip()[:80] or path.stem
        stem = path.stem.strip() or "导入的记事"
        return stem[:80]

    @staticmethod
    def _read_text_file(path: Path) -> str:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _on_import_md(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入 Markdown",
            "",
            "Markdown (*.md *.markdown *.mdown *.mkd);;文本 (*.txt);;所有文件 (*.*)",
        )
        if not paths:
            return
        # 导入后便于编辑/预览：切到多功能 Markdown
        if str(self._mode.currentData() or "") != "rich":
            idx = self._mode.findData("rich")
            if idx >= 0:
                self._mode.setCurrentIndex(idx)

        last_id = ""
        ok = 0
        for p in paths:
            path = Path(p)
            if not path.is_file():
                continue
            try:
                body = self._read_text_file(path)
            except OSError as exc:
                show_warning(self, f"无法读取：\n{path.name}\n{exc}")
                continue
            title = self._title_from_md(path, body)
            entry = add_note(title, "", parent_id=self._sibling_parent_id())
            update_note(entry["id"], title, body)
            last_id = entry["id"]
            ok += 1

        if ok == 0:
            show_warning(self, "没有成功导入的文件。")
            return
        self._current_id = last_id
        self._reload_tree(keep_selection=last_id)
        n = find_note(last_id)
        if n:
            self._title_label.setText(str(n.get("title") or ""))
            self._load_note_body(str(n.get("body") or ""))
            self._sync_view_chrome()
        self.schedule_primary_focus()
        self.report_status(
            f"已导入 {ok} 个 Markdown 文件",
            level=StatusLevel.SUCCESS,
        )

    def _seed_new_editor(self) -> None:
        """新建后填充编辑器；Markdown 模式带出全景示例并落盘。"""
        self._loading_body = True
        try:
            if str(self._mode.currentData() or "") == "rich":
                self._using_wysiwyg = False
                md = markdown_demo_template()
                self._md_source.setPlainText(md)
                self._rich.clear()
                self._apply_view_mode("edit")
                if self._current_id:
                    title = self._title_label.text().strip() or "新记事"
                    update_note(self._current_id, title, md)
            else:
                self._rich.clear()
                self._md_source.clear()
                self._plain.clear()
        finally:
            self._loading_body = False
        self._sync_view_chrome()
        self._set_save_badge("saved")
        self._update_word_count()

    def _on_new_note(self) -> None:
        self._flush_autosave()
        entry = add_note("新记事", "", parent_id=self._sibling_parent_id())
        self._current_id = entry["id"]
        self._reload_tree(keep_selection=self._current_id)
        self._title_label.setText(entry["title"])
        self._seed_new_editor()
        self.schedule_primary_focus()
        rich = str(self._mode.currentData() or "") == "rich"
        self.report_status(
            "已新建 · 已带出 Markdown 示例" if rich else "已新建记事 · 直接输入",
            level=StatusLevel.SUCCESS,
        )

    def _on_new_below(self) -> None:
        """Enter：在当前条下方新建同级（Outline）。"""
        self._flush_autosave()
        after = self._current_id
        entry = insert_note_after(after, title="新记事", body="")
        self._current_id = entry["id"]
        self._reload_tree(keep_selection=self._current_id)
        self._title_label.setText(entry["title"])
        self._seed_new_editor()
        self._tree.setFocus(Qt.FocusReason.ShortcutFocusReason)
        rich = str(self._mode.currentData() or "") == "rich"
        self.report_status(
            "已在下方新建 · 已带出 Markdown 示例" if rich else "已在下方新建",
            level=StatusLevel.SUCCESS,
        )

    def _on_edit_title(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            show_warning(self, "请先选择记事。")
            return
        nid = str(item.data(0, Qt.ItemDataRole.UserRole))
        node = find_note(nid)
        if not node:
            return
        dlg = FormEditDialog(self, title="修改标题", fields=[("标题", "title")])
        dlg.set_values({"title": node.get("title") or ""})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title = (dlg.values().get("title") or "").strip() or "无标题"
        update_note(nid, title, str(node.get("body") or ""))
        self._title_label.setText(title)
        self._reload_tree(keep_selection=nid)
        self.schedule_primary_focus()

    def _update_tree_item_label(self, node_id: str) -> None:
        node = find_note(node_id)
        if node is None:
            return

        def walk(item: QTreeWidgetItem | None) -> QTreeWidgetItem | None:
            if item is None:
                for i in range(self._tree.topLevelItemCount()):
                    found = walk(self._tree.topLevelItem(i))
                    if found is not None:
                        return found
                return None
            if str(item.data(0, Qt.ItemDataRole.UserRole)) == str(node_id):
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        item = walk(None)
        if item is not None:
            title = str(node.get("title") or "无标题")
            item.setText(0, title)
            item.setToolTip(0, f"{node.get('updated', '')} · {title}")

    def _on_save_body(self, silent: bool = False) -> None:
        rich = str(self._mode.currentData() or "") == "rich"
        if rich:
            if self._view_mode == "design":
                self._using_wysiwyg = self._using_wysiwyg or rich_has_images(self._rich)
                if self._using_wysiwyg:
                    cursor_pos = self._rich.textCursor().position()
                    body = export_body_from(self._rich)
                    plain_len = len(self._rich.toPlainText())
                else:
                    self._sync_source_from_design()
                    cursor_pos = self._md_source.textCursor().position()
                    body = self._md_source.toPlainText()
                    plain_len = len(body)
            elif self._using_wysiwyg or rich_has_images(self._rich):
                cursor_pos = self._rich.textCursor().position()
                body = export_body_from(self._rich)
                plain_len = len(self._rich.toPlainText())
            else:
                cursor_pos = self._md_source.textCursor().position()
                body = self._md_source.toPlainText()
                plain_len = len(body)
        else:
            cursor_pos = self._plain.textCursor().position()
            body = self._plain.toPlainText()
            plain_len = len(body)
        if not self._current_id:
            if silent and not (body or "").strip():
                return
            title = self._title_label.text().strip()
            if not title or title == "未选择":
                title = "新记事"
            entry = add_note(title, body, parent_id=self._sibling_parent_id())
            self._current_id = entry["id"]
            self._title_label.setText(entry["title"])
            self._reload_tree(keep_selection=self._current_id)
        else:
            n = find_note(self._current_id)
            if not n:
                if not silent:
                    show_warning(self, "当前记事不存在，请重新选择。")
                return
            title = str(n.get("title") or self._title_label.text() or "无标题")
            update_note(self._current_id, title, body)
            self._title_label.setText(title)
            self._update_tree_item_label(self._current_id)
        if not silent:
            if rich and (self._view_mode == "design" or self._using_wysiwyg):
                cur = self._rich.textCursor()
                cur.setPosition(min(cursor_pos, plain_len))
                self._rich.setTextCursor(cur)
            elif rich:
                cur = self._md_source.textCursor()
                cur.setPosition(min(cursor_pos, plain_len))
                self._md_source.setTextCursor(cur)
            else:
                cur = self._plain.textCursor()
                cur.setPosition(min(cursor_pos, plain_len))
                self._plain.setTextCursor(cur)
            self.schedule_primary_focus(move_cursor_end=False)
            self.report_status("已保存 · 可继续编辑", level=StatusLevel.SUCCESS)
        self._set_save_badge("saved")

    def _on_delete(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        self._flush_autosave()
        nid = str(item.data(0, Qt.ItemDataRole.UserRole))
        n = find_note(nid) or {}
        kids = children_of(nid)
        label = f"「{n.get('title') or nid}」"
        if kids:
            label += f"（{len(kids)} 个子项会提升到上一级）"
        if not confirm_delete(self, label):
            return
        delete_node(nid)
        if self._current_id == nid:
            self._current_id = None
            self._loading_body = True
            try:
                self._rich.clear()
                self._plain.clear()
            finally:
                self._loading_body = False
            self._title_label.setText("未选择")
            self._set_save_badge("empty")
        self._reload_tree()

    def on_enter(self) -> None:
        self._set_shortcuts_active(True)
        sanitize_tree()
        self._consume_stash()
        self._reload_tree(keep_selection=self._current_id)
        if self._current_id:
            self._select_tree_id(self._current_id)
        self.report_status("快速记事 · 自动保存已开")

    def on_leave(self) -> None:
        self._flush_autosave()
        self._set_shortcuts_active(False)

    def on_theme_changed(self, _theme_id: str, palette: dict) -> None:
        self._reload_tree(keep_selection=self._current_id)
        self._refresh_fg_btn_icon()
        self._refresh_hl_btn_icon()
        if hasattr(self, "_md_highlighter"):
            self._md_highlighter.set_palette(palette or {})
