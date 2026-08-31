# -*- coding: utf-8 -*-
"""终端购买面板：选套餐 · 手机号 · 一键开通（与设置页共用）。"""
from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.user_messages import show_error, show_success, show_warning
from services.commerce_client import list_sellable_packs
from services.commerce_profile import merge_buyer_profile
from services.license_manager import global_license_manager
from services.upgrade_flow import primary_action_label, submit_purchase_request, sync_paid_order
from widgets import ComboBox, HintLabel, LineEdit, PrimaryButton, ReadOnlyPlainTextEdit, SecondaryButton

_NETWORK_PACK_TIMEOUT_S = 6.0
_LOAD_WATCHDOG_MS = 8000


def _local_sellable_packs() -> list[dict]:
    """运营台不可达时回退到本机 feature_packs 可售方案。"""
    try:
        from services.feature_packs import list_packs

        rows = list_packs(sellable_only=True)
    except Exception:
        rows = []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "").strip()
        if not pid:
            continue
        out.append(
            {
                "plan_id": pid,
                "id": pid,
                "name": str(row.get("name") or pid),
                "desc": str(row.get("desc") or ""),
                "price_yuan": int(row.get("price_yuan") or 0),
                "validity_days": int(row.get("validity_days") or 365),
                "menu_ids": list(row.get("features") or []),
            }
        )
    return out


def _fetch_remote_packs():
    ok, packs, _commerce, err = list_sellable_packs(timeout=_NETWORK_PACK_TIMEOUT_S)
    if ok and packs:
        return True, "", packs
    return False, err or "无法连接运营台", None


