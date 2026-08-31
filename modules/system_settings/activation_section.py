# -*- coding: utf-8 -*-
"""系统设置 · 一键开通 + 可选授权码激活。"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.exceptions import AuthError
from core.base_page import BasePage
from core.user_messages import show_error, show_info, show_success, show_warning
from services.commerce_profile import merge_buyer_profile
from services.commerce_urls import open_admin_purchase_page
from services.license_manager import global_license_manager
from services.subscription_renew import _DEFAULT_PACK, fetch_renew_quote
from services.upgrade_flow import primary_action_label, purchase_pack
from widgets import FormSection, HintLabel, LineEdit, PasswordLineEdit, PrimaryButton, SecondaryButton, SemanticLabel


class _QuoteWorker(QObject):
    finished = Signal(bool, dict)

    def __init__(self, pack_id: str) -> None:
        super().__init__()
        self._pack_id = pack_id

    def run(self) -> None:
        ok, quote, _ = fetch_renew_quote(self._pack_id)
        self.finished.emit(ok, quote or {})


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


class _PurchaseWorker(QObject):
    finished = Signal(bool, str, object)

    def __init__(self, pack_id: str, name: str, phone: str) -> None:
        super().__init__()
        self._pack_id = pack_id
        self._name = name
        self._phone = phone

    def run(self) -> None:
        ok, msg, meta = purchase_pack(pack_id=self._pack_id, name=self._name, phone=self._phone)
        self.finished.emit(ok, msg, meta)


class ActivationSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("一键开通")
        self._page = parent
        self._lm = global_license_manager
        self._thread: QThread | None = None
        self._worker: _ActivateWorker | None = None
        self._busy = False
        self._profile = merge_buyer_profile()
        self._pack_id = _DEFAULT_PACK
        self._show_code_form = False

        self._status = SemanticLabel("", kind="info")
        self.add_widget(self._status)
        self.add_widget(
            HintLabel(
                "当前为试用版：填手机号后在此升级正式版；离线体验时长见 config/app.yml license.standalone_experience_days。"
                "外部支付后点「同步已付订单」。"
            )
        )

        self._quote = SemanticLabel("正在获取推荐产品方案…", kind="info")
        self.add_widget(self._quote)

        self._phone = LineEdit()
        self._phone.setPlaceholderText("购买 / 试用时填写 11 位手机号")
        phone = str(self._profile.get("phone") or "")
        if phone:
            self._phone.setText(phone)
        self.add_widget(self._phone)

        row = QHBoxLayout()
        self._btn_trial = SecondaryButton("下载试用")
        self._btn_trial.clicked.connect(self._on_trial)
        row.addWidget(self._btn_trial)
        self._btn_buy = PrimaryButton("购买 / 续费")
        self._btn_buy.clicked.connect(self._on_one_click)
        row.addWidget(self._btn_buy)
        self._btn_portal = SecondaryButton("打开运营台")
        self._btn_portal.clicked.connect(self._on_open_portal)
        row.addWidget(self._btn_portal)
        self._btn_code = SecondaryButton("更换授权码")
        self._btn_code.clicked.connect(self._toggle_code_form)
        row.addWidget(self._btn_code)
        row.addStretch(1)
        self.add_layout(row)

        self._code_panel = QWidget()
        code_lay = QVBoxLayout(self._code_panel)
        code_lay.setContentsMargins(0, 8, 0, 0)
        code_lay.addWidget(HintLabel("粘贴运营台签发的授权码，联网激活。"))
        form = QFormLayout()
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("TOA 授权码")
        form.addRow("授权码", self._key)
        code_lay.addLayout(form)
        code_row = QHBoxLayout()
        self._btn_activate = SecondaryButton("联网激活")
        self._btn_activate.clicked.connect(self._on_activate)
        code_row.addWidget(self._btn_activate)
        code_row.addStretch(1)
        code_lay.addLayout(code_row)
        self.add_widget(self._code_panel)
        self._code_panel.setVisible(self._show_code_form)

        self.refresh_status()
        self._load_quote()

    def _scroll_to_more_packs(self) -> None:
        from core.user_messages import show_info

        show_info(self._page, "请向下滚动，在「全部产品方案」区选择其它方案。")

    def _toggle_code_form(self) -> None:
        self._show_code_form = not self._show_code_form
        self._code_panel.setVisible(self._show_code_form)
        self._btn_code.setText("收起授权码" if self._show_code_form else "更换授权码")

    def _on_trial(self) -> None:
        if self._busy:
            return
        phone = self._buyer_phone()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._page, "下载试用请填写 11 位手机号")
            return
        name = str(self._profile.get("name") or "用户").strip() or "用户"
        self._set_busy(True)
        self._page.report_status("正在申请试用…")

        def work():
            from services.auth_service import authenticate_trial

            try:
                session = authenticate_trial(phone, display_name=name)
                return True, "", session
            except AuthError as e:
                return False, str(e), None

        def done(ok: bool, err: str, session: object) -> None:
            self._set_busy(False)
            if not ok:
                show_error(self._page, err or "试用申请失败")
                return
            from app.app_state import AppState
            from services.notify_bus import emit_license_changed

            sess = session if isinstance(session, dict) else {}
            uname = str(sess.get("display_name") or name)
            AppState.get().set_user(uname, uname, role=str(sess.get("role") or "user"))
            emit_license_changed()
            self.refresh_status()
            show_success(self._page, "试用已开通，请查看顶栏有效期。")
            self._page.report_status("试用已激活")

        import threading

        def runner():
            try:
                ok, err, session = work()
            except Exception as e:
                ok, err, session = False, str(e), None
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda: done(ok, err, session))

        threading.Thread(target=runner, daemon=True).start()

    def _on_open_portal(self) -> None:
        pack_id = self._pack_id or _DEFAULT_PACK
        if open_admin_purchase_page(plan_id=pack_id):
            show_info(self._page, "已在浏览器打开运营台产品方案页。")
            self._page.report_status("已打开运营台")
        else:
            show_warning(self._page, "无法打开浏览器，请手动访问运营台。")

    def refresh_status(self) -> None:
        text = self._lm.get_validity_text() or "—"
        licensed = self._lm.is_licensed()
        kind = "success" if licensed else ("info" if self._lm.is_standalone_mode() else "warning")
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.setText(f"当前：{text}")
        self._set_busy(self._busy)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_buy.setEnabled(not busy)
        self._btn_trial.setEnabled(not busy)
        self._btn_portal.setEnabled(not busy)
        self._btn_code.setEnabled(not busy)
        self._btn_activate.setEnabled(not busy)
        self._key.setEnabled(not busy)
        self._phone.setEnabled(not busy)
        if busy:
            self._btn_buy.setText("处理中…")
            self._btn_trial.setText("申请中…")
        elif not self._busy:
            self._btn_buy.setText("购买 / 续费")
            self._btn_trial.setText("下载试用")
            self._load_quote()

    def _load_quote(self) -> None:
        if self._busy:
            return
        pack_id = self._pack_id or _DEFAULT_PACK
        worker = _QuoteWorker(pack_id)
        worker.finished.connect(self._apply_quote)
        threading.Thread(target=worker.run, daemon=True).start()

    def _apply_quote(self, ok: bool, quote: dict) -> None:
        if self._busy:
            return
        pack_id = self._pack_id or _DEFAULT_PACK
        if not ok:
            self._quote.setText("推荐产品方案 · 请联网后重试")
            self._btn_buy.setText("一键开通")
            return
        name = str(quote.get("plan_name") or quote.get("pack_name") or pack_id)
        price = int(quote.get("price_yuan") or 0)
        days = int(quote.get("validity_days") or quote.get("license_days") or 365)
        self._quote.setText(f"推荐 {name} · ¥{price} / {days} 天")
        self._btn_buy.setText(primary_action_label(price_yuan=price))

    def _buyer_phone(self) -> str:
        return self._phone.text().strip() or str(self._profile.get("phone") or "").strip()

    def _on_one_click(self) -> None:
        if self._busy:
            return
        phone = self._buyer_phone()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._page, "购买 / 续费请填写 11 位手机号")
            return
        name = str(self._profile.get("name") or "用户").strip() or "用户"
        self._set_busy(True)
        self._page.report_status("正在开通…")

        worker = _PurchaseWorker(self._pack_id, name, phone)
        worker.finished.connect(self._on_purchase_done)
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_purchase_done(self, ok: bool, msg: str, meta: object) -> None:
        self._set_busy(False)
        if not ok:
            data = meta if isinstance(meta, dict) else {}
            if data.get("pending_payment"):
                show_warning(self._page, msg or "请在 Portal 完成支付后重试，或联系管理员。")
            else:
                show_error(self._page, msg or "开通失败")
            self._page.report_status("开通失败")
            return
        self._profile = merge_buyer_profile()
        self.refresh_status()
        from app.app_state import AppState
        from services.notify_bus import emit_license_changed

        info = self._lm.get_license_info()
        uname = str(info.get("user_name") or self._profile.get("name") or "用户").strip() or "用户"
        AppState.get().set_user(uname, uname, role=str(info.get("role") or "user"))
        emit_license_changed()
        show_success(self._page, "开通成功，已刷新授权。")
        self._page.report_status("已切换为网络授权版")

    def _on_activate(self) -> None:
        if self._busy:
            return
        key = self._key.text().strip().replace(" ", "")
        if not key or key.startswith("[") or "粘贴" in key:
            show_warning(self._page, "请粘贴 TOA 运营台签发的完整授权码（勿用占位提示文字）。")
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
        name = str((payload or {}).get("name") or "用户")
        role = str((payload or {}).get("role") or "user")
        from app.app_state import AppState
        from services.notify_bus import emit_license_changed

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
