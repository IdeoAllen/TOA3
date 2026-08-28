# -*- coding: utf-8 -*-
"""无感开通/升级/续费：一处弹窗、一键完成。"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QVBoxLayout

from core.base_dialog import BaseDialog
from core.user_messages import show_error, show_success
from services.subscription_renew import fetch_renew_quote
from services.upgrade_flow import (
    UpgradeIntent,
    build_offer,
    primary_action_label,
    purchase_one_click,
    should_offer_purchase,
)
from widgets import DialogButtonRow, HintLabel, LineEdit, SemanticLabel


class _QuoteWorker(QObject):
    finished = Signal(bool, dict, str)

    def __init__(self, pack_id: str) -> None:
        super().__init__()
        self._pack_id = pack_id

    def run(self) -> None:
        ok, quote, err = fetch_renew_quote(self._pack_id)
        self.finished.emit(ok, quote or {}, err or "")


class _PurchaseWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, name: str, phone: str, pack_id: str) -> None:
        super().__init__()
        self._name = name
        self._phone = phone
        self._pack_id = pack_id

    def run(self) -> None:
        ok, msg = purchase_one_click(name=self._name, phone=self._phone, pack_id=self._pack_id)
        self.finished.emit(ok, msg)


class UpgradeOfferDialog(BaseDialog):
    dialog_kind = "small"

    def __init__(
        self,
        parent=None,
        *,
        module_id: str = "",
        reason: str = "",
    ) -> None:
        super().__init__(parent)
        self._offer = build_offer(module_id=module_id, reason=reason)
        self._intent: UpgradeIntent = self._offer["intent"]
        self._pack_id = str(self._offer["pack_id"])
        self._completed = False
        self._busy = False

        self.setWindowTitle(str(self._offer["window_title"]))
        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(SemanticLabel(str(self._offer["headline"]), kind="info"))
        root.addWidget(HintLabel("支付成功后立即生效，无需重启或粘贴授权码。"))

        self._quote = SemanticLabel("正在获取价格…", kind="info")
        root.addWidget(self._quote)

        self._phone = LineEdit()
        self._phone.setPlaceholderText("11 位手机号")
        phone = str(self._offer.get("phone") or "")
        if phone:
            self._phone.setText(phone)
            self._phone.hide()
        else:
            root.addWidget(HintLabel("首次开通需验证手机号"))
            root.addWidget(self._phone)

        self._actions = DialogButtonRow()
        self._btn_later = self._actions.add_secondary("稍后再说", self.reject)
        self._btn_more = self._actions.add_secondary("更多套餐", self._open_subscription)
        self._btn_pay = self._actions.add_primary("一键开通", self._on_pay)
        root.addWidget(self._actions)

        self._load_quote()

    @property
    def completed(self) -> bool:
        return self._completed

    def _load_quote(self) -> None:
        worker = _QuoteWorker(self._pack_id)
        worker.finished.connect(self._apply_quote)
        threading.Thread(target=worker.run, daemon=True).start()

    def _apply_quote(self, ok: bool, quote: dict, err: str) -> None:
        if self._busy:
            return
        pack_name = str(quote.get("pack_name") or self._pack_id)
        if not ok:
            self._quote.setText(f"{pack_name} · 请联网后重试")
            self._btn_pay.setEnabled(True)
            return
        days = int(quote.get("license_days") or 365)
        price = int(quote.get("price_yuan") or 0)
        self._quote.setText(f"{pack_name} · ¥{price} / {days} 天")
        self._btn_pay.setText(primary_action_label(intent=self._intent, price_yuan=price))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_pay.setEnabled(not busy)
        self._btn_later.setEnabled(not busy)
        self._btn_more.setEnabled(not busy)

    def _open_subscription(self) -> None:
        shell = self.parent()
        while shell is not None and not hasattr(shell, "navigate"):
            shell = shell.parent()
        if shell is not None and hasattr(shell, "open_subscription_settings"):
            shell.open_subscription_settings()
        elif shell is not None:
            shell.navigate("system_settings")
            page = getattr(shell, "_pages", {}).get("system_settings")
            if page is not None and hasattr(page, "open_license_or_subscription"):
                page.open_license_or_subscription()
        self.reject()

    def _on_pay(self) -> None:
        if self._busy:
            return
        name = str(self._offer.get("name") or "用户").strip() or "用户"
        phone = self._phone.text().strip() if self._phone.isVisible() else str(self._offer.get("phone") or "")
        if len(phone) != 11 or not phone.isdigit():
            show_error(self, "请填写 11 位手机号")
            if self._phone.isHidden():
                self._phone.show()
            return

        self._set_busy(True)
        self._btn_pay.setText("处理中…")
        worker = _PurchaseWorker(name, phone, self._pack_id)
        worker.finished.connect(self._on_paid)
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_paid(self, ok: bool, msg: str) -> None:
        self._set_busy(False)
        if not ok:
            show_error(self, msg or "开通失败，请检查网络后重试")
            self._load_quote()
            return
        self._completed = True
        if self._intent is UpgradeIntent.RENEW:
            show_success(self, "续费成功，已恢复使用。")
        else:
            show_success(self, "开通成功，正在进入功能…")
        self.accept()


_dialog_open = False


def offer_upgrade_for_module(
    parent,
    *,
    module_id: str = "",
    reason: str = "",
) -> bool:
    """弹出无感开通窗；成功返回 True。同一时刻只弹一次。"""
    global _dialog_open
    if _dialog_open:
        return False
    if not should_offer_purchase(reason=reason):
        return False
    _dialog_open = True
    try:
        dlg = UpgradeOfferDialog(parent, module_id=module_id, reason=reason)
        accepted = dlg.exec()
        return bool(accepted and dlg.completed)
    finally:
        _dialog_open = False
