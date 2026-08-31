# -*- coding: utf-8 -*-
"""系统设置 · 应用（版本、更新、关于、重启与退出）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_error, show_info
from services.product_vision import tagline
from services.system_info import get_system_info
from services.update_check import UpdateCheckResult, get_update_hub, open_download_page
from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton


class AppUpdateSection(QWidget):
    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._update_busy = False
        hub = get_update_hub()
        hub.checking_changed.connect(self._on_hub_checking)
        hub.result_ready.connect(self._on_hub_update_result)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        info = get_system_info()
        ver = FormSection("检查更新")
        ver.add_widget(
            HintLabel(f"{info.get('brand_name') or 'TOA'} · {tagline()}")
        )
        row = QHBoxLayout()
        self._btn_check = PrimaryButton("检查更新")
        self._btn_check.clicked.connect(self._on_check_update)
        row.addWidget(self._btn_check)
        btn_about = SecondaryButton("关于产品…")
        btn_about.clicked.connect(self._on_about)
        row.addWidget(btn_about)
        row.addStretch(1)
        ver.add_layout(row)
        outer.addWidget(ver)

        actions = FormSection("运行")
        actions.add_widget(
            HintLabel(
                "重启会拉起新进程；完全退出不进入托盘。"
                "快捷键：Ctrl+Shift+R 重启 · Ctrl+Q 退出。"
            )
        )
        row2 = QHBoxLayout()
        btn_restart = SecondaryButton("重启应用")
        btn_restart.clicked.connect(self._on_restart)
        row2.addWidget(btn_restart)
        btn_quit = SecondaryButton("完全退出")
        btn_quit.setProperty("class", "danger")
        btn_quit.clicked.connect(self._on_quit)
        row2.addWidget(btn_quit)
        row2.addStretch(1)
        actions.add_layout(row2)
        outer.addWidget(actions)

        outer.addWidget(
            HintLabel(
                "账号与退出见顶栏人像；管理员切换身份见本页「身份」。"
                "商业订单与发版见「运营台与商业 → 运营台」。"
            )
        )
        outer.addStretch(1)

    def _shell(self):
        w = self.window()
        return w if w is not None and hasattr(w, "_restart_app") else None

    def _on_about(self) -> None:
        shell = self._shell()
        if shell is not None and hasattr(shell, "_show_about"):
            shell._show_about()
            return
        show_error(self._page, "无法打开关于。")

    def _on_restart(self) -> None:
        shell = self._shell()
        if shell is not None:
            shell._restart_app()
            return
        show_error(self._page, "无法重启：未找到主窗口。")

    def _on_quit(self) -> None:
        shell = self._shell()
        if shell is not None:
            shell._quit_app()
            return
        show_error(self._page, "无法退出：未找到主窗口。")

    def _on_hub_checking(self, busy: bool) -> None:
        self._set_check_busy(busy)

    def _on_hub_update_result(self, result: object) -> None:
        if get_update_hub().last_reason() != "manual":
            return
        if not isinstance(result, UpdateCheckResult):
            show_error(self._page, "检查更新失败：返回无效", title="检查更新")
            return
        try:
            self._on_update_checked(result)
        except Exception as exc:
            show_error(self._page, f"检查更新失败：{exc}", title="检查更新")

    def _set_check_busy(self, busy: bool) -> None:
        self._update_busy = busy
        self._btn_check.setEnabled(not busy)
        self._btn_check.setText("检查中…" if busy else "检查更新")

    def _on_check_update(self) -> None:
        if self._update_busy:
            return
        get_update_hub().check_async(reason="manual")

    def _on_update_checked(self, result: UpdateCheckResult) -> None:
        if result.has_update and result.latest_version:
            notes = ""
            if result.release_notes:
                notes = f"\n\n{result.release_notes.strip()}"
            show_info(
                self._page,
                f"发现新版本 {result.latest_version}（当前 {result.current_version}）。"
                f"{notes}\n\n将打开下载页。",
                title="有可用更新",
            )
            open_download_page(result)
            return
        msg = f"当前版本 {result.current_version} 已是最新。"
        if result.source:
            src = "TOA 云服务" if result.source.startswith("toa") else result.source
            msg += f"\n（来源：{src}）"
        if result.error and result.source.startswith("local"):
            msg += f"\n\n提示：{result.error}"
        show_info(self._page, msg, title="检查更新")
