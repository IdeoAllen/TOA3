# -*- coding: utf-8 -*-
"""列表、表格、页签、进度、日历等展示控件。"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QSize, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPalette, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QGraphicsOpacityEffect,
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
    """确定进度；填充段带缓动斑马微纹（主题色派生，非硬编码）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(14)
        self.setTextVisible(True)
        self._zebra_offset = 0.0
        self._zebra_timer = QTimer(self)
        self._zebra_timer.setInterval(33)
        self._zebra_timer.timeout.connect(self._tick_zebra)
        self.valueChanged.connect(self._sync_zebra_timer)
        self._sync_zebra_timer()

    def _sync_zebra_timer(self, *_args) -> None:
        lo, hi, cur = self.minimum(), self.maximum(), self.value()
        busy = hi > lo and lo < cur < hi
        if busy and not self._zebra_timer.isActive():
            self._zebra_timer.start()
        elif not busy and self._zebra_timer.isActive():
            self._zebra_timer.stop()
            self.update()

    def _tick_zebra(self) -> None:
        self._zebra_offset = (self._zebra_offset + 1.1) % 16.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter, QPainterPath, QColor
        from PySide6.QtWidgets import QStyle, QStyleOptionProgressBar, QStylePainter

        opt = QStyleOptionProgressBar()
        self.initStyleOption(opt)
        sp = QStylePainter(self)
        sp.drawControl(QStyle.ControlElement.CE_ProgressBarGroove, opt)

        lo, hi, cur = self.minimum(), self.maximum(), self.value()
        if hi > lo and cur > lo:
            groove = self.style().subElementRect(
                QStyle.SubElement.SE_ProgressBarGroove, opt, self
            )
            if not groove.isValid():
                groove = self.style().subElementRect(
                    QStyle.SubElement.SE_ProgressBarContents, opt, self
                )
            frac = max(0.0, min(1.0, (cur - lo) / float(hi - lo)))
            fill_w = max(0, int(groove.width() * frac))
            if fill_w > 0:
                fill = groove.adjusted(1, 1, fill_w - groove.width() - 1, -1)
                accent = self.palette().color(QPalette.ColorRole.Highlight)
                if not accent.isValid():
                    accent = self.palette().color(QPalette.ColorRole.WindowText)

                path = QPainterPath()
                path.addRoundedRect(fill, 3.0, 3.0)
                sp.setClipPath(path)
                sp.fillRect(fill, accent)

                # 斑马微纹叠在填充上（低透明），文字稍后由 Label 绘出
                stripe = QColor(accent)
                if accent.lightness() > 140:
                    stripe = accent.lighter(135)
                else:
                    stripe = accent.lighter(165)
                stripe.setAlpha(55)

                period = 16.0
                half = period * 0.5
                skew = float(max(1, fill.height()))
                x = float(fill.x()) - period - (self._zebra_offset % period)
                right = float(fill.right()) + period
                band = 0
                while x < right:
                    if band % 2 == 0:
                        poly = QPainterPath()
                        poly.moveTo(x, fill.top())
                        poly.lineTo(x + half, fill.top())
                        poly.lineTo(x + half + skew, fill.bottom())
                        poly.lineTo(x + skew, fill.bottom())
                        poly.closeSubpath()
                        sp.fillPath(poly, stripe)
                    x += half
                    band += 1
                sp.setClipping(False)

        sp.drawControl(QStyle.ControlElement.CE_ProgressBarLabel, opt)