class CommercePurchasePanel(QWidget):
    """终端用户购买/续费：不依赖系统设置页。"""

    completed = Signal()
    _async_result = Signal(bool, str, object, int)

    def __init__(self, parent=None, *, show_portal: bool = False) -> None:
        super().__init__(parent)
        self._host = parent
        self._lm = global_license_manager
        self._packs: list[dict] = []
        self._loading_packs = False
        self._submitting = False
        self._load_token = 0
        self._load_watchdog: QTimer | None = None
        self._profile = merge_buyer_profile()
        self._async_callbacks: dict[int, Callable[[bool, str, object], None]] = {}
        self._async_cb_seq = 0
        self._pending_order_no = str(global_license_manager.get_license_info().get("last_order_no") or "")
        self._async_result.connect(self._dispatch_async_result)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        form = QFormLayout()
        self._pack_combo = ComboBox()
        self._pack_combo.currentIndexChanged.connect(self._on_pack_changed)
        form.addRow("产品套餐", self._pack_combo)

        self._phone = LineEdit()
        self._phone.setPlaceholderText("11 位手机号")
        phone = str(self._profile.get("phone") or "")
        if phone:
            self._phone.setText(phone)
        form.addRow("手机号", self._phone)

        self._detail = ReadOnlyPlainTextEdit()
        self._detail.setMinimumHeight(72)
        self._detail.setMaximumHeight(96)
        form.addRow("套餐说明", self._detail)
        lay.addLayout(form)

        lay.addWidget(
            HintLabel("选择套餐并填写手机号，申请将提交至运营台；确认后在此同步授权，无需在客户端支付。")
        )

        row = QHBoxLayout()
        self._btn_buy = PrimaryButton("提交开通申请")
        self._btn_buy.clicked.connect(self._on_buy)
        row.addWidget(self._btn_buy)
        self._btn_reload = SecondaryButton("刷新方案")
        self._btn_reload.clicked.connect(self._load_packs)
        row.addWidget(self._btn_reload)
        if show_portal:
            self._btn_portal = SecondaryButton("打开运营台")
            self._btn_portal.clicked.connect(self._on_open_portal)
            row.addWidget(self._btn_portal)
        row.addStretch(1)
        lay.addLayout(row)

        adv = QHBoxLayout()
        self._btn_sync = SecondaryButton("同步授权")
        self._btn_sync.clicked.connect(self._on_sync_paid)
        adv.addWidget(self._btn_sync)
        adv.addWidget(HintLabel("运营台确认订单后，填写手机号并同步授权"))
        adv.addStretch(1)
        lay.addLayout(adv)

        self._load_packs()

    def _on_open_portal(self) -> None:
        from services.commerce_urls import open_admin_purchase_page

        pack = self._selected_pack()
        plan_id = str(pack.get("plan_id") or pack.get("id") or "") if pack else ""
        open_admin_purchase_page(plan_id=plan_id)

    def refresh(self) -> None:
        """弹窗再次聚焦时恢复可操作态并刷新方案列表。"""
        self._set_submitting(False)
        self._load_token += 1
        if self._load_watchdog is not None:
            self._load_watchdog.stop()
        self._set_loading_packs(False)
        self._load_packs()

    def _set_loading_packs(self, loading: bool) -> None:
        self._loading_packs = loading
        self._btn_reload.setEnabled(not loading and not self._submitting)
        self._btn_reload.setText("加载中…" if loading else "刷新方案")
        self._btn_buy.setEnabled(not self._submitting and bool(self._packs))
        if not loading and not self._submitting:
            self._pack_combo.setEnabled(True)
            self._phone.setEnabled(True)

    def _set_submitting(self, submitting: bool) -> None:
        self._submitting = submitting
        self._btn_buy.setEnabled(not submitting and bool(self._packs))
        self._pack_combo.setEnabled(not submitting)
        self._phone.setEnabled(not submitting)
        self._btn_sync.setEnabled(not submitting)
        self._btn_reload.setEnabled(not submitting and not self._loading_packs)
        if submitting:
            self._btn_buy.setText("提交中…")
        elif self._packs:
            self._on_pack_changed()

    def _dispatch_async_result(self, ok: bool, err: str, data: object, cb_id: int) -> None:
        cb = self._async_callbacks.pop(cb_id, None)
        if cb is not None:
            cb(ok, err, data)

    def _run_worker(self, fn, on_done: Callable[[bool, str, object], None]) -> None:
        """后台 IO 完成后经面板 Signal 回到 GUI 线程。"""
        self._async_cb_seq += 1
        cb_id = self._async_cb_seq
        self._async_callbacks[cb_id] = on_done

        def _target() -> None:
            try:
                result = fn()
                if isinstance(result, tuple) and len(result) >= 3:
                    ok, msg, payload = result[0], result[1], result[2]
                elif isinstance(result, tuple) and len(result) == 2:
                    ok, msg, payload = result[0], result[1], None
                else:
                    ok, msg, payload = bool(result), "", None
                if ok:
                    self._async_result.emit(True, "", payload, cb_id)
                else:
                    self._async_result.emit(False, msg or "请求失败", payload, cb_id)
            except Exception as exc:
                self._async_result.emit(False, str(exc), None, cb_id)

        threading.Thread(target=_target, daemon=True).start()

    def _apply_packs(self, packs: list[dict], *, hint: str = "") -> None:
        self._packs = list(packs)
        self._pack_combo.blockSignals(True)
        self._pack_combo.clear()
        for p in packs:
            pid = str(p.get("plan_id") or p.get("id") or "")
            days = int(p.get("validity_days") or p.get("license_days") or 365)
            label = f"{p.get('name') or pid} · ¥{p.get('price_yuan', 0)} · {days}天"
            self._pack_combo.addItem(label, p)
        self._pack_combo.blockSignals(False)
        if packs:
            self._on_pack_changed()
            if hint:
                cur = self._detail.toPlainText().strip()
                self._detail.setPlainText(f"{hint}\n\n{cur}" if cur else hint)
        else:
            self._detail.setPlainText(hint or "暂无可售套餐")
            self._btn_buy.setText("提交开通申请")
            self._btn_buy.setEnabled(False)

    def _selected_pack(self) -> dict | None:
        data = self._pack_combo.currentData()
        return data if isinstance(data, dict) else None

    def _buyer_phone(self) -> str:
        return self._phone.text().strip() or str(self._profile.get("phone") or "").strip()

    def _buyer_name(self) -> str:
        return str(self._profile.get("name") or "用户").strip() or "用户"

    def _on_pack_changed(self) -> None:
        pack = self._selected_pack()
        if not pack:
            self._detail.clear()
            self._btn_buy.setText("提交开通申请")
            return
        lines = [
            str(pack.get("plan_name") or pack.get("name") or ""),
            str(pack.get("desc") or pack.get("description") or pack.get("summary") or ""),
            f"¥{pack.get('price_yuan', 0)} / {int(pack.get('validity_days') or pack.get('license_days') or 365)} 天",
        ]
        menus = pack.get("menu_ids") or pack.get("menus") or []
        if menus:
            lines.append(f"包含模块：{', '.join(str(m) for m in menus[:8])}{'…' if len(menus) > 8 else ''}")
        self._detail.setPlainText("\n".join(x for x in lines if x))
        self._update_buy_label(str(pack.get("plan_id") or pack.get("id") or ""))

    def _update_buy_label(self, pack_id: str) -> None:
        if self._submitting or not pack_id:
            return
        pack = self._selected_pack()
        price = int((pack or {}).get("price_yuan") or 0)
        self._btn_buy.setText(primary_action_label(price_yuan=price))

    def _load_packs(self) -> None:
        if self._submitting:
            return
        self._load_token += 1
        token = self._load_token

        local = _local_sellable_packs()
        if local:
            self._apply_packs(
                local,
                hint="已加载本机默认方案；正在后台同步运营台最新价格…",
            )
            self._set_loading_packs(False)
        else:
            self._set_loading_packs(True)
            if self._pack_combo.count() == 0:
                self._pack_combo.addItem("正在加载方案…", None)

        if self._load_watchdog is not None:
            self._load_watchdog.stop()
        self._load_watchdog = QTimer(self)
        self._load_watchdog.setSingleShot(True)
        self._load_watchdog.timeout.connect(lambda t=token: self._on_load_timeout(t))
        self._load_watchdog.start(_LOAD_WATCHDOG_MS)

        def work():
            return _fetch_remote_packs()

        def done(ok: bool, err: str, data: object) -> None:
            if token != self._load_token:
                return
            if self._load_watchdog is not None:
                self._load_watchdog.stop()
            self._set_loading_packs(False)
            if ok and isinstance(data, list) and data:
                self._apply_packs(data)
                return
            if self._packs:
                note = str(err or "运营台暂不可用")
                cur = self._detail.toPlainText().strip()
                if note and note not in cur:
                    self._detail.setPlainText(f"{cur}\n\n（{note}，已使用本机默认方案）".strip())
                return
            self._pack_combo.blockSignals(True)
            self._pack_combo.clear()
            self._pack_combo.addItem("加载失败 · 点刷新重试", None)
            self._pack_combo.blockSignals(False)
            self._detail.setPlainText(str(err or "无法连接运营台"))
            self._btn_buy.setEnabled(False)
            self._btn_buy.setText("提交开通申请")
            if err:
                show_error(self._host or self, err)

        if local:
            self._set_loading_packs(True)
        self._run_worker(work, done)

    def _on_load_timeout(self, token: int) -> None:
        if token != self._load_token:
            return
        self._set_loading_packs(False)
        if self._packs:
            cur = self._detail.toPlainText().strip()
            if "运营台" not in cur:
                self._detail.setPlainText(f"{cur}\n\n（运营台同步较慢，已使用本机默认方案）".strip())
            return
        self._load_token += 1
        self._pack_combo.blockSignals(True)
        self._pack_combo.clear()
        self._pack_combo.addItem("加载超时 · 点刷新重试", None)
        self._pack_combo.blockSignals(False)
        self._detail.setPlainText("连接运营台超时，请检查网络后点「刷新方案」。")
        self._btn_buy.setEnabled(False)
        self._btn_buy.setText("提交开通申请")

    def _on_buy(self) -> None:
        if self._submitting or self._loading_packs:
            return
        pack = self._selected_pack()
        if not pack:
            show_warning(self._host or self, "请先选择产品方案")
            return
        phone = self._buyer_phone()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._host or self, "请填写 11 位手机号")
            return

        pack_id = str(pack.get("plan_id") or pack.get("id") or "")
        name = self._buyer_name()
        self._set_submitting(True)

        def work():
            return submit_purchase_request(pack_id=pack_id, name=name, phone=phone)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_submitting(False)
            meta = data if isinstance(data, dict) else {}
            if not ok:
                show_error(self._host or self, err or "提交失败")
                self._on_pack_changed()
                return
            order_no = str(meta.get("order_no") or "")
            if order_no:
                self._pending_order_no = order_no
            self._profile = merge_buyer_profile()
            tip = f"开通申请已提交（订单 {order_no}）。" if order_no else "申请已提交至运营台。"
            show_success(self._host or self, tip)
            self._on_pack_changed()

        self._run_worker(work, done)

    def _on_sync_paid(self) -> None:
        if self._submitting or self._loading_packs:
            return
        phone = self._buyer_phone()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._host or self, "请填写 11 位手机号")
            return
        order_no = str(self._pending_order_no or "").strip()
        if not order_no:
            order_no = str(global_license_manager.get_license_info().get("last_order_no") or "").strip()
        if not order_no:
            show_warning(self._host or self, "暂无待同步订单；请先提交开通申请")
            return
        self._set_submitting(True)

        def work():
            return sync_paid_order(order_no=order_no, phone=phone)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_submitting(False)
            if not ok:
                show_error(self._host or self, err or "同步失败")
                self._on_pack_changed()
                return
            self._pending_order_no = ""
            self._profile = merge_buyer_profile()
            show_success(self._host or self, "授权已同步并刷新。")
            self.completed.emit()

        self._run_worker(work, done)
