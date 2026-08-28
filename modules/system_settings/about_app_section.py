# -*- coding: utf-8 -*-
"""系统设置 · 关于与应用（版本、更新、重启、退出）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.dialog_chrome import make_info_form, value_label
from core.base_page import BasePage
from core.user_messages import show_error, show_info
from services.icon_registry import brand_logo_pixmap
from services.product_vision import tagline, vision_home_rows
from services.system_info import get_system_info, logo_path
from services.update_check import UpdateCheckResult, get_update_hub, open_download_page
from widgets import FormSection, HintLabel, PrimaryButton, SecondaryButton


class AboutAppSection(QWidget):
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
        hero = FormSection("产品")
        row = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(72, 72)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if logo_path() is not None:
            pix = brand_logo_pixmap(64, 64, parent=self)
            if not pix.isNull():
                logo.setPixmap(pix)
        else:
            logo.setText("Logo")
        row.addWidget(logo)
        title = QLabel(str(info.get("brand_name") or "运营宝"))
        title.setObjectName("PageTitle")
        sub = QLabel(tagline())
        sub.setObjectName("HintLabel")
        text_col = QVBoxLayout()
        text_col.addWidget(title)
        text_col.addWidget(sub)
        row.addLayout(text_col)
        row.addStretch(1)
        hero.add_layout(row)
        outer.addWidget(hero)

        vision_rows = vision_home_rows()
        if vision_rows:
            box = FormSection("使命 · 愿景 · 目标")
            form = make_info_form()
            for label, text in vision_rows:
                form.addRow(label, value_label(str(text)))
            wrap = QWidget()
            wrap.setLayout(form)
            box.add_widget(wrap)
            outer.addWidget(box)

        meta = FormSection("版本信息")
        form = make_info_form()
        form.addRow("版本", value_label(str(info.get("app_version") or "—")))
        form.addRow("发行", value_label(str(info.get("build_profile") or "—")))
        form.addRow("产品", value_label(str(info.get("app_name") or "—")))
        form.addRow("作者", value_label(str(info.get("author") or "—")))
        email = str(info.get("author_email") or "").strip()
        form.addRow(
            "联系",
            value_label(email or "—", selectable=bool(email)),
        )
        try:
            from services.license_manager import global_license_manager

            form.addRow(
                "机器 ID",
                value_label(global_license_manager.get_machine_id(), selectable=True),
            )
        except Exception:
            pass
        wrap_meta = QWidget()
        wrap_meta.setLayout(form)
        meta.add_widget(wrap_meta)
        outer.addWidget(meta)

        actions = FormSection("应用")
        actions.add_widget(
            HintLabel(
                "重启会拉起新进程并结束当前实例；完全退出不进入托盘。"
                "快捷键：Ctrl+Shift+R 重启 · Ctrl+Q 退出。"
            )
        )
        row = QHBoxLayout()
        self._btn_check = SecondaryButton("检查更新")
        self._btn_check.clicked.connect(self._on_check_update)
        row.addWidget(self._btn_check)
        btn_restart = SecondaryButton("重启应用")
        btn_restart.clicked.connect(self._on_restart)
        row.addWidget(btn_restart)
        btn_quit = PrimaryButton("完全退出")
        btn_quit.setProperty("class", "danger")
        btn_quit.clicked.connect(self._on_quit)
        row.addWidget(btn_quit)
        row.addStretch(1)
        actions.add_layout(row)
        outer.addWidget(actions)

        from services.settings_access import is_settings_admin

        if is_settings_admin():
            outer.addWidget(
                HintLabel("日志与连通诊断见「运行诊断」页签；品牌文案见「品牌定制」。")
            )
        else:
            outer.addWidget(
                HintLabel(
                    "未授权：请前往「激活与订阅」页粘贴授权码并联网激活。"
                    "AI Key 见「模型与 AI」。"
                )
            )

        outer.addStretch(1)

    def _shell(self):
        w = self.window()
        return w if w is not None and hasattr(w, "_restart_app") else None

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

    def set_update_check_busy(self, busy: bool) -> None:
        self._set_check_busy(busy)

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
