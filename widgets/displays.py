# -*- coding: utf-8 -*-
"""列表、表格、页签、进度、日历等展示控件。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QBrush, QColor, QFont, QPalette, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QHeaderView,
    QListWidget,
    QProgressBar,
    QSizePolicy,
    QTableView,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QWidget,
)


def _fg_on_bg(bg: QColor, *, light: str = "#FFFFFF", dark: str = "#1A1A1A") -> QColor:
    return QColor(dark if bg.lightness() > 150 else light)


class ListWidget(QListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)


class TreeWidget(QTreeWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setExpandsOnDoubleClick(True)
        self.setMinimumHeight(120)


class ProgressBar(QProgressBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(12)


class TabWidget(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 点击页签不留虚线焦点框（Windows 默认 PE_FrameFocusRect）
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        bar = self.tabBar()
        bar.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        bar.setExpanding(False)


class DataTable(QTableWidget):
    def __init__(self, rows: int = 0, columns: int = 0, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self._auto_column_layout = True
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hdr.setMinimumSectionSize(48)

    def set_auto_column_layout(self, enabled: bool) -> None:
        """关闭后由调用方自行 setSectionResizeMode（如 Finder 明细表）。"""
        self._auto_column_layout = bool(enabled)

    def set_headers(self, headers: list[str]) -> None:
        try:
            self.setColumnCount(len(headers))
            self.setHorizontalHeaderLabels(headers)
            self._apply_column_layout()
        except RuntimeError:
            # C++ 对象已删（常见于刚拆 WebEngine 后进业务页）
            return

    def set_rows(self, rows: list[tuple[str, ...]]) -> None:
        try:
            self.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    self.setItem(r, c, QTableWidgetItem(str(val)))
            self._apply_column_layout()
        except RuntimeError:
            return

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._auto_column_layout:
            self._apply_column_layout()

    def _column_weights(self) -> list[float]:
        """按表头语义分配相对权重，避免名称独占、时间贴边。"""
        weights: list[float] = []
        for c in range(self.columnCount()):
            item = self.horizontalHeaderItem(c)
            t = item.text() if item is not None else ""
            if any(k in t for k in ("序号", "编号", "#")):
                weights.append(0.55)
            elif t == "名称" and self.columnCount() >= 7:
                weights.append(1.65)
            elif any(k in t for k in ("开始", "结束", "时间", "日期", "修改", "创建")):
                weights.append(1.35)
            elif any(k in t for k in ("名称", "标题", "班级", "文件", "路径", "内容", "说明")):
                weights.append(2.6)
            elif any(k in t for k in ("类型", "大小", "状态", "引擎", "判定", "来源", "供应商", "角色")):
                weights.append(0.75)
            elif any(k in t for k in ("手机", "有效期", "功能数")):
                weights.append(0.9)
            elif "功能权限" in t or "显示名" in t:
                weights.append(1.85)
            elif "URL" in t:
                weights.append(1.45)
            elif "模型" in t:
                weights.append(1.05)
            elif t in ("Key", "默认"):
                weights.append(0.55)
            else:
                weights.append(1.15)
        return weights

    def _apply_column_layout(self) -> None:
        if not self._auto_column_layout:
            return
        try:
            from shiboken6 import isValid

            if not isValid(self):
                return
        except Exception:
            pass
        try:
            cols = self.columnCount()
            if cols <= 0:
                return
            hdr = self.horizontalHeader()
            if hdr is None:
                return
            try:
                from shiboken6 import isValid

                if not isValid(hdr):
                    return
            except Exception:
                pass
            hdr.setStretchLastSection(False)
            # 批量改 mode 比逐列 Interactive 更稳；WebEngine 刚拆时逐列 setSectionResizeMode 易 AV
            hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            avail = max(int(self.viewport().width()), 240)
            weights = self._column_weights()
            if len(weights) != cols:
                weights = [1.0] * cols
            total = sum(weights) or 1.0
            used = 0
            for c in range(cols - 1):
                w = max(48, int(avail * weights[c] / total))
                self.setColumnWidth(c, w)
                used += w
            self.setColumnWidth(cols - 1, max(48, avail - used))
        except RuntimeError:
            return
        except Exception:
            return


class CalendarWidget(QCalendarWidget):
    """主题化月历（全局 QSS + 调色板，避免系统白底浅字）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ThemedCalendar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self._sel_fmt_date = None
        self.selectionChanged.connect(self.highlight_selected)
        self.apply_theme_colors()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.apply_theme_colors()
        self.highlight_selected()
        self._style_navigation()

    def highlight_selected(self) -> None:
        """当前选中日反显（Windows 上 QSS selection 常不生效）。"""
        try:
            from app.app_state import AppState

            p = AppState.get().palette or {}
        except Exception:
            p = {}
        primary = QColor(str(p.get("primary") or "#C17F4E"))
        on_primary = _fg_on_bg(primary)

        text = QColor(str(p.get("text_primary") or "#F0E6DC"))

        # 清掉上一选中日的专用格式，避免残留反显
        if self._sel_fmt_date is not None and self._sel_fmt_date != self.selectedDate():
            cleared = QTextCharFormat()
            cleared.setForeground(QBrush(text))
            self.setDateTextFormat(self._sel_fmt_date, cleared)

        sel = self.selectedDate()
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(primary))
        fmt.setForeground(QBrush(on_primary))
        fmt.setFontWeight(QFont.Weight.Bold)
        self.setDateTextFormat(sel, fmt)
        self._sel_fmt_date = sel

    def apply_theme_colors(self) -> None:
        """用当前主题调色板刷导航与日期格（QSS alone 在 Windows 上常被系统色盖住）。"""
        try:
            from app.app_state import AppState

            p = AppState.get().palette or {}
        except Exception:
            p = {}
        surface = QColor(str(p.get("surface") or "#33261E"))
        surface_raised = QColor(str(p.get("surface_raised") or p.get("panel") or "#3D2E24"))
        text = QColor(str(p.get("text_primary") or "#F0E6DC"))
        text_muted = QColor(str(p.get("text_secondary") or "#B8A99A"))
        primary = QColor(str(p.get("primary") or "#C17F4E"))
        on_primary = _fg_on_bg(primary)
        weekend = QColor(str(p.get("danger") or "#E57373"))
        if weekend.lightness() < 120 and surface.lightness() < 128:
            weekend = QColor("#EF9A9A")
        elif weekend.lightness() > 180 and surface.lightness() > 200:
            weekend = QColor("#C62828")

        pal = self.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.Window, surface)
            pal.setColor(group, QPalette.ColorRole.WindowText, text)
            pal.setColor(group, QPalette.ColorRole.Base, surface)
            pal.setColor(group, QPalette.ColorRole.AlternateBase, surface_raised)
            pal.setColor(group, QPalette.ColorRole.Text, text)
            pal.setColor(group, QPalette.ColorRole.Button, surface)
            pal.setColor(group, QPalette.ColorRole.ButtonText, text)
            pal.setColor(group, QPalette.ColorRole.Highlight, primary)
            pal.setColor(group, QPalette.ColorRole.HighlightedText, on_primary)
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_muted)
        self.setPalette(pal)

        view = self.findChild(QTableView, "qt_calendar_calendarview")
        if view is not None:
            view.setPalette(pal)
            view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            view.setFrameShape(QFrame.Shape.StyledPanel)
            view.setLineWidth(1)
            view.setShowGrid(True)

        weekday = QTextCharFormat()
        weekday.setForeground(QBrush(text))
        weekend_fmt = QTextCharFormat()
        weekend_fmt.setForeground(QBrush(weekend))
        for day in (
            Qt.DayOfWeek.Monday,
            Qt.DayOfWeek.Tuesday,
            Qt.DayOfWeek.Wednesday,
            Qt.DayOfWeek.Thursday,
            Qt.DayOfWeek.Friday,
        ):
            self.setWeekdayTextFormat(day, weekday)
        self.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, weekend_fmt)
        self.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, weekend_fmt)
        self.highlight_selected()
        self._style_navigation()

    def _style_navigation(self) -> None:
        """替换 Qt 默认绿圆箭头为与导航栏同色的 flat chevron。"""
        try:
            from app.app_state import AppState
            from services.icon_registry import chevron_icon

            p = AppState.get().palette or {}
        except Exception:
            return
        nav_fg = str(p.get("header_fg") or p.get("on_primary") or "#FFFFFF")
        icon_size = 14
        for obj_name, direction in (
            ("qt_calendar_prevmonth", "left"),
            ("qt_calendar_nextmonth", "right"),
        ):
            btn = self.findChild(QToolButton, obj_name)
            if btn is None:
                continue
            btn.setText("")
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setIcon(chevron_icon(direction, color=nav_fg, size=icon_size, parent=self))
            btn.setIconSize(QSize(icon_size, icon_size))
