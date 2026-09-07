# -*- coding: utf-8 -*-
"""班级日程提醒：五场景课表 + 简易事件列表。"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
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
from services.harness_task_runner import HarnessTaskRunner
from services.storage_paths import module_output_dir
from widgets import (
    DataTable,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
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
        self._scene_mtime: float | None = None
        self._scene_runner = HarnessTaskRunner(self)

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(10)

        header = PageHeader(
            "班级日程提醒",
            "加载课表 Excel，按五场景筛选并导出；也可维护简易到期事件。",
        )
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        outer.addWidget(header)

        self._main_tabs = TabWidget()
        self._main_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._main_tabs.setDocumentMode(True)
        outer.addWidget(self._main_tabs, 1)
        self._main_tabs.addTab(self._build_scenes_tab(), "五场景课表")
        self._main_tabs.addTab(self._build_events_tab(), "简易事件")

        log_box = FormSection("日志")
        log_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(44)
        self._log.setMaximumHeight(68)
        self._log.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        log_box.add_widget(self._log)
        outer.addWidget(log_box)
        self.apply_page_focus_policy()
        self._reload_events()

    def primary_focus_widget(self):
        return self._excel_path

    def _build_scenes_tab(self) -> QWidget:
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._excel_path = LineEdit()
        self._excel_path.setReadOnly(True)
        self._excel_path.setToolTip(
            "需含「开始时间」「结束时间」列（可用开课时间/结课时间等别名）。"
        )
        existing = data_file_path()
        if existing.is_file():
            self._excel_path.setText(str(existing))
        toolbar.addWidget(self._excel_path, 1)
        btn_load = SecondaryButton("加载课表…")
        btn_load.setToolTip("选择 Excel 并缓存到本机数据目录")
        btn_load.clicked.connect(self._pick_schedule)
        toolbar.addWidget(btn_load)
        btn_reload = SecondaryButton("重新查询")
        btn_reload.setToolTip("按五场景重新筛选当前课表")
        btn_reload.clicked.connect(self._reload_scenes)
        toolbar.addWidget(btn_reload)
        btn_cur = PrimaryButton("导出当前场景")
        btn_cur.clicked.connect(self._export_current)
        toolbar.addWidget(btn_cur)
        btn_all = SecondaryButton("导出五场景 xlsx")
        btn_all.clicked.connect(self._export_all)
        toolbar.addWidget(btn_all)
        lay.addLayout(toolbar)

        self._scene_tabs = TabWidget()
        self._scene_tabs.setDocumentMode(True)
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
            table.setMinimumHeight(280)
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

    def _reload_scenes(self, *, force: bool = True) -> None:
        path = data_file_path()
        if not path.is_file():
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        # 进页重复切业务：文件未变则不重读 Excel
        if (
            not force
            and self._scenes
            and mtime is not None
            and self._scene_mtime == mtime
        ):
            return
        if self._scene_runner.is_running():
            return

        self._log.setPlainText("正在查询五场景…")
        self.report_status("正在查询课表…", level=StatusLevel.INFO)

        def _work():
            scenes = query_all_scenes()
            try:
                stamp = path.stat().st_mtime
            except OSError:
                stamp = None
            return scenes, stamp

        def _done(ok: bool, value) -> None:
            if self.window() is not None and getattr(
                self.window(), "_current_id", None
            ) != self.page_id:
                # 已离开本页：仍缓存结果，下次进页免再等
                if ok and isinstance(value, tuple) and len(value) == 2:
                    self._scenes, self._scene_mtime = value[0], value[1]
                return
            if not ok:
                self.handle_error(value, title="查询失败")
                return
            scenes, stamp = value
            self._apply_scenes(scenes, stamp)

        if not self._scene_runner.run(_work, on_done=_done):
            # 线程忙时退回同步（极少）
            self.run_safe(
                lambda: self._apply_scenes(query_all_scenes(), mtime),
                title="查询失败",
            )

    def _apply_scenes(self, scenes: dict, mtime: float | None) -> None:
        self._scenes = scenes or {}
        self._scene_mtime = mtime
        # 延后一拍画表：刚离开引擎时 WebEngine deleteLater 未落稳，
        # 同步 setSectionResizeMode 会 Windows ACCESS_VIOLATION（见 toa3_faulthandler.log）
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: self._apply_scenes_ui(self._scenes))

    def _apply_scenes_ui(self, scenes: dict) -> None:
        if self.window() is not None and getattr(
            self.window(), "_current_id", None
        ) != self.page_id:
            return
        for sid, _, _ in SCENE_DEFS:
            result = (scenes or {}).get(sid)
            table = self._tables.get(sid)
            if result is None or table is None:
                continue
            try:
                table.set_headers(result.columns)
                table.set_rows([tuple(str(c) for c in row) for row in result.rows])
            except RuntimeError:
                continue
        counts = {
            sid: len(r.rows)
            for sid, r in (scenes or {}).items()
            if r and not (len(r.columns) == 1 and r.columns[0] == "提示")
        }
        msg = "已刷新五场景：" + "、".join(f"{k}={v}" for k, v in counts.items())
        try:
            self._log.setPlainText(msg)
        except RuntimeError:
            return
        self.report_status(msg)

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
        # 先让顶栏「业务」与侧栏画完，再刷事件/课表（Excel 查询放后台）
        # 从引擎切来时壳层已有 ~900ms delay；此处再错开一拍，避免与 WebEngine 拆解重叠
        self.report_status("班级日程提醒")
        QTimer.singleShot(80, self._on_enter_deferred)

    def _on_enter_deferred(self) -> None:
        import logging

        log = logging.getLogger("TOA3.schedule_reminder")
        log.debug(
            "schedule on_enter_deferred current_id=%s",
            getattr(self.window(), "_current_id", None) if self.window() else None,
        )
        if self.window() is not None and getattr(self.window(), "_current_id", None) != self.page_id:
            return
        self._reload_events()
        if not data_file_path().is_file():
            log.debug("schedule 无课表文件，跳过查询")
            return
        # 有缓存先画上，避免顶栏切业务时空转
        if self._scenes:
            self._apply_scenes(self._scenes, self._scene_mtime)
            self.report_status("课表（缓存）", level=StatusLevel.INFO)
        log.debug("schedule 开始 _reload_scenes force=False")
        self._reload_scenes(force=False)
