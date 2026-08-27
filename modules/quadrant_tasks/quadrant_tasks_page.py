# -*- coding: utf-8 -*-
"""四象限任务看板（Eisenhower · 指尖时光风格）。"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QMimeData, Signal, QSize
from PySide6.QtGui import QDrag, QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base_dialog import BaseDialog
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_warning
from modules.quadrant_tasks.schedule_month_view import ScheduleMonthView
from modules.quadrant_tasks.task_store import (
    QUADRANT_IDS,
    QUADRANT_KINDS,
    QUADRANT_LABELS,
    Q1,
    add_task,
    count_overdue,
    delete_task,
    find_task,
    load_tasks,
    matches_filter,
    move_task,
    overdue_days,
    parse_due,
    task_covers_day,
    tasks_in_quadrant,
    update_task,
)
from widgets import (
    CheckBox,
    ComboBox,
    DateEdit,
    FormSection,
    HintLabel,
    ListWidget,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)
from widgets.dialog_actions import DialogButtonRow
from widgets.inputs import LineEdit
from widgets.list_edit import confirm_delete
from widgets.metrics import CONTROL_GAP, TREE_ROW_HEIGHT

_MIME = "application/x-toa3-quadrant-task"
_WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")


def _today_label(day: date | None = None) -> str:
    d = day or date.today()
    return f"{d.year}年{d.month:02d}月{d.day:02d}日 星期{_WEEKDAYS[d.weekday()]}"


def _refresh_button_class(btn: SecondaryButton, *, primary: bool) -> None:
    btn.setProperty("class", "primary" if primary else "")
    sty = btn.style()
    sty.unpolish(btn)
    sty.polish(btn)
    btn.update()


class _TaskRow(QWidget):
    """任务行：勾选 · 标题 · 截止/逾期。支持按住拖到其他象限。"""

    done_toggled = Signal(str, bool)

    def __init__(self, task: dict, parent=None) -> None:
        super().__init__(parent)
        self.task_id = str(task.get("id") or "")
        self._drag_start = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(CONTROL_GAP)

        self._cb = CheckBox()
        self._cb.setChecked(bool(task.get("done")))
        self._cb.setFixedWidth(28)
        self._cb.setCursor(Qt.CursorShape.ArrowCursor)
        self._cb.toggled.connect(self._emit_done)
        lay.addWidget(self._cb, 0, Qt.AlignmentFlag.AlignVCenter)

        title = str(task.get("title") or "")
        self._title = QLabel(title)
        self._title.setWordWrap(False)
        self._title.setToolTip(title)
        self._title.setMinimumWidth(40)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._title, 1)

        days = overdue_days(task)
        if days is not None:
            meta: HintLabel | SemanticLabel = SemanticLabel(
                f"逾期 {days} 天", kind="danger", compact=True
            )
            meta.setWordWrap(False)
        else:
            start = str(task.get("start") or "").strip()
            due = str(task.get("due") or "").strip()
            if start and due and start != due:
                meta = HintLabel(f"{start[5:]}→{due[5:]}" if len(start) >= 10 else f"{start}→{due}")
            else:
                meta = HintLabel(due or start)
            meta.setWordWrap(False)
        meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(meta)

    def _list(self) -> _QuadrantList | None:
        w = self.parent()
        while w is not None:
            if isinstance(w, _QuadrantList):
                return w
            w = w.parent()
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._cb.geometry().contains(event.position().toPoint()):
                self._drag_start = None
                super().mousePressEvent(event)
                return
            self._drag_start = event.position().toPoint()
            lst = self._list()
            if lst is not None:
                for i in range(lst.count()):
                    if lst.itemWidget(lst.item(i)) is self:
                        lst.setCurrentRow(i)
                        break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            self._drag_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = (event.position().toPoint() - self._drag_start).manhattanLength()
            from PySide6.QtWidgets import QApplication

            if delta >= QApplication.startDragDistance():
                lst = self._list()
                self._drag_start = None
                if lst is not None:
                    lst.startDrag(Qt.DropAction.MoveAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def _emit_done(self, checked: bool) -> None:
        self.done_toggled.emit(self.task_id, checked)


class _QuadrantList(ListWidget):
    """支持跨象限拖放的任务列表（页内轻量扩展）。"""

    task_dropped = Signal(str)
    edit_requested = Signal(str)
    move_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, quadrant_id: str, parent=None) -> None:
        super().__init__(parent)
        self.quadrant_id = quadrant_id
        self.setMinimumHeight(180)
        self.setAlternatingRowColors(False)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_menu)
        self.itemDoubleClicked.connect(self._on_double)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def startDrag(self, supportedActions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if not task_id:
            return
        mime = QMimeData()
        mime.setData(_MIME, str(task_id).encode("utf-8"))
        mime.setText(str(task_id))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if not event.mimeData().hasFormat(_MIME):
            event.ignore()
            return
        task_id = bytes(event.mimeData().data(_MIME)).decode("utf-8")
        self.task_dropped.emit(task_id)
        event.acceptProposedAction()

    def _current_task_id(self) -> str | None:
        item = self.currentItem()
        if item is None:
            return None
        tid = item.data(Qt.ItemDataRole.UserRole)
        return str(tid) if tid else None

    def _on_double(self, _item) -> None:
        tid = self._current_task_id()
        if tid:
            self.edit_requested.emit(tid)

    def _on_menu(self, pos) -> None:
        tid = self._current_task_id()
        if not tid:
            item = self.itemAt(pos)
            if item is None:
                return
            self.setCurrentItem(item)
            tid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not tid:
            return
        menu = QMenu(self)
        act_edit = QAction("编辑", menu)
        act_move = QAction("移到…", menu)
        act_del = QAction("删除", menu)
        menu.addAction(act_edit)
        menu.addAction(act_move)
        menu.addSeparator()
        menu.addAction(act_del)
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is act_edit:
            self.edit_requested.emit(tid)
        elif chosen is act_move:
            self.move_requested.emit(tid)
        elif chosen is act_del:
            self.delete_requested.emit(tid)


class _TaskFormDialog(BaseDialog):
    """新增 / 编辑任务（标题 · 截止 · 象限）。"""

    dialog_kind = "medium"

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        initial: dict | None = None,
        default_quadrant: str = Q1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        init = initial or {}
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        row_title = QHBoxLayout()
        row_title.addWidget(HintLabel("标题"))
        self._title = LineEdit()
        self._title.setText(str(init.get("title") or ""))
        self._title.setPlaceholderText("任务内容")
        row_title.addWidget(self._title, 1)
        lay.addLayout(row_title)

        row_start = QHBoxLayout()
        row_start.addWidget(HintLabel("开始日期"))
        self._start = DateEdit()
        start_raw = str(init.get("start") or "").strip()
        if start_raw:
            self._start.set_iso(start_raw)
        elif str(init.get("due") or "").strip():
            self._start.set_iso(str(init.get("due") or ""))
        row_start.addWidget(self._start, 1)
        lay.addLayout(row_start)

        row_due = QHBoxLayout()
        row_due.addWidget(HintLabel("截止日期"))
        self._due = DateEdit()
        due_raw = str(init.get("due") or "").strip()
        if due_raw:
            self._due.set_iso(due_raw)
        # 新建默认今天；编辑无截止时也落在今天便于改选
        row_due.addWidget(self._due, 1)
        lay.addLayout(row_due)
        lay.addWidget(HintLabel("跨日任务：开始≠截止时，日历上通栏显示任务名。"))

        row_q = QHBoxLayout()
        row_q.addWidget(HintLabel("象限"))
        self._quadrant = ComboBox()
        current_q = str(init.get("quadrant") or default_quadrant)
        for qid in QUADRANT_IDS:
            self._quadrant.addItem(QUADRANT_LABELS[qid], qid)
        idx = self._quadrant.findData(current_q)
        self._quadrant.setCurrentIndex(idx if idx >= 0 else 0)
        row_q.addWidget(self._quadrant, 1)
        lay.addLayout(row_q)

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("确定", self.accept)
        lay.addWidget(buttons)

    def values(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "start": self._start.to_iso(),
            "due": self._due.to_iso(),
            "quadrant": str(self._quadrant.currentData() or Q1),
        }


class _MoveQuadrantDialog(BaseDialog):
    dialog_kind = "small"

    def __init__(self, parent=None, *, current: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("移到象限")
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(HintLabel("选择目标象限"))
        self._combo = ComboBox()
        for qid in QUADRANT_IDS:
            if qid == current:
                continue
            self._combo.addItem(QUADRANT_LABELS[qid], qid)
        lay.addWidget(self._combo)
        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("确定", self.accept)
        lay.addWidget(buttons)

    def selected_quadrant(self) -> str:
        return str(self._combo.currentData() or "")


class QuadrantTasksPage(BasePage):
    page_id = "quadrant_tasks"
    page_title = "四象限任务"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lists: dict[str, _QuadrantList] = {}
        self._filter = "all"
        self._view = "board"  # board | calendar

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll, 1)

        scroll.add_layout(self._build_top_bar())

        self._stack = QStackedWidget()
        board = QWidget()
        grid = QGridLayout(board)
        grid.setSpacing(12)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        positions = ((0, 0), (0, 1), (1, 0), (1, 1))
        for (row, col), qid in zip(positions, QUADRANT_IDS):
            panel = self._build_quadrant(qid)
            grid.addWidget(panel, row, col)
        self._stack.addWidget(board)

        cal_host = QWidget()
        cal_lay = QHBoxLayout(cal_host)
        cal_lay.setContentsMargins(0, 0, 0, 0)
        cal_lay.setSpacing(12)
        self._calendar = ScheduleMonthView()
        self._calendar.daySelected.connect(self._on_calendar_day)
        self._calendar.dayCreateRequested.connect(self._on_add_for_selected_day)
        self._calendar.taskActivated.connect(self._on_edit)
        self._calendar.monthChanged.connect(lambda *_: self._calendar.refresh_tasks())
        cal_lay.addWidget(self._calendar, 3)
        day_box = FormSection("当日任务")
        day_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._day_list = ListWidget()
        self._day_list.setMinimumHeight(280)
        self._day_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._day_list.itemDoubleClicked.connect(self._on_calendar_edit)
        day_box.add_widget(self._day_list, 1)
        day_row = QHBoxLayout()
        btn_cal_add = PrimaryButton("本日新建")
        btn_cal_add.clicked.connect(self._on_add_for_selected_day)
        day_row.addWidget(btn_cal_add)
        btn_cal_edit = SecondaryButton("编辑")
        btn_cal_edit.clicked.connect(self._on_calendar_edit)
        day_row.addWidget(btn_cal_edit)
        day_row.addStretch(1)
        day_box.add_layout(day_row)
        day_box.add_widget(
            HintLabel(
                "单击选日；再点同一日新建任务。点任务条编辑。跨日任务通栏显示标题。"
            )
        )
        cal_lay.addWidget(day_box, 2)
        self._stack.addWidget(cal_host)
        scroll.content_layout.addWidget(self._stack, 1)
        self._apply_filter_chips()
        self._apply_view_chips()
        self._reload_all()

        sc_new = QShortcut(QKeySequence("Ctrl+N"), self)
        sc_new.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_new.activated.connect(self._on_add)

    def _build_top_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(CONTROL_GAP)
        self._date_label = HintLabel(_today_label())
        self._date_label.setWordWrap(False)
        row.addWidget(self._date_label)
        row.addStretch(1)

        self._chip_today = SecondaryButton("今日")
        self._chip_all = SecondaryButton("全部")
        self._chip_today.clicked.connect(lambda: self._set_filter("today"))
        self._chip_all.clicked.connect(lambda: self._set_filter("all"))
        row.addWidget(self._chip_today)
        row.addWidget(self._chip_all)

        self._chip_board = SecondaryButton("看板")
        self._chip_cal = SecondaryButton("日历")
        self._chip_board.clicked.connect(lambda: self._set_view("board"))
        self._chip_cal.clicked.connect(lambda: self._set_view("calendar"))
        row.addWidget(self._chip_board)
        row.addWidget(self._chip_cal)

        btn_add = PrimaryButton("+")
        btn_add.setToolTip("添加任务 (Ctrl+N)")
        btn_add.setFixedWidth(36)
        btn_add.clicked.connect(self._on_add)
        row.addWidget(btn_add)
        return row

    def _build_quadrant(self, quadrant_id: str) -> FormSection:
        box = FormSection("")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        kind = QUADRANT_KINDS.get(quadrant_id, "info")
        header = SemanticLabel(QUADRANT_LABELS[quadrant_id], kind=kind)
        header.setWordWrap(False)
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        box.add_widget(header)

        lst = _QuadrantList(quadrant_id)
        lst.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lst.task_dropped.connect(lambda tid, q=quadrant_id: self._on_drop(tid, q))
        lst.edit_requested.connect(self._on_edit)
        lst.move_requested.connect(self._on_move)
        lst.delete_requested.connect(self._on_delete)
        self._lists[quadrant_id] = lst
        box.add_widget(lst)
        return box

    def _apply_filter_chips(self) -> None:
        _refresh_button_class(self._chip_today, primary=self._filter == "today")
        _refresh_button_class(self._chip_all, primary=self._filter == "all")

    def _apply_view_chips(self) -> None:
        _refresh_button_class(self._chip_board, primary=self._view == "board")
        _refresh_button_class(self._chip_cal, primary=self._view == "calendar")

    def _set_view(self, mode: str) -> None:
        self._view = "calendar" if mode == "calendar" else "board"
        self._stack.setCurrentIndex(1 if self._view == "calendar" else 0)
        self._apply_view_chips()
        if self._view == "calendar":
            self._calendar.refresh_tasks()
            self._reload_calendar_day()
        self.report_status("日历模式" if self._view == "calendar" else "看板模式")

    def _set_filter(self, mode: str) -> None:
        self._filter = "today" if mode == "today" else "all"
        self._apply_filter_chips()
        self._reload_all()
        label = "今日" if self._filter == "today" else "全部"
        self.report_status(f"筛选 · {label}")

    def _on_calendar_day(self, day: date) -> None:
        self._reload_calendar_day()

    def _reload_calendar_day(self) -> None:
        day = self._calendar.selected_date()
        self._day_list.clear()
        self._day_task_ids: list[str] = []
        for t in load_tasks():
            if not task_covers_day(t, day):
                continue
            if not matches_filter(t, self._filter):
                continue
            tid = str(t.get("id") or "")
            self._day_task_ids.append(tid)
            qlab = QUADRANT_LABELS.get(str(t.get("quadrant") or ""), "")
            done = "✓ " if t.get("done") else ""
            start = str(t.get("start") or "").strip()
            due = str(t.get("due") or "").strip()
            span = f" · {start[5:]}→{due[5:]}" if start and due and start != due else ""
            self._day_list.addItem(f"{done}{t.get('title')} · {qlab}{span}")

    def _on_add_for_selected_day(self, day=None) -> None:
        # 按钮 clicked 会传入 bool；日历信号传入 date
        if not isinstance(day, date):
            day = self._calendar.selected_date()
        iso = day.isoformat()
        dlg = _TaskFormDialog(
            self,
            title="添加任务",
            initial={"start": iso, "due": iso},
            default_quadrant=Q1,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        title = vals.get("title") or ""
        if not title:
            show_warning(self, "请填写任务标题。")
            return
        add_task(
            title,
            str(vals.get("quadrant") or Q1),
            start=str(vals.get("start") or iso),
            due=str(vals.get("due") or iso),
        )
        self._reload_all()
        self.report_status("已添加任务", level=StatusLevel.SUCCESS)

    def _on_calendar_edit(self) -> None:
        row = self._day_list.currentRow()
        ids = getattr(self, "_day_task_ids", [])
        if 0 <= row < len(ids):
            self._on_edit(ids[row])

    def _reload_quadrant(self, quadrant_id: str) -> None:
        lst = self._lists[quadrant_id]
        lst.clear()
        for task in tasks_in_quadrant(quadrant_id):
            if not matches_filter(task, self._filter):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, task.get("id"))
            lst.addItem(item)
            row = _TaskRow(task)
            row.done_toggled.connect(self._on_done_toggled)
            lst.setItemWidget(item, row)
            # 按实际行高，避免逾期徽章被列表行高裁切
            hint_h = max(row.sizeHint().height(), TREE_ROW_HEIGHT + 16, 40)
            item.setSizeHint(QSize(0, hint_h))

    def _reload_all(self) -> None:
        self._date_label.setText(_today_label())
        for qid in QUADRANT_IDS:
            self._reload_quadrant(qid)
        if self._view == "calendar":
            self._calendar.refresh_tasks()
            self._reload_calendar_day()

    def _on_add(self) -> None:
        dlg = _TaskFormDialog(self, title="添加任务", default_quadrant=Q1)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        title = vals.get("title") or ""
        if not title:
            show_warning(self, "请填写任务标题。")
            return
        due = vals.get("due") or ""
        start = vals.get("start") or ""
        if due and parse_due(due) is None:
            show_warning(self, "截止日期格式须为 YYYY-MM-DD。")
            return
        if start and parse_due(start) is None:
            show_warning(self, "开始日期格式须为 YYYY-MM-DD。")
            return
        add_task(
            title,
            str(vals.get("quadrant") or Q1),
            start=start or due,
            due=due or start,
        )
        self._reload_all()
        self.report_status("已添加任务", level=StatusLevel.SUCCESS)

    def _on_edit(self, task_id: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        dlg = _TaskFormDialog(
            self,
            title="编辑任务",
            initial=task,
            default_quadrant=str(task.get("quadrant") or Q1),
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        title = vals.get("title") or ""
        if not title:
            show_warning(self, "请填写任务标题。")
            return
        due = vals.get("due") or ""
        start = vals.get("start") or ""
        if due and parse_due(due) is None:
            show_warning(self, "截止日期格式须为 YYYY-MM-DD。")
            return
        if start and parse_due(start) is None:
            show_warning(self, "开始日期格式须为 YYYY-MM-DD。")
            return
        update_task(
            task_id,
            title=title,
            start=start or due,
            due=due or start,
            quadrant=str(vals.get("quadrant") or task.get("quadrant") or Q1),
        )
        self._reload_all()
        self.report_status("已更新任务", level=StatusLevel.SUCCESS)

    def _on_move(self, task_id: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        current = str(task.get("quadrant") or Q1)
        dlg = _MoveQuadrantDialog(self, current=current)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        target = dlg.selected_quadrant()
        if not target or target == current:
            return
        move_task(task_id, target)
        self._reload_all()
        self.report_status(f"已移到「{QUADRANT_LABELS[target]}」", level=StatusLevel.SUCCESS)

    def _on_drop(self, task_id: str, target_quadrant: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        if task.get("quadrant") == target_quadrant:
            return
        move_task(task_id, target_quadrant)
        self._reload_all()
        self.report_status(
            f"已拖到「{QUADRANT_LABELS[target_quadrant]}」",
            level=StatusLevel.SUCCESS,
        )

    def _on_done_toggled(self, task_id: str, done: bool) -> None:
        task = find_task(task_id)
        if not task:
            return
        if bool(task.get("done")) == done:
            return
        update_task(task_id, done=done)
        self._reload_all()
        self.report_status("已完成" if done else "已恢复为未完成", level=StatusLevel.SUCCESS)

    def _on_delete(self, task_id: str) -> None:
        task = find_task(task_id)
        label = (task or {}).get("title") or "该任务"
        if not confirm_delete(self, f"任务「{label}」"):
            return
        delete_task(task_id)
        self._reload_all()
        self.report_status("已删除任务")

    def on_enter(self) -> None:
        load_tasks()
        self._reload_all()
        n = count_overdue()
        if n > 0:
            self.report_status(f"有 {n} 项任务已逾期", level=StatusLevel.WARNING)
        else:
            total = len(load_tasks())
            self.report_status(f"四象限任务 · 共 {total} 项")

    def on_theme_changed(self, theme_id: str, palette: dict) -> None:
        self._calendar.refresh_tasks()
        if self._view == "calendar":
            self._reload_calendar_day()
