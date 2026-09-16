# -*- coding: utf-8 -*-
"""任务管理：状态看板 · 日历 · 四象限优先级（Eisenhower）。"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QMimeData, QTimer, Signal, QSize
from PySide6.QtGui import QDrag, QAction, QKeySequence, QShortcut, QShowEvent
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
    QUADRANT_HINTS,
    QUADRANT_IDS,
    QUADRANT_KINDS,
    QUADRANT_LABELS,
    QUADRANT_SHORT,
    Q1,
    COLOR_LEGEND,
    STATUS_HEADERS,
    STATUS_HINTS,
    STATUS_IDS,
    STATUS_KINDS,
    STATUS_LABELS,
    add_task,
    count_overdue,
    delete_task,
    find_task,
    format_note_handoff,
    load_tasks,
    matches_filter,
    move_task,
    normalize_status,
    overdue_days,
    parse_due,
    set_task_status,
    task_covers_day,
    task_span,
    tasks_in_quadrant,
    tasks_in_status,
    update_task,
)
from widgets import (
    CheckBox,
    ComboBox,
    DateEdit,
    FormRow,
    FormSection,
    HintLabel,
    ListWidget,
    PlainTextEdit,
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


def _send_task_to_notepad(task: dict, shell) -> bool:
    title, body = format_note_handoff(task)
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

    QuickNotepadPage.stash_incoming(body, title=title)
    if shell is not None and hasattr(shell, "navigate"):
        shell.navigate("quick_notepad")
        return True
    return False


class _TaskRow(QWidget):
    """任务行：勾选 · 标题 · 优先级/状态徽章 · 截止。"""

    done_toggled = Signal(str, bool)

    def __init__(self, task: dict, parent=None, *, peer_badge: str = "quadrant") -> None:
        """peer_badge=quadrant：状态列旁显示优先级；=status：四象限列旁显示进度。"""
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
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)
        desc = str(task.get("description") or "").strip()
        qid = str(task.get("quadrant") or Q1)
        st = normalize_status(str(task.get("status") or ""), done=bool(task.get("done")))
        tip_bits = [title]
        if desc:
            tip_bits.append(desc)
        tip_bits.append(QUADRANT_HINTS.get(qid, ""))
        tip_bits.append(STATUS_HINTS.get(st, ""))
        tip = "\n\n".join(x for x in tip_bits if x)
        self._title.setToolTip(tip)
        self.setToolTip(tip)
        self._title.setMinimumWidth(40)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._title, 1)

        if desc:
            note_mark = HintLabel("有说明")
            note_mark.setToolTip("有任务说明 · 右键可送入记事本")
            note_mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lay.addWidget(note_mark)

        # 行内第二维只用文字，避免与列头色块抢注意力
        if peer_badge == "quadrant":
            peer = HintLabel(QUADRANT_SHORT.get(qid, "Ⅰ"))
            peer.setToolTip(QUADRANT_HINTS.get(qid, ""))
        else:
            peer = HintLabel(STATUS_LABELS.get(st, st))
            peer.setToolTip(STATUS_HINTS.get(st, ""))
        peer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(peer)

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

    def _list(self) -> _BucketList | None:
        w = self.parent()
        while w is not None:
            if isinstance(w, _BucketList):
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


class _BucketList(ListWidget):
    """支持拖放的任务列表（象限或进度状态列）。"""

    task_dropped = Signal(str)
    edit_requested = Signal(str)
    move_requested = Signal(str)
    notepad_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, bucket_id: str, parent=None) -> None:
        super().__init__(parent)
        self.bucket_id = bucket_id
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
        act_note = QAction("送入记事本", menu)
        act_del = QAction("删除", menu)
        menu.addAction(act_edit)
        menu.addAction(act_move)
        menu.addAction(act_note)
        menu.addSeparator()
        menu.addAction(act_del)
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is act_edit:
            self.edit_requested.emit(tid)
        elif chosen is act_move:
            self.move_requested.emit(tid)
        elif chosen is act_note:
            self.notepad_requested.emit(tid)
        elif chosen is act_del:
            self.delete_requested.emit(tid)


# 兼容旧名
_QuadrantList = _BucketList


class _TaskFormDialog(BaseDialog):
    """新增 / 编辑任务（标题 · 日期 · 优先级 · 状态 · 任务说明）。"""

    dialog_kind = "large"

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

        self._title = LineEdit()
        self._title.setText(str(init.get("title") or ""))
        self._title.setPlaceholderText("一句话说清要做什么")
        lay.addWidget(FormRow("标题", self._title, label_width=64))

        dates = QHBoxLayout()
        dates.setSpacing(12)
        self._start = DateEdit()
        start_raw = str(init.get("start") or "").strip()
        if start_raw:
            self._start.set_iso(start_raw)
        elif str(init.get("due") or "").strip():
            self._start.set_iso(str(init.get("due") or ""))
        dates.addWidget(FormRow("开始", self._start, label_width=64), 1)

        self._due = DateEdit()
        due_raw = str(init.get("due") or "").strip()
        if due_raw:
            self._due.set_iso(due_raw)
        dates.addWidget(FormRow("截止", self._due, label_width=64), 1)
        lay.addLayout(dates)
        lay.addWidget(HintLabel("跨日任务：开始≠截止时，日历上通栏显示任务名。"))

        self._quadrant = ComboBox()
        current_q = str(init.get("quadrant") or default_quadrant)
        for qid in QUADRANT_IDS:
            self._quadrant.addItem(QUADRANT_LABELS[qid], qid)
        idx = self._quadrant.findData(current_q)
        self._quadrant.setCurrentIndex(idx if idx >= 0 else 0)
        lay.addWidget(FormRow("优先级", self._quadrant, label_width=64))
        lay.addWidget(HintLabel("优先级（列头色）：红立刻 · 紫计划 · 青速办 · 灰延后"))

        self._status = ComboBox()
        current_st = str(init.get("status") or ("done" if init.get("done") else "todo"))
        for sid in STATUS_IDS:
            self._status.addItem(STATUS_LABELS[sid], sid)
        sidx = self._status.findData(current_st)
        self._status.setCurrentIndex(sidx if sidx >= 0 else 0)
        lay.addWidget(FormRow("状态", self._status, label_width=64))
        lay.addWidget(HintLabel("进度（列头/日历条）：蓝待办 · 橙进行中 · 绿已完成"))

        desc_box = FormSection("任务说明")
        self._description = PlainTextEdit()
        self._description.setPlaceholderText("短说明、步骤、验收点写这里；长文点下方「送入记事本」…")
        self._description.setMinimumHeight(140)
        self._description.setPlainText(str(init.get("description") or ""))
        desc_box.add_widget(self._description)
        note_row = QHBoxLayout()
        note_row.addWidget(HintLabel("说明留给执行要点；会议纪要/长草稿用记事本"))
        note_row.addStretch(1)
        self._btn_to_note = SecondaryButton("送入记事本")
        self._btn_to_note.setToolTip("把当前标题与说明送到快速记事，便于展开写长文")
        self._btn_to_note.clicked.connect(self._on_send_notepad)
        note_row.addWidget(self._btn_to_note)
        desc_box.add_layout(note_row)
        lay.addWidget(desc_box, 1)

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("确定", self.accept)
        lay.addWidget(buttons)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._focus_title)

    def _focus_title(self) -> None:
        self._title.setFocus(Qt.FocusReason.OtherFocusReason)
        self._title.deselect()
        self._title.setCursorPosition(len(self._title.text()))

    def _on_send_notepad(self) -> None:
        vals = self.values()
        title = (vals.get("title") or "").strip()
        if not title:
            show_warning(self, "请先填写任务标题再送入记事本。")
            return
        draft = {
            "title": title,
            "description": vals.get("description") or "",
            "quadrant": vals.get("quadrant") or Q1,
            "status": vals.get("status") or "todo",
            "start": vals.get("start") or "",
            "due": vals.get("due") or "",
            "done": (vals.get("status") or "") == "done",
        }
        shell = self.parent().window() if self.parent() is not None else None
        if not _send_task_to_notepad(draft, shell):
            show_warning(self, "无法打开记事本（请从主窗口操作）。")

    def values(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "description": self._description.toPlainText().strip(),
            "start": self._start.to_iso(),
            "due": self._due.to_iso(),
            "quadrant": str(self._quadrant.currentData() or Q1),
            "status": str(self._status.currentData() or "todo"),
        }


class _MoveQuadrantDialog(BaseDialog):
    dialog_kind = "small"

    def __init__(self, parent=None, *, current: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("改优先级")
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(HintLabel("选择优先级：立刻 / 计划 / 速办 / 延后"))
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


class _MoveStatusDialog(BaseDialog):
    dialog_kind = "small"

    def __init__(self, parent=None, *, current: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("改状态")
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(HintLabel("进度：待办（蓝）→ 进行中（橙）→ 已完成（绿）"))
        self._combo = ComboBox()
        for sid in STATUS_IDS:
            if sid == current:
                continue
            self._combo.addItem(STATUS_LABELS[sid], sid)
        lay.addWidget(self._combo)
        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        buttons.add_primary("确定", self.accept)
        lay.addWidget(buttons)

    def selected_status(self) -> str:
        return str(self._combo.currentData() or "")


class QuadrantTasksPage(BasePage):
    page_id = "quadrant_tasks"
    page_title = "任务管理"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lists: dict[str, _BucketList] = {}
        self._status_lists: dict[str, _BucketList] = {}
        self._filter = "all"
        self._view = "status"  # status | board | calendar
        self._focus_task_id: str | None = None
        self._syncing_focus = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll, 1)

        scroll.add_layout(self._build_top_bar())

        self._stack = QStackedWidget()

        # 入栈顺序：状态 → 日历 → 四象限
        status_board = QWidget()
        status_grid = QHBoxLayout(status_board)
        status_grid.setSpacing(12)
        for sid in STATUS_IDS:
            status_grid.addWidget(self._build_status_column(sid), 1)

        # 四象限（后入栈）
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

        # 日历（中位入栈）
        cal_host = QWidget()
        cal_lay = QHBoxLayout(cal_host)
        cal_lay.setContentsMargins(0, 0, 0, 0)
        cal_lay.setSpacing(12)
        self._calendar = ScheduleMonthView()
        self._calendar.daySelected.connect(self._on_calendar_day)
        self._calendar.dayCreateRequested.connect(self._on_add_for_selected_day)
        self._calendar.rangeCreateRequested.connect(self._on_add_for_range)
        self._calendar.dayEditRequested.connect(self._on_day_edit)
        self._calendar.taskActivated.connect(self._on_calendar_task_activated)
        self._calendar.monthChanged.connect(lambda *_: self._calendar.refresh_tasks())
        cal_lay.addWidget(self._calendar, 3)
        day_box = FormSection("当日任务")
        day_box.setToolTip(
            "单击选日；再点同一日新建。拖选多日弹出新建。"
            "双击有任务的日可编辑。跨日通栏显示标题。"
            "三视图共用同一批任务与选中项。"
        )
        day_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._day_list = ListWidget()
        self._day_list.setMinimumHeight(280)
        self._day_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._day_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._day_list.itemDoubleClicked.connect(self._on_calendar_edit)
        self._day_list.currentRowChanged.connect(self._on_day_list_row)
        day_box.add_widget(self._day_list, 1)
        day_row = QHBoxLayout()
        btn_cal_add = PrimaryButton("本日新建")
        btn_cal_add.clicked.connect(self._on_add_for_selected_day)
        day_row.addWidget(btn_cal_add)
        btn_cal_edit = SecondaryButton("编辑")
        btn_cal_edit.clicked.connect(self._on_calendar_edit)
        day_row.addWidget(btn_cal_edit)
        btn_cal_note = SecondaryButton("送入记事")
        btn_cal_note.setToolTip("把当日选中任务送到快速记事本")
        btn_cal_note.clicked.connect(self._on_calendar_notepad)
        day_row.addWidget(btn_cal_note)
        day_row.addStretch(1)
        day_box.add_layout(day_row)
        cal_lay.addWidget(day_box, 2)
        self._stack.addWidget(status_board)  # 0 状态
        self._stack.addWidget(cal_host)  # 1 日历
        self._stack.addWidget(board)  # 2 四象限
        scroll.content_layout.addWidget(self._stack, 1)
        scroll.add_widget(HintLabel(COLOR_LEGEND))
        self._apply_filter_chips()
        self._apply_view_chips()
        self._stack.setCurrentIndex(0)
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

        # 两组：范围 / 视图 —— 避免一排同形按钮难认
        scope_lab = HintLabel("范围")
        scope_lab.setWordWrap(False)
        row.addWidget(scope_lab)
        self._chip_today = SecondaryButton("今日")
        self._chip_all = SecondaryButton("全部")
        self._chip_today.setToolTip("只看覆盖今天或已逾期的未完成任务")
        self._chip_all.setToolTip("显示全部任务（含已完成）")
        self._chip_today.clicked.connect(lambda: self._set_filter("today"))
        self._chip_all.clicked.connect(lambda: self._set_filter("all"))
        row.addWidget(self._chip_today)
        row.addWidget(self._chip_all)

        sep = HintLabel("｜")
        sep.setWordWrap(False)
        row.addWidget(sep)

        view_lab = HintLabel("视图")
        view_lab.setWordWrap(False)
        row.addWidget(view_lab)
        self._chip_status = SecondaryButton("看板")
        self._chip_cal = SecondaryButton("日历")
        self._chip_board = SecondaryButton("优先级")
        self._chip_status.setToolTip("看板：待办 → 进行中 → 已完成（拖卡片改进度）")
        self._chip_cal.setToolTip("日历：按日期排期与跨日通栏")
        self._chip_board.setToolTip("优先级：立刻 / 计划 / 速办 / 延后（四象限）")
        self._chip_status.clicked.connect(lambda: self._set_view("status"))
        self._chip_cal.clicked.connect(lambda: self._set_view("calendar"))
        self._chip_board.clicked.connect(lambda: self._set_view("board"))
        row.addWidget(self._chip_status)
        row.addWidget(self._chip_cal)
        row.addWidget(self._chip_board)

        btn_add = PrimaryButton("新建")
        btn_add.setToolTip("添加任务 (Ctrl+N)")
        btn_add.clicked.connect(self._on_add)
        row.addWidget(btn_add)
        return row

    def _build_quadrant(self, quadrant_id: str) -> FormSection:
        box = FormSection("")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        kind = QUADRANT_KINDS.get(quadrant_id, "muted")
        header = SemanticLabel(QUADRANT_LABELS[quadrant_id], kind=kind)
        header.setToolTip(QUADRANT_HINTS.get(quadrant_id, ""))
        header.setWordWrap(False)
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hf = header.font()
        hf.setBold(True)
        hf.setPointSize(max(hf.pointSize() + 1, 11))
        header.setFont(hf)
        box.add_widget(header)

        lst = _BucketList(quadrant_id)
        lst.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lst.task_dropped.connect(lambda tid, q=quadrant_id: self._on_drop_quadrant(tid, q))
        lst.edit_requested.connect(self._on_edit)
        lst.move_requested.connect(self._on_move)
        lst.notepad_requested.connect(self._on_send_notepad)
        lst.delete_requested.connect(self._on_delete)
        lst.currentItemChanged.connect(self._on_bucket_selection)
        self._lists[quadrant_id] = lst
        box.add_widget(lst)
        return box

    def _build_status_column(self, status_id: str) -> FormSection:
        box = FormSection("")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        kind = STATUS_KINDS.get(status_id, "info")
        header = SemanticLabel(STATUS_HEADERS.get(status_id, STATUS_LABELS[status_id]), kind=kind)
        header.setToolTip(STATUS_HINTS.get(status_id, ""))
        header.setWordWrap(False)
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hf = header.font()
        hf.setBold(True)
        hf.setPointSize(max(hf.pointSize() + 1, 11))
        header.setFont(hf)
        box.add_widget(header)

        lst = _BucketList(status_id)
        lst.setMinimumHeight(320)
        lst.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lst.task_dropped.connect(lambda tid, s=status_id: self._on_drop_status(tid, s))
        lst.edit_requested.connect(self._on_edit)
        lst.move_requested.connect(self._on_move_status)
        lst.notepad_requested.connect(self._on_send_notepad)
        lst.delete_requested.connect(self._on_delete)
        lst.currentItemChanged.connect(self._on_bucket_selection)
        self._status_lists[status_id] = lst
        box.add_widget(lst)
        return box

    def _apply_filter_chips(self) -> None:
        _refresh_button_class(self._chip_today, primary=self._filter == "today")
        _refresh_button_class(self._chip_all, primary=self._filter == "all")

    def _apply_view_chips(self) -> None:
        _refresh_button_class(self._chip_status, primary=self._view == "status")
        _refresh_button_class(self._chip_board, primary=self._view == "board")
        _refresh_button_class(self._chip_cal, primary=self._view == "calendar")

    def _set_view(self, mode: str) -> None:
        if mode == "calendar":
            self._view = "calendar"
            self._stack.setCurrentIndex(1)
        elif mode == "board":
            self._view = "board"
            self._stack.setCurrentIndex(2)
        else:
            self._view = "status"
            self._stack.setCurrentIndex(0)
        self._apply_view_chips()
        self._calendar.set_filter_mode(self._filter)
        self._calendar.set_focus_task(self._focus_task_id)
        if self._view == "calendar":
            self._reveal_focus_on_calendar()
            self._calendar.refresh_tasks()
            self._reload_calendar_day()
        else:
            self._restore_focus_selection()
        labels = {"status": "进度看板", "board": "优先级矩阵", "calendar": "日历排期"}
        self.report_status(labels.get(self._view, "任务管理"))

    def _set_filter(self, mode: str) -> None:
        self._filter = "today" if mode == "today" else "all"
        self._apply_filter_chips()
        self._reload_all()
        label = "今日" if self._filter == "today" else "全部"
        self.report_status(f"筛选 · {label}")

    def _on_bucket_selection(self, current, _previous) -> None:
        if self._syncing_focus or current is None:
            return
        tid = current.data(Qt.ItemDataRole.UserRole)
        if tid:
            self._set_focus(str(tid), reveal=False)

    def _on_day_list_row(self, row: int) -> None:
        if self._syncing_focus:
            return
        ids = getattr(self, "_day_task_ids", [])
        if 0 <= row < len(ids):
            self._set_focus(ids[row], reveal=False)

    def _on_calendar_task_activated(self, task_id: str) -> None:
        self._set_focus(task_id, reveal=False)
        self._on_edit(task_id)

    def _set_focus(self, task_id: str | None, *, reveal: bool = True) -> None:
        tid = (task_id or "").strip() or None
        if tid == self._focus_task_id and not reveal:
            self._calendar.set_focus_task(tid)
            return
        self._focus_task_id = tid
        self._calendar.set_focus_task(tid)
        if reveal:
            if self._view == "calendar":
                self._reveal_focus_on_calendar()
                self._reload_calendar_day()
            else:
                self._restore_focus_selection()

    def _reveal_focus_on_calendar(self) -> None:
        """切到日历时：落到焦点任务所在日，并高亮条。"""
        tid = self._focus_task_id
        if not tid:
            return
        task = find_task(tid)
        if not task:
            return
        span = task_span(task)
        if span is None:
            return
        start, end = span
        day = self._calendar.selected_date()
        if not (start <= day <= end):
            # 优先落在开始日；若开始日被今日筛选挡掉仍可看排期
            self._calendar.set_selected(start)

    def _restore_focus_selection(self) -> None:
        """在看板 / 优先级 / 当日列表里选中同一任务。"""
        tid = self._focus_task_id
        if not tid:
            return
        self._syncing_focus = True
        try:
            lists: list[_BucketList] = []
            if self._view == "status":
                lists = list(self._status_lists.values())
            elif self._view == "board":
                lists = list(self._lists.values())
            for lst in lists:
                found = False
                for i in range(lst.count()):
                    item = lst.item(i)
                    if item is None:
                        continue
                    if str(item.data(Qt.ItemDataRole.UserRole) or "") == tid:
                        lst.setCurrentRow(i)
                        lst.scrollToItem(item)
                        found = True
                        break
                if not found:
                    lst.clearSelection()
            ids = getattr(self, "_day_task_ids", [])
            if tid in ids:
                row = ids.index(tid)
                self._day_list.setCurrentRow(row)
            self._calendar.set_focus_task(tid)
        finally:
            self._syncing_focus = False

    def _on_calendar_day(self, day: date) -> None:
        self._reload_calendar_day()

    def _reload_calendar_day(self) -> None:
        day = self._calendar.selected_date()
        self._day_list.clear()
        self._day_task_ids: list[str] = []
        focus_row = -1
        for t in load_tasks():
            if not task_covers_day(t, day):
                continue
            if not matches_filter(t, self._filter):
                continue
            tid = str(t.get("id") or "")
            if tid and tid == self._focus_task_id:
                focus_row = len(self._day_task_ids)
            self._day_task_ids.append(tid)
            qlab = QUADRANT_LABELS.get(str(t.get("quadrant") or ""), "")
            done = "✓ " if t.get("done") else ""
            start = str(t.get("start") or "").strip()
            due = str(t.get("due") or "").strip()
            span = f" · {start[5:]}→{due[5:]}" if start and due and start != due else ""
            st = STATUS_LABELS.get(str(t.get("status") or ""), "")
            st_bit = f" · {st}" if st else ""
            self._day_list.addItem(f"{done}{t.get('title')} · {qlab}{st_bit}{span}")
        if focus_row >= 0:
            self._syncing_focus = True
            try:
                self._day_list.setCurrentRow(focus_row)
            finally:
                self._syncing_focus = False

    def _on_add_for_selected_day(self, day=None) -> None:
        # 按钮 clicked 会传入 bool；日历信号传入 date
        if not isinstance(day, date):
            day = self._calendar.selected_date()
        iso = day.isoformat()
        self._open_add_dialog(start=iso, due=iso)

    def _on_add_for_range(self, start: date, end: date) -> None:
        self._open_add_dialog(start=start.isoformat(), due=end.isoformat())

    def _open_add_dialog(self, *, start: str, due: str) -> None:
        dlg = _TaskFormDialog(
            self,
            title="添加任务",
            initial={"start": start, "due": due},
            default_quadrant=Q1,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        title = vals.get("title") or ""
        if not title:
            show_warning(self, "请填写任务标题。")
            return
        created = add_task(
            title,
            str(vals.get("quadrant") or Q1),
            start=str(vals.get("start") or start),
            due=str(vals.get("due") or due),
            description=str(vals.get("description") or ""),
            status=str(vals.get("status") or "todo"),
        )
        self._focus_task_id = str(created.get("id") or "") or None
        self._reload_all()
        self.report_status("已添加任务", level=StatusLevel.SUCCESS)

    def _on_day_edit(self, day: date) -> None:
        """双击有任务的日历日 → 打开修改（优先焦点任务，否则当日列表第一条）。"""
        tasks = [
            t
            for t in load_tasks()
            if matches_filter(t, self._filter) and task_covers_day(t, day)
        ]
        if not tasks:
            return
        if self._focus_task_id:
            for t in tasks:
                if str(t.get("id") or "") == self._focus_task_id:
                    self._on_edit(self._focus_task_id)
                    return
        tid = str(tasks[0].get("id") or "")
        if tid:
            self._set_focus(tid, reveal=False)
            self._on_edit(tid)

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
            row = _TaskRow(task, peer_badge="status")
            row.done_toggled.connect(self._on_done_toggled)
            lst.setItemWidget(item, row)
            hint_h = max(row.sizeHint().height(), TREE_ROW_HEIGHT + 16, 40)
            item.setSizeHint(QSize(0, hint_h))

    def _reload_status_column(self, status_id: str) -> None:
        lst = self._status_lists[status_id]
        lst.clear()
        for task in tasks_in_status(status_id):
            if not matches_filter(task, self._filter):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, task.get("id"))
            lst.addItem(item)
            row = _TaskRow(task, peer_badge="quadrant")
            row.done_toggled.connect(self._on_done_toggled)
            lst.setItemWidget(item, row)
            hint_h = max(row.sizeHint().height(), TREE_ROW_HEIGHT + 16, 40)
            item.setSizeHint(QSize(0, hint_h))

    def _reload_all(self) -> None:
        self._date_label.setText(_today_label())
        for qid in QUADRANT_IDS:
            self._reload_quadrant(qid)
        for sid in STATUS_IDS:
            self._reload_status_column(sid)
        # 三视图共用筛选与焦点：后台视图也同步刷新，切过去立刻一致
        self._calendar.set_filter_mode(self._filter)
        self._calendar.set_focus_task(self._focus_task_id)
        self._calendar.refresh_tasks()
        self._reload_calendar_day()
        self._restore_focus_selection()

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
        created = add_task(
            title,
            str(vals.get("quadrant") or Q1),
            start=start or due,
            due=due or start,
            description=str(vals.get("description") or ""),
            status=str(vals.get("status") or "todo"),
        )
        self._focus_task_id = str(created.get("id") or "") or None
        self._reload_all()
        self.report_status("已添加任务", level=StatusLevel.SUCCESS)

    def _on_edit(self, task_id: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        self._focus_task_id = task_id
        dlg = _TaskFormDialog(
            self,
            title="编辑任务",
            initial=task,
            default_quadrant=str(task.get("quadrant") or Q1),
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            self._calendar.set_focus_task(self._focus_task_id)
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
            description=str(vals.get("description") or ""),
            start=start or due,
            due=due or start,
            quadrant=str(vals.get("quadrant") or task.get("quadrant") or Q1),
            status=str(vals.get("status") or task.get("status") or "todo"),
        )
        self._focus_task_id = task_id
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
        self._focus_task_id = task_id
        self._reload_all()
        self.report_status(f"已移到「{QUADRANT_LABELS[target]}」", level=StatusLevel.SUCCESS)

    def _on_move_status(self, task_id: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        current = str(task.get("status") or "todo")
        dlg = _MoveStatusDialog(self, current=current)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        target = dlg.selected_status()
        if not target or target == current:
            return
        set_task_status(task_id, target)
        self._focus_task_id = task_id
        self._reload_all()
        self.report_status(f"已改为「{STATUS_LABELS[target]}」", level=StatusLevel.SUCCESS)

    def _on_drop_quadrant(self, task_id: str, target_quadrant: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        if task.get("quadrant") == target_quadrant:
            return
        move_task(task_id, target_quadrant)
        self._focus_task_id = task_id
        self._reload_all()
        self.report_status(
            f"已拖到「{QUADRANT_LABELS[target_quadrant]}」",
            level=StatusLevel.SUCCESS,
        )

    def _on_drop_status(self, task_id: str, target_status: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        if str(task.get("status") or "") == target_status:
            return
        set_task_status(task_id, target_status)
        self._focus_task_id = task_id
        self._reload_all()
        self.report_status(
            f"已拖到「{STATUS_LABELS[target_status]}」",
            level=StatusLevel.SUCCESS,
        )

    def _on_done_toggled(self, task_id: str, done: bool) -> None:
        task = find_task(task_id)
        if not task:
            return
        if bool(task.get("done")) == done:
            return
        update_task(task_id, done=done)
        self._focus_task_id = task_id
        self._reload_all()
        self.report_status("已完成" if done else "已恢复为未完成", level=StatusLevel.SUCCESS)

    def _on_delete(self, task_id: str) -> None:
        task = find_task(task_id)
        label = (task or {}).get("title") or "该任务"
        if not confirm_delete(self, f"任务「{label}」"):
            return
        delete_task(task_id)
        if self._focus_task_id == task_id:
            self._focus_task_id = None
        self._reload_all()
        self.report_status("已删除任务")


    def _on_send_notepad(self, task_id: str) -> None:
        task = find_task(task_id)
        if not task:
            return
        if _send_task_to_notepad(task, self.window()):
            self.report_status("已送入记事本", level=StatusLevel.SUCCESS)
        else:
            show_warning(self, "无法打开记事本。")

    def _on_calendar_notepad(self) -> None:
        row = self._day_list.currentRow()
        ids = getattr(self, "_day_task_ids", [])
        if not (0 <= row < len(ids)):
            show_warning(self, "请先在当日任务中选中一项。")
            return
        self._on_send_notepad(ids[row])

    def on_enter(self) -> None:
        load_tasks()
        self._reload_all()
        n = count_overdue()
        if n > 0:
            self.report_status(f"有 {n} 项任务已逾期", level=StatusLevel.WARNING)
        else:
            total = len(load_tasks())
            self.report_status(f"任务管理 · 共 {total} 项 · 状态 → 日历 → 四象限")

    def on_theme_changed(self, theme_id: str, palette: dict) -> None:
        self._calendar.refresh_tasks()
        if self._view == "calendar":
            self._reload_calendar_day()
