# -*- coding: utf-8 -*-
"""Hub · Harness 适配面板：视觉/交互对齐 Comfy LocalWebHost，不改 harness_agent 页。"""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import ask_confirm, show_info, show_saved, show_warning
from widgets import HintLabel, MenuButton, PrimaryButton, ProgressBar, SecondaryButton, SectionTitle


class HubHarnessHost(BasePage):
    """与 LocalWebHostPage 同构：门页 / 工具条 / 打开工作台 / 更多六件套。"""

    page_id = "engine_host_hub"
    page_title = "Harness Agent"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._visit_gen = 0
        self._status_known = False
        self._poll = QTimer(self)
        self._poll.setInterval(2500)
        self._poll.timeout.connect(self._refresh)

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(max(4, m[0] // 2), 4, max(4, m[2] // 2), 4)
        outer.setSpacing(2)

        self._header = SectionTitle("Harness Agent")
        self._header.setMaximumHeight(22)
        outer.addWidget(self._header)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._status = HintLabel("① 检测安装…")
        bar.addWidget(self._status, 1)

        self._action_stack = QStackedWidget()
        self._action_stack.setFixedHeight(32)
        self._btn_start = PrimaryButton("启动")
        self._btn_start.setMinimumWidth(72)
        self._btn_start.setMinimumHeight(32)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop = SecondaryButton("停止")
        self._btn_stop.setMinimumWidth(72)
        self._btn_stop.setMinimumHeight(32)
        self._btn_stop.clicked.connect(self._on_stop)
        self._action_stack.addWidget(self._btn_start)
        self._action_stack.addWidget(self._btn_stop)
        bar.addWidget(self._action_stack)

        self._btn_open_bench = PrimaryButton("打开工作台")
        self._btn_open_bench.setMinimumWidth(96)
        self._btn_open_bench.setMinimumHeight(32)
        self._btn_open_bench.setToolTip("在系统浏览器打开（与 Comfy 浏览器表面同构）")
        self._btn_open_bench.clicked.connect(self._on_open_workbench)
        bar.addWidget(self._btn_open_bench)

        self._btn_reload = SecondaryButton("刷新")
        self._btn_reload.setMinimumWidth(64)
        self._btn_reload.setMinimumHeight(32)
        self._btn_reload.clicked.connect(self._refresh)
        bar.addWidget(self._btn_reload)

        self._btn_more = MenuButton("更多")
        self._more_menu = QMenu(self)
        self._more_menu.addAction("打开日志", self._hub_open_logs)
        self._more_menu.addAction("一键修复", self._hub_repair)
        self._more_menu.addAction("版本备份", self._hub_backup)
        self._more_menu.addAction("一键卸载…", self._hub_uninstall)
        self._more_menu.addSeparator()
        self._more_menu.addAction("打开侧栏「编码智能体」", self._open_legacy_page)
        self._btn_more.setMenu(self._more_menu)
        self._btn_more.setMinimumWidth(64)
        self._btn_more.setMinimumHeight(32)
        bar.addWidget(self._btn_more)

        self._toolbar = QWidget()
        self._toolbar.setMinimumHeight(32)
        self._toolbar.setMaximumHeight(40)
        self._toolbar.setLayout(bar)
        self._toolbar.hide()
        outer.addWidget(self._toolbar)

        self._body = QStackedWidget()
        gate = QWidget()
        gate_lay = QVBoxLayout(gate)
        gate_lay.setContentsMargins(24, 16, 24, 16)
        gate_lay.setSpacing(12)
        gate_lay.addStretch(1)
        self._gate_title = HintLabel("① 正在检测安装…")
        self._gate_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lay.addWidget(self._gate_title)
        self._gate_body = HintLabel("请稍候…")
        self._gate_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gate_body.setWordWrap(True)
        gate_lay.addWidget(self._gate_body)
        self._progress = ProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setMaximumHeight(10)
        gate_lay.addWidget(self._progress, 0, Qt.AlignmentFlag.AlignHCenter)
        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_install = PrimaryButton("一键安装")
        self._btn_install.clicked.connect(self._on_install)
        self._btn_install.hide()
        row.addWidget(self._btn_install)
        row.addStretch(1)
        gate_lay.addLayout(row)
        gate_lay.addStretch(2)
        self._body.addWidget(gate)

        work = QWidget()
        wlay = QVBoxLayout(work)
        wlay.setContentsMargins(16, 12, 16, 12)
        self._work_hint = QLabel()
        self._work_hint.setObjectName("LocalWebHostPlaceholder")
        self._work_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._work_hint.setWordWrap(True)
        self._work_hint.setText("服务就绪后点「打开工作台」在浏览器干活。\n完整会话页仍在侧栏「编码智能体」（未改写）。")
        wlay.addStretch(1)
        wlay.addWidget(self._work_hint)
        wlay.addStretch(2)
        self._body.addWidget(work)
        outer.addWidget(self._body, 1)

    def on_enter(self) -> None:
        self._visit_gen += 1
        self.report_status("Harness · 管家适配", level=StatusLevel.INFO)
        self._set_detecting(True)
        QTimer.singleShot(40, self._refresh)
        self._poll.start()

    def on_leave(self) -> None:
        self._visit_gen += 1
        self._poll.stop()

    def soft_leave(self) -> None:
        self.on_leave()

    def _set_detecting(self, detecting: bool) -> None:
        self._status_known = not detecting
        if detecting:
            self._toolbar.hide()
            self._body.setCurrentIndex(0)
            self._gate_title.setText("① 正在检测安装…")
            self._btn_install.hide()
            self._progress.show()
            self._progress.setRange(0, 0)
        else:
            self._toolbar.show()
            self._progress.hide()

    def _refresh(self) -> None:
        try:
            from services import harness_sidecar
            from services.harness_setup import discover_runtime

            rt = discover_runtime()
            installed = bool(rt.get("dsh") and rt.get("node"))
            running = bool(harness_sidecar.is_running(timeout=0.5))
        except Exception as exc:
            self._status.setText(f"检测失败：{exc}")
            self._set_detecting(False)
            self._body.setCurrentIndex(0)
            self._gate_title.setText("无法检测 Harness")
            self._gate_body.setText(str(exc))
            self._btn_install.show()
            return

        self._set_detecting(False)
        if not installed:
            self._body.setCurrentIndex(0)
            self._gate_title.setText("未安装 Harness 运行时")
            self._gate_body.setText("一键安装后即可启动，并在浏览器打开工作台。")
            self._btn_install.show()
            self._status.setText("未安装")
            self._action_stack.setCurrentIndex(0)
            self._btn_start.setEnabled(False)
            return

        self._body.setCurrentIndex(1)
        self._btn_install.hide()
        self._btn_start.setEnabled(True)
        if running:
            self._action_stack.setCurrentIndex(1)
            self._status.setText("运行中 · 点「打开工作台」")
            self._work_hint.setText("服务已在运行。\n主路径：打开工作台（系统浏览器）。")
        else:
            self._action_stack.setCurrentIndex(0)
            self._status.setText("已安装 · 未启动")
            self._work_hint.setText("已安装。点「启动」后「打开工作台」。")

    def _on_install(self) -> None:
        from services.harness_setup import install_harness_runtime

        self.report_status("正在安装…", level=StatusLevel.INFO)
        ok, msg = install_harness_runtime()
        if ok:
            show_info(self, msg or "安装完成")
            self._refresh()
        else:
            show_warning(self, msg or "安装失败")

    def _on_start(self) -> None:
        from services import harness_sidecar

        self.report_status("正在启动…", level=StatusLevel.INFO)
        ok, msg = harness_sidecar.start(wait_ready=True)
        if ok:
            self.report_status("已启动", level=StatusLevel.SUCCESS)
        else:
            show_warning(self, msg or "启动失败")
        self._refresh()

    def _on_stop(self) -> None:
        from services import harness_sidecar

        ok, msg = harness_sidecar.stop(force=False)
        self.report_status(msg or ("已停止" if ok else "停止失败"), level=StatusLevel.INFO)
        self._refresh()

    def _on_open_workbench(self) -> None:
        from services.harness_surface import open_in_system_browser

        url = open_in_system_browser()
        if url:
            self.report_status("已在浏览器打开", level=StatusLevel.SUCCESS)
        else:
            show_warning(self, "无法打开浏览器，请先启动服务")

    def _hub_open_logs(self) -> None:
        from services.engine_host.lifecycle import open_log

        ok, msg, path = open_log("harness_agent")
        if not ok or path is None:
            show_warning(self, msg)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        show_info(self, msg)

    def _hub_repair(self) -> None:
        from services.engine_host.lifecycle import repair_engine

        ok, msg = repair_engine("harness_agent")
        if ok:
            show_info(self, msg)
            self._refresh()
        else:
            show_warning(self, msg)

    def _hub_backup(self) -> None:
        from services.engine_host.lifecycle import backup_engine

        ok, msg, path = backup_engine("harness_agent")
        if ok and path:
            show_saved(self, msg, path)
        else:
            show_warning(self, msg)

    def _hub_uninstall(self) -> None:
        from services.engine_host.lifecycle import uninstall_engine

        if not ask_confirm(self, "卸载 Harness 运行时登记？将停止服务。", title="一键卸载"):
            return
        delete_files = ask_confirm(self, "是否删除安装目录文件？", title="删除文件")
        ok, msg = uninstall_engine("harness_agent", delete_files=delete_files)
        if ok:
            show_info(self, msg)
            self._refresh()
        else:
            show_warning(self, msg)

    def _open_legacy_page(self) -> None:
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            shell.navigate("harness_agent")
            return
        if shell is not None and hasattr(shell, "_summon_module"):
            shell._summon_module("harness_agent")
            return
        show_info(self, "请到侧栏打开「编码智能体」（该页未改写）。")