class SoftActivityBar(QWidget):
    """斑马纹滑动活动条：布局高度常驻，忙碌淡入匀速滑动，空闲淡出后停。

    不用系统 indeterminate / 实心 chunk（Windows 上易咔咔、装完还往前跑）。
    斜向斑马带连续平移，避免旧版虚线「走走停停」感。
    """

    _HEIGHT = 4
    _PERIOD = 18.0  # 一对斑马带周期（px）
    _SPEED = 1.35  # 每帧位移（16ms ≈ 84px/s）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SoftActivityBar")
        self.setFixedHeight(self._HEIGHT)
        self.setMaximumHeight(self._HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)

        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)

        self._want = False
        self._visible_soft = False
        self._offset = 0.0

        self._marquee = QTimer(self)
        self._marquee.setInterval(16)
        self._marquee.timeout.connect(self._tick_marquee)

        self._defer_show = QTimer(self)
        self._defer_show.setSingleShot(True)
        self._defer_show.setInterval(80)
        self._defer_show.timeout.connect(self._really_show)

    def set_active(self, active: bool, *, immediate: bool = False) -> None:
        active = bool(active)
        self._want = active
        if active:
            if immediate:
                self._defer_show.stop()
                self._really_show()
            elif not self._visible_soft and not self._defer_show.isActive():
                self._defer_show.start()
        else:
            self._defer_show.stop()
            self._begin_hide()

    def _really_show(self) -> None:
        if not self._want:
            return
        was = self._visible_soft
        self._visible_soft = True
        self._fade.stop()
        self._fade.setStartValue(max(0.0, float(self._fx.opacity())))
        self._fade.setEndValue(1.0)
        self._fade.start()
        if not self._marquee.isActive():
            self._marquee.start()
        # 已在滚动时不要重置相位，避免反复启停「跳一下」
        if not was:
            self.update()

    def _begin_hide(self) -> None:
        """先淡出，动画仍跑；淡出结束后再硬停计时器。"""
        self._want = False
        self._visible_soft = False
        self._defer_show.stop()
        self._fade.stop()
        cur = float(self._fx.opacity())
        if cur <= 0.02:
            self._fx.setOpacity(0.0)
            self._marquee.stop()
            self.update()
            return
        # 淡出期间保持斑马滑动，避免「突然定格再消失」
        if not self._marquee.isActive():
            self._marquee.start()
        self._fade.setStartValue(cur)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._want:
            return
        if float(self._fx.opacity()) <= 0.02:
            self._marquee.stop()
            self._fx.setOpacity(0.0)
            self.update()

    def _hard_stop(self) -> None:
        """兼容旧调用：立即停。"""
        self._begin_hide()

    def _tick_marquee(self) -> None:
        # 淡出过程中仍滑动；仅完全隐藏且不要显示时停
        if not self._want and float(self._fx.opacity()) <= 0.02:
            self._marquee.stop()
            return
        self._offset = (self._offset + self._SPEED) % self._PERIOD
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        op = float(self._fx.opacity())
        if op < 0.02:
            return
        from PySide6.QtGui import QPainter, QPainterPath, QColor

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        if not accent.isValid() or accent.lightness() > 240:
            accent = self.palette().color(QPalette.ColorRole.WindowText)
        track = self.palette().color(QPalette.ColorRole.Mid)
        if not track.isValid() or track.lightness() > 250:
            track = self.palette().color(QPalette.ColorRole.Window)

        r = self.rect()
        # 圆角轨道
        path = QPainterPath()
        path.addRoundedRect(r.adjusted(0, 0, 0, 0), 2.0, 2.0)
        p.setClipPath(path)

        base = QColor(track)
        base.setAlpha(int(90 * op))
        p.fillRect(r, base)

        # 斜向斑马：亮带 / 暗带交替平移
        hi = QColor(accent)
        hi.setAlpha(int(210 * op))
        lo = QColor(accent)
        # 略提亮或压暗形成斑马对比（走 palette 派生，不写死 hex）
        if accent.lightness() > 140:
            lo = accent.darker(125)
        else:
            lo = accent.lighter(140)
        lo.setAlpha(int(95 * op))

        period = self._PERIOD
        half = period * 0.5
        # 斜带宽度沿 x；倾斜约 28°
        skew = self.height() * 1.8
        w = float(r.width())
        h = float(r.height())
        x0 = -period - (self._offset % period)
        band = 0
        x = x0
        while x < w + period + skew:
            color = hi if (band % 2 == 0) else lo
            poly = QPainterPath()
            # 平行四边形：左上 → 右上 → 右下 → 左下（带倾斜）
            poly.moveTo(x, 0)
            poly.lineTo(x + half, 0)
            poly.lineTo(x + half + skew, h)
            poly.lineTo(x + skew, h)
            poly.closeSubpath()
            p.fillPath(poly, color)
            x += half
            band += 1
        p.end()


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
