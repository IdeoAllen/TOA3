# -*- coding: utf-8 -*-
"""系统设置 · Harness Sidecar 配置。"""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.harness_config import load_harness_config, save_harness_config
from services.harness_sidecar import health_status, restart, start
from widgets import CheckBox, FormSection, HintLabel, LineEdit, PrimaryButton, SecondaryButton, SpinBox


class HarnessSection(QWidget):
    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(
            HintLabel(
                "DeepSeek Harness 为本地 Sidecar（dsh web），不走 integrations HTTP。"
                "API Key 由 DSH 自己的 .credentials.yaml 管理。"
            )
        )

        box = FormSection("Harness Sidecar")
        cfg = load_harness_config()
        form = QFormLayout()

        self._enabled = CheckBox("启用 Harness 智能体模块")
        self._enabled.setChecked(bool(cfg.get("enabled", True)))
        form.addRow("", self._enabled)

        self._dsh_home = LineEdit(str(cfg.get("dsh_home") or ""))
        form.addRow("DSH_HOME", self._dsh_home)

        self._node = LineEdit(str(cfg.get("node_exe") or ""))
        form.addRow("Node 路径", self._node)

        self._dsh_bin = LineEdit(str(cfg.get("dsh_bin") or ""))
        form.addRow("dsh bin.js", self._dsh_bin)

        self._port = SpinBox()
        self._port.setRange(1024, 65535)
        self._port.setValue(int(cfg.get("web_port") or 3081))
        form.addRow("Web 端口", self._port)

        self._dshm_port = SpinBox()
        self._dshm_port.setRange(1024, 65535)
        self._dshm_port.setValue(int(cfg.get("dshm_port") or 8787))
        form.addRow("dshm 端口", self._dshm_port)

        self._auto = CheckBox("进页自动启动（未运行时）")
        self._auto.setChecked(bool(cfg.get("auto_start", True)))
        form.addRow("", self._auto)

        self._stop_exit = CheckBox("关闭 TOA3 时停止 Sidecar")
        self._stop_exit.setChecked(bool(cfg.get("stop_on_app_exit", False)))
        form.addRow("", self._stop_exit)

        self._clear_key = CheckBox("启动前清除 DEEPSEEK_API_KEY 环境变量")
        self._clear_key.setChecked(bool(cfg.get("clear_env_api_key", True)))
        form.addRow("", self._clear_key)

        box.add_layout(form)
        row = QHBoxLayout()
        btn_save = PrimaryButton("保存 Harness 配置")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        btn_start = SecondaryButton("测试启动")
        btn_start.clicked.connect(self._test_start)
        row.addWidget(btn_start)
        btn_status = SecondaryButton("查看状态")
        btn_status.clicked.connect(self._show_status)
        row.addWidget(btn_status)
        btn_open = SecondaryButton("打开编码智能体页")
        btn_open.clicked.connect(self._open_harness_page)
        row.addWidget(btn_open)
        box.add_layout(row)
        lay.addWidget(box)
        lay.addStretch(1)

    def _save(self) -> None:
        save_harness_config(
            {
                "enabled": self._enabled.isChecked(),
                "dsh_home": self._dsh_home.text().strip(),
                "node_exe": self._node.text().strip(),
                "dsh_bin": self._dsh_bin.text().strip(),
                "web_port": self._port.value(),
                "dshm_port": self._dshm_port.value(),
                "auto_start": self._auto.isChecked(),
                "stop_on_app_exit": self._stop_exit.isChecked(),
                "clear_env_api_key": self._clear_key.isChecked(),
            }
        )
        show_info(self, "Harness 配置已保存到 data/user/harness.yml")
        self._page.report_status("Harness 配置已保存")

    def _test_start(self) -> None:
        def _run() -> None:
            ok, msg = start()
            if ok:
                show_info(self, msg)
            else:
                show_warning(self, msg)

        self._page.run_safe(_run, title="启动失败")

    def _show_status(self) -> None:
        st = health_status()
        lines = [
            f"运行：{'是' if st.get('running') else '否'}",
            f"TOA3 托管：{'是' if st.get('owned') else '否'}",
            f"外部实例：{'是' if st.get('external') else '否'}",
            f"URL：{st.get('url')}",
            f"端口占用：{'是' if st.get('port_busy') else '否'}",
            f"Node：{'就绪' if st.get('node_ok') else '缺失'}",
            f"dsh：{'就绪' if st.get('dsh_ok') else '缺失'}",
            f"DSH_HOME：{st.get('dsh_home')}",
        ]
        show_info(self, "\n".join(lines))

    def _open_harness_page(self) -> None:
        win = self._page.window()
        if win is not None and hasattr(win, "navigate"):
            win.navigate("harness_agent")
