# -*- coding: utf-8 -*-
"""系统设置 · Harness：仅安装路径与密钥，业务在 Harness Web。"""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.harness_credentials import masked_status, save_api_key
from services.harness_config import load_harness_config, save_harness_config
from services.harness_guide import PRODUCT_POSITION
from services.harness_setup import discover_runtime, init_dsh_home
from services.harness_sidecar import start
from services.harness_surface import set_surface_mode, surface_mode
from services.harness_task_runner import HarnessTaskRunner
from widgets import CheckBox, ComboBox, FormSection, HintLabel, LineEdit, PasswordLineEdit, PrimaryButton, SecondaryButton, SpinBox


class HarnessSection(QWidget):
    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._task_runner = HarnessTaskRunner(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(HintLabel(PRODUCT_POSITION))

        box = FormSection("Sidecar 路径（不含 Harness 业务配置）")
        cfg = load_harness_config()
        form = QFormLayout()

        self._enabled = CheckBox("启用编码智能体模块")
        self._enabled.setChecked(bool(cfg.get("enabled", True)))
        form.addRow("", self._enabled)

        self._dsh_home = LineEdit(str(cfg.get("dsh_home") or ""))
        form.addRow("DSH_HOME", self._dsh_home)

        self._node = LineEdit(str(cfg.get("node_exe") or ""))
        form.addRow("Node 路径", self._node)

        self._dsh_bin = LineEdit(str(cfg.get("dsh_bin") or ""))
        form.addRow("dsh bin.js", self._dsh_bin)

        self._api_key = PasswordLineEdit()
        self._api_key.setPlaceholderText("DeepSeek API Key（写入 DSH .credentials.yaml）")
        form.addRow("API Key", self._api_key)
        form.addRow("密钥状态", HintLabel(masked_status()))

        self._port = SpinBox()
        self._port.setRange(1024, 65535)
        self._port.setValue(int(cfg.get("web_port") or 3081))
        form.addRow("Web 端口", self._port)

        self._surface = ComboBox()
        self._surface.addItem("内嵌在套件内（默认）", "embed")
        self._surface.addItem("启动后优先系统浏览器", "browser")
        cur = surface_mode()
        self._surface.setCurrentIndex(0 if cur == "embed" else 1)
        form.addRow("显示方式", self._surface)

        self._auto = CheckBox("进页自动启动")
        self._auto.setChecked(bool(cfg.get("auto_start", True)))
        form.addRow("", self._auto)

        self._stop_exit = CheckBox("关闭 TOA3 时停止 Sidecar")
        self._stop_exit.setChecked(bool(cfg.get("stop_on_app_exit", False)))
        form.addRow("", self._stop_exit)

        box.add_layout(form)
        row = QHBoxLayout()
        btn_detect = SecondaryButton("自动检测")
        btn_detect.clicked.connect(self._auto_detect)
        row.addWidget(btn_detect)
        btn_save = PrimaryButton("保存")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        btn_start = SecondaryButton("测试启动")
        btn_start.clicked.connect(self._test_start)
        row.addWidget(btn_start)
        self._btn_test_start = btn_start
        btn_open = SecondaryButton("打开编码智能体")
        btn_open.clicked.connect(self._open_harness_page)
        row.addWidget(btn_open)
        box.add_layout(row)
        lay.addWidget(box)
        lay.addStretch(1)

    def _auto_detect(self) -> None:
        found = discover_runtime()
        if not found:
            show_warning(self, "未检测到环境。请在编码智能体页安装 dsh 或手填路径。")
            return
        if found.get("node_exe"):
            self._node.setText(found["node_exe"])
        if found.get("dsh_bin"):
            self._dsh_bin.setText(found["dsh_bin"])
        if found.get("dsh_home"):
            self._dsh_home.setText(found["dsh_home"])
        show_info(self, "已填入检测路径，点保存生效。")

    def _save(self) -> None:
        key = self._api_key.text().strip()
        if key:
            ok, msg = save_api_key(key)
            if not ok:
                show_warning(self, msg)
                return
            self._api_key.clear()
        from pathlib import Path

        home = self._dsh_home.text().strip()
        if home:
            init_dsh_home(Path(home))
        save_harness_config(
            {
                "enabled": self._enabled.isChecked(),
                "dsh_home": home,
                "node_exe": self._node.text().strip(),
                "dsh_bin": self._dsh_bin.text().strip(),
                "web_port": self._port.value(),
                "auto_start": self._auto.isChecked(),
                "stop_on_app_exit": self._stop_exit.isChecked(),
            }
        )
        set_surface_mode(str(self._surface.currentData() or "embed"))
        show_info(self, "已保存。工作区/插件请在 Harness Web 内配置。")
        self._page.report_status("Harness 路径已保存")

    def _test_start(self) -> None:
        if self._task_runner.is_running():
            show_warning(self, "测试启动进行中，请稍候。")
            return
        self._btn_test_start.setEnabled(False)
        self._page.report_status("正在测试启动 Harness…")

        def _done(ok: bool, payload) -> None:
            self._btn_test_start.setEnabled(True)
            if ok:
                success, msg = payload
                (show_info if success else show_warning)(self, msg)
                self._page.report_status(msg)
            else:
                show_warning(self, str(payload or "启动失败"))

        self._task_runner.run(start, on_done=_done)

    def _open_harness_page(self) -> None:
        win = self._page.window()
        if win is not None and hasattr(win, "navigate"):
            win.navigate("harness_agent")
