# -*- coding: utf-8 -*-
"""大纲树：拖放意图、文件投放、Tab/Enter 快捷键。"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QTreeWidgetItem

from widgets import TreeWidget


class OutlineTree(TreeWidget):
    """Outline：拖放只发意图，由存储落盘后重载；Tab / Enter 交给页面。"""

    drop_resolved = Signal(str, object, int)  # nid, parent_id|None, order
    files_dropped = Signal(object)  # list[str] 本地路径
    indent_requested = Signal()
    outdent_requested = Signal()
    create_below_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("OutlineTree")
        self.setAlternatingRowColors(False)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)
        self.setIndentation(22)
        self.setItemsExpandable(True)
        self.setExpandsOnDoubleClick(False)
        self.setAnimated(False)
        self.setAllColumnsShowFocus(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        if event.mimeData().hasUrls() and any(
            u.isLocalFile() for u in event.mimeData().urls()
        ):
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat("application/x-toa-outline-note") or event.source() is self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(
            u.isLocalFile() for u in event.mimeData().urls()
        ):
            event.acceptProposedAction()
            self._drop_item = None
            self._drop_where = QAbstractItemView.DropIndicatorPosition.OnViewport
            self.viewport().update()
            return
        if not (
            event.mimeData().hasFormat("application/x-toa-outline-note")
            or event.source() is self
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
            y = (
                rect.top()
                if where == QAbstractItemView.DropIndicatorPosition.AboveItem
                else rect.bottom()
            )
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
        if event.mimeData().hasUrls():
            paths = [
                u.toLocalFile()
                for u in event.mimeData().urls()
                if u.isLocalFile() and u.toLocalFile()
            ]
            if paths:
                event.acceptProposedAction()
                self._drop_item = None
                self._dragging = False
                self.viewport().update()
                self.files_dropped.emit(paths)
                return
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
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()

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


class OutlineKeyFilter(QObject):
    """树有焦点时兜底 Tab / Shift+Tab（部分平台不进 keyPressEvent）。"""

    def __init__(self, tree: OutlineTree, parent=None) -> None:
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
