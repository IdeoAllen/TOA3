# -*- coding: utf-8 -*-
"""到期续费弹窗：一键支付并恢复使用。"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QVBoxLayout

from core.base_dialog import BaseDialog
from core.user_messages import show_error, show_success
from services.subscription_renew import fetch_renew_quote, is_renewable_block, renew_one_click, renew_profile
from widgets import DialogButtonRow, HintLabel, LineEdit, SemanticLabel


class _QuoteWorker(QObject):
    finished = Signal(bool, dict, str)

    def __init__(self, pack_id: str) -> None:
        super().__init__()
        self._pack_id = pack_id

    def run(self) -> None:
        ok, quote, err = fetch_renew_quote(self._pack_id)
        self.finished.emit(ok, quote or {}, err or "")


class _RenewWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, name: str, phone: str, pack_id: str) -> None:
        super().__init__()
        self._name = name
        self._phone = phone
        self._pack_id = pack_id

    def run(self) -> None:
        ok, msg = renew_one_click(name=self._name, phone=self._phone, pack_id=self._pack_id)
        self.finished.emit(ok, msg)


class RenewDialog(BaseDialog):
    dialog_kind = "small"

    def __init__(self, parent=None, *, message: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("续费订阅")
        self._renewed = False
        self._busy = False
        self._profile = renew_profile()
        self._pack_id = self._profile["pack_id"]

        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(SemanticLabel("订阅已到期", kind="warning"))
        root.addWidget(HintLabel(message.strip() or "续费后立即恢复，无需重启。"))

        self._quote = SemanticLabel(
            f"续费 {self._profile.get('pack_name', self._pack_id)} · 加载价格…",
            kind="info",
        )
        root.addWidget(self._quote)

        self._phone = LineEdit()
        self._phone.setPlaceholderText("11 位手机号")
        if self._profile.get("phone"):
            self._phone.setText(self._profile["phone"])
            self._phone.hide()
        else:
            root.addWidget(HintLabel("请填写手机号完成续费"))
            root.addWidget(self._phone)

        self._actions = DialogButtonRow()
        self._btn_later = self._actions.add_secondary("稍后再说", self.reject)
        self._btn_pay = self._actions.add_primary("立即续费", self._on_pay)
        root.addWidget(self._actions)

        self._load_quote()

    @property
    def renewed(self) -> bool:
        return self._renewed

    def _load_quote(self) -> None:
        worker = _QuoteWorker(self._pack_id)
        worker.finished.connect(self._apply_quote)
        threading.Thread(target=worker.run, daemon=True).start()

    def _apply_quote(self, ok: bool, quote: dict, err: str) -> None:
        if self._busy:
            return
        if not ok:
            self._quote.setText(f"{self._profile.get('pack_name', self._pack_id)} · 请联网续费")
            return
        days = int(quote.get("license_days") or 365)
        price = int(quote.get("price_yuan") or 0)
        name = str(quote.get("pack_name") or self._pack_id)
        self._quote.setText(f"续费 {name} · ¥{price} / {days} 天")
        self._btn_pay.setText(f"立即续费 ¥{price}")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_pay.setEnabled(not busy)
        self._btn_later.setEnabled(not busy)

    def _on_pay(self) -> None:
        if self._busy:
            return
        name = str(self._profile.get("name") or "用户").strip() or "用户"
        phone = self._phone.text().strip() if self._phone.isVisible() else str(self._profile.get("phone") or "")
        if len(phone) != 11 or not phone.isdigit():
            show_error(self, "请填写 11 位手机号")
            if self._phone.isHidden():
                self._phone.show()
            return

        self._set_busy(True)
        self._btn_pay.setText("支付中…")
        worker = _RenewWorker(name, phone, self._pack_id)
        worker.finished.connect(self._on_paid)
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_paid(self, ok: bool, msg: str) -> None:
        self._set_busy(False)
        if not ok:
            show_error(self, msg or "续费失败，请检查网络")
            self._btn_pay.setText("立即续费")
            return
        self._renewed = True
        show_success(self, f"续费成功\n\n{msg}")
        self.accept()


_dialog_open = False


def offer_renew_dialog(parent, *, message: str = "", reason: str = "") -> bool:
    """弹出续费窗；成功返回 True。同一时刻只弹一次。"""
    global _dialog_open
    if _dialog_open:
        return False
    if reason and not is_renewable_block(reason):
        return False
    _dialog_open = True
    try:
        dlg = RenewDialog(parent, message=message or reason)
        accepted = dlg.exec()
        return bool(accepted and dlg.renewed)
    finally:
        _dialog_open = False
