# -*- coding: utf-8 -*-
"""班级日程提醒：五场景课表 + 简易事件列表。"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_info, show_saved, show_warning
from modules.schedule_reminder.reminder_service import (
    add_event,
    delete_event,
    load_events,
    scan_due_events,
    update_event,
)
from modules.schedule_reminder.schedule_reminder_service import (
    SCENE_DEFS,
    data_file_path,
    export_all_scenes_xlsx,
    export_scene_xlsx,
    load_schedule_source,
    query_all_scenes,
)
from services.storage_paths import module_output_dir
from widgets import (
    DataTable,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    TabWidget,
)
from widgets.list_edit import FormEditDialog, ListPanel, confirm_delete


class ScheduleReminderPage(BasePage):
    page_id = "schedule_reminder"
    page_title = "班级日程提醒"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._events = []
        self._scenes = {}
        self._tables: dict[str, DataTable] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll, 1)

        scroll.add_widget(
            PageHeader(
                "班级日程提醒",
                "加载课表 Excel，按五场景筛选并导出；也可维护简易到期事件。",
            )
        )

        self._main_tabs = TabWidget()
        self._main_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        scroll.content_layout.addWidget(self._main_tabs, 1)
        self._main_tabs.addTab(self._build_scenes_tab(), "五场景课表")
        self._main_tabs.addTab(self._build_events_tab(), "简易事件")

        log_box = FormSection("日志")
        log_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(56)
        self._log.setMaximumHeight(88)
        self._log.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        log_box.add_widget(self._log)
        scroll.add_widget(log_box)
        self.apply_page_focus_policy()
        self._reload_events()

    def primary_focus_widget(self):
        return self._excel_path

    def _build_scenes_tab(self) -> QWidget:
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 0, 0, 0)

        src = FormSection("课表数据源")
        src.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        row = QHBoxLayout()
        self._excel_path = LineEdit()
        self._excel_path.setReadOnly(True)
        existing = data_file_path()
        if existing.is_file():
            self._excel_path.setText(str(existing))
        row.addWidget(self._excel_path, 1)
        btn_load = SecondaryButton("加载课表…")
        btn_load.clicked.connect(self._pick_schedule)
        row.addWidget(btn_load)
        btn_reload = SecondaryButton("重新查询")
        btn_reload.clicked.connect(self._reload_scenes)
        row.addWidget(btn_reload)
        src.add_layout(row)
        src.add_widget(
            HintLabel(
                "需含「开始时间」「结束时间」列（可用开课时间/结课时间等别名）。"
                "场景：布置场地(明天开始) / 课程签到(进行中) / 物流订单(今天结束) / 本周 / 下周。"
            )
        )
        lay.addWidget(src)

        actions = QHBoxLayout()
        btn_cur = PrimaryButton("导出当前场景")
        btn_cur.clicked.connect(self._export_current)
        actions.addWidget(btn_cur)
        btn_all = SecondaryButton("导出五场景 xlsx")
        btn_all.clicked.connect(self._export_all)
        actions.addWidget(btn_all)
        actions.addStretch(1)
        lay.addLayout(actions)

        self._scene_tabs = TabWidget()
        self._scene_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        for sid, title, _ in SCENE_DEFS:
            panel = QWidget()
            panel.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            pl = QVBoxLayout(panel)
            pl.setContentsMargins(0, 0, 0, 0)
            table = DataTable()
            table.setMinimumHeight(160)
            table.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._tables[sid] = table
            pl.addWidget(table, 1)
            self._scene_tabs.addTab(panel, title)
        lay.addWidget(self._scene_tabs, 1)
        return tab

    def _build_events_tab(self) -> QWidget:
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 0, 0, 0)
        box = FormSection("事件列表")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panel = ListPanel(
            add_label="新增",
            edit_label="编辑",
            delete_label="删除",
            refresh_label="刷新",
            hint="到期时间格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM",
        )
        self._panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._panel.bind_add(self._on_add)
        self._panel.bind_edit(self._on_edit)
        self._panel.bind_delete(self._on_delete)
        self._panel.bind_refresh(self._reload_events)
        box.add_widget(self._panel, stretch=1)
        lay.addWidget(box, 1)

        actions = QHBoxLayout()
        btn_scan = PrimaryButton("立即扫描到期")
        btn_scan.clicked.connect(self._on_scan)
        actions.addWidget(btn_scan)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addWidget(
            HintLabel("定时任务动作名：schedule_reminder_scan（系统设置 → 定时任务）。")
        )
        return tab

    def _pick_schedule(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择课表 Excel",
            "",
            "Excel (*.xlsx *.xls)",
        )
        if not path:
            return

        def _run() -> None:
            dest = load_schedule_source(path)
            self._excel_path.setText(str(dest))
            self._reload_scenes()
            self.report_status("课表已加载", level=StatusLevel.SUCCESS)
            show_saved(self, f"已加载并缓存到：\n{dest}", dest)

        self.run_safe(_run, title="加载失败")

    def _reload_scenes(self) -> None:
        def _run() -> None:
            self._scenes = query_all_scenes()
            for sid, _, _ in SCENE_DEFS:
                result = self._scenes.get(sid)
                table = self._tables[sid]
                if result is None:
                    continue
                table.set_headers(result.columns)
                table.set_rows([tuple(str(c) for c in row) for row in result.rows])
            counts = {
                sid: len(r.rows)
                for sid, r in self._scenes.items()
                if r and not (len(r.columns) == 1 and r.columns[0] == "提示")
            }
            msg = "已刷新五场景：" + "、".join(f"{k}={v}" for k, v in counts.items())
            self._log.setPlainText(msg)
            self.report_status(msg)

        self.run_safe(_run, title="查询失败")

    def _current_scene_id(self) -> str:
        idx = self._scene_tabs.currentIndex()
        if 0 <= idx < len(SCENE_DEFS):
            return SCENE_DEFS[idx][0]
        return SCENE_DEFS[0][0]

    def _export_current(self) -> None:
        sid = self._current_scene_id()
        result = self._scenes.get(sid)
        if result is None:
            show_warning(self, "请先加载并查询课表。")
            return

        def _run() -> None:
            path = export_scene_xlsx(result, module_output_dir(self.page_id, create=True))
            self._log.setPlainText(f"已导出：{path}")
            self.report_status("场景已导出", level=StatusLevel.SUCCESS)
            show_saved(self, f"已导出：\n{path}", path)

        self.run_safe(_run, title="导出失败")

    def _export_all(self) -> None:
        def _run() -> None:
            results = self._scenes or query_all_scenes()
            path = export_all_scenes_xlsx(results, module_output_dir(self.page_id, create=True))
            self._log.setPlainText(f"五场景已导出：{path}")
            self.report_status("五场景已导出", level=StatusLevel.SUCCESS)
            show_saved(self, f"已导出：\n{path}", path)

        self.run_safe(_run, title="导出失败")

    def _reload_events(self) -> None:
        self._events = load_events()
        lines = []
        for ev in self._events:
            flag = "✓" if ev.notified else "·"
            lines.append(f"{flag} {ev.due_at}  {ev.title}")
        self._panel.set_items(lines)

    def _on_add(self) -> None:
        dlg = FormEditDialog(
            self,
            title="新增日程",
            fields=[("标题", "title"), ("到期时间", "due_at"), ("备注", "note")],
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        if not vals.get("title") or not vals.get("due_at"):
            show_warning(self, "标题与到期时间必填。")
            return
        add_event(vals["title"], vals["due_at"], vals.get("note") or "")
        self._reload_events()
        self.report_status("已新增日程", level=StatusLevel.SUCCESS)

    def _on_edit(self) -> None:
        row = self._panel.current_row()
        if row < 0 or row >= len(self._events):
            show_warning(self, "请先选择一条日程。")
            return
        ev = self._events[row]
        dlg = FormEditDialog(
            self,
            title="编辑日程",
            fields=[("标题", "title"), ("到期时间", "due_at"), ("备注", "note")],
        )
        dlg.set_values({"title": ev.title, "due_at": ev.due_at, "note": ev.note})
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        update_event(ev.id, title=vals["title"], due_at=vals["due_at"], note=vals.get("note") or "")
        self._reload_events()
        self.report_status("已更新日程", level=StatusLevel.SUCCESS)

    def _on_delete(self) -> None:
        row = self._panel.current_row()
        if row < 0 or row >= len(self._events):
            return
        ev = self._events[row]
        if not confirm_delete(self, f"日程「{ev.title}」"):
            return
        delete_event(ev.id)
        self._reload_events()
        self.report_status("已删除日程")

    def _on_scan(self) -> None:
        def _run() -> None:
            n = scan_due_events()
            msg = f"扫描完成：到期 {n} 项"
            self._log.setPlainText(msg)
            self._reload_events()
            self.report_status(msg, level=StatusLevel.SUCCESS if n else StatusLevel.INFO)
            show_info(self, msg)

        self.run_safe(_run, title="扫描失败")

    def on_enter(self) -> None:
        self._reload_events()
        if data_file_path().is_file():
            self._reload_scenes()
        self.report_status("班级日程提醒")
