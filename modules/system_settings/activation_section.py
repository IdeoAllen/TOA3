# -*- coding: utf-8 -*-
"""系统设置 · 单机升级 / 授权码联网激活。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout

from core.base_page import BasePage
from core.user_messages import show_error, show_success, show_warning
from services.license_manager import global_license_manager
from services.notify_bus import emit_license_changed
from widgets import FormSection, HintLabel, LineEdit, PasswordLineEdit, PrimaryButton, SecondaryButton, SemanticLabel


class _ActivateWorker(QObject):
    finished = Signal(bool, str, object)

    def __init__(self, license_key: str) -> None:
        super().__init__()
        self._key = license_key

    def run(self) -> None:
        try:
            ok, msg, payload = global_license_manager.activate_with_code(self._key)
            self.finished.emit(bool(ok), str(msg or ""), payload)
        except Exception as exc:
            self.finished.emit(False, str(exc), None)


class ActivationSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("升级完整版（联网激活）")
        self._page = parent
        self._lm = global_license_manager
        self._thread: QThread | None = None
        self._worker: _ActivateWorker | None = None
        self._busy = False

        self._status = SemanticLabel("", kind="info")
        self.add_widget(self._status)
        self.add_widget(
            HintLabel(
                "单机基础版可离线使用部分办公工具。"
                "粘贴 TOA 运营台签发的授权码并联网激活后，将切换为完整网络版。"
                "获取授权码：https://toa-service.yczh.tech/admin/"
            )
        )

        form = QFormLayout()
        self._display = LineEdit()
        self._display.setPlaceholderText("可选，以授权码登记姓名为准")
        info = self._lm.get_license_info()
        self._display.setText(str(info.get("user_name") or "").strip())
        form.addRow("显示名", self._display)

        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("TOA 授权码")
        form.addRow("授权码", self._key)
        self.add_layout(form)

        row = QHBoxLayout()
        self._btn_activate = PrimaryButton("联网激活")
        self._btn_activate.clicked.connect(self._on_activate)
        row.addWidget(self._btn_activate)
        self._btn_sub = SecondaryButton("订阅购买")
        self._btn_sub.clicked.connect(self._open_subscription)
        row.addWidget(self._btn_sub)
        row.addStretch(1)
        self.add_layout(row)

        self.refresh_status()

    def refresh_status(self) -> None:
        text = self._lm.get_validity_text() or "—"
        licensed = self._lm.is_licensed()
        kind = "success" if licensed else ("info" if self._lm.is_standalone_mode() else "warning")
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.setText(f"当前：{text}")

        from services.settings_access import subscription_tab_visible

        self._btn_sub.setVisible(subscription_tab_visible())
        self._set_busy(self._busy)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_activate.setEnabled(not busy)
        self._btn_activate.setText("激活中…" if busy else "联网激活")
        self._key.setEnabled(not busy)

    def _open_subscription(self) -> None:
        page = self._page
        if hasattr(page, "open_subscription_tab"):
            page.open_subscription_tab()

    def _on_activate(self) -> None:
        if self._busy:
            return
        key = self._key.text().strip().replace(" ", "")
        if not key:
            show_warning(self._page, "请粘贴 TOA 运营台签发的完整授权码。")
            return
        if self._thread is not None and self._thread.isRunning():
            show_warning(self._page, "正在联网激活，请稍候。")
            return

        self._set_busy(True)
        self._page.report_status("正在联网激活…")

        self._thread = QThread(self)
        self._worker = _ActivateWorker(key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_activate_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_activate_done(self, ok: bool, msg: str, payload: object) -> None:
        self._set_busy(False)
        if not ok:
            show_error(self._page, msg or "激活失败", title="联网激活失败")
            self._page.report_status("联网激活失败")
            return
        name = str((payload or {}).get("name") or self._display.text().strip() or "用户")
        role = str((payload or {}).get("role") or "user")
        from app.app_state import AppState

        AppState.get().set_user(name, name, role=role)
        emit_license_changed()
        self._key.clear()
        self.refresh_status()
        show_success(self._page, msg or "授权激活成功", title="激活完成")
        self._page.report_status("已切换为网络授权版")

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
