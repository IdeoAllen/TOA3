# -*- coding: utf-8 -*-
"""系统设置 · 订阅购买：与全局无感开通共用同一套一键流程。"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_error, show_success, show_warning
from services.commerce_client import list_sellable_packs
from services.commerce_profile import merge_buyer_profile
from services.license_manager import global_license_manager
from services.subscription_renew import fetch_renew_quote
from services.upgrade_flow import primary_action_label, purchase_pack, sync_paid_order
from widgets import ComboBox, FormSection, HintLabel, LineEdit, PrimaryButton, ReadOnlyPlainTextEdit, SecondaryButton, SemanticLabel


class _CommerceWorker(QObject):
    finished = Signal(bool, str, object)

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
            if isinstance(result, tuple) and len(result) >= 3:
                ok, msg, data = result[0], result[1], result[2]
            elif isinstance(result, tuple) and len(result) == 2:
                ok, msg, data = result[0], result[1], None
            else:
                ok, msg, data = bool(result), "", None
            if ok:
                self.finished.emit(True, "", data)
            else:
                self.finished.emit(False, msg or "请求失败", data)
        except Exception as e:
            self.finished.emit(False, str(e), None)


class SubscriptionSection(FormSection):
    """选套餐 → 一键开通；与 paywall 弹窗同一购买链路。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__("全部产品方案")
        self._page = parent
        self._lm = global_license_manager
        self._packs: list[dict] = []
        self._commerce: dict = {}
        self._busy = False
        self._profile = merge_buyer_profile()
        self._pending_order_no = ""

        self.add_widget(
            HintLabel("选择产品方案（功能 + 有效期 + 定价）；支付后立即生效，一订单一授权码。")
        )

        self._status = SemanticLabel("", kind="info")
        self.add_widget(self._status)

        form = QFormLayout()
        self._pack_combo = ComboBox()
        self._pack_combo.currentIndexChanged.connect(self._on_pack_changed)
        form.addRow("产品方案", self._pack_combo)

        self._phone = LineEdit()
        self._phone.setPlaceholderText("11 位手机号")
        phone = str(self._profile.get("phone") or "")
        if phone:
            self._phone.setText(phone)
        else:
            form.addRow("手机号", self._phone)

        self._detail = ReadOnlyPlainTextEdit()
        self._detail.setMinimumHeight(72)
        form.addRow("说明", self._detail)

        wrap = QVBoxLayout()
        wrap.addLayout(form)
        self.add_layout(wrap)

        row = QHBoxLayout()
        self._btn_buy = PrimaryButton("一键开通")
        self._btn_buy.clicked.connect(self._on_buy)
        row.addWidget(self._btn_buy)
        self._btn_reload = SecondaryButton("刷新方案")
        self._btn_reload.clicked.connect(self._load_packs)
        row.addWidget(self._btn_reload)
        row.addStretch(1)
        self.add_layout(row)

        adv = QHBoxLayout()
        self._btn_sync = SecondaryButton("同步已付订单")
        self._btn_sync.clicked.connect(self._on_sync_paid)
        adv.addWidget(self._btn_sync)
        adv.addWidget(HintLabel("仅在 Portal 完成真实支付后使用"))
        adv.addStretch(1)
        self.add_layout(adv)

        self._refresh_status_line()
        self._load_packs()

    def _refresh_status_line(self) -> None:
        text = self._lm.get_validity_text() or "—"
        kind = "success" if self._lm.is_licensed() else ("info" if self._lm.is_standalone_mode() else "warning")
        self._status.setText(f"当前：{text}")
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_buy.setEnabled(not busy)
        self._btn_reload.setEnabled(not busy)
        self._pack_combo.setEnabled(not busy)
        self._phone.setEnabled(not busy)
        self._btn_sync.setEnabled(not busy)
        if busy:
            self._btn_buy.setText("处理中…")

    def _selected_pack(self) -> dict | None:
        data = self._pack_combo.currentData()
        return data if isinstance(data, dict) else None

    def _buyer_phone(self) -> str:
        visible = self._phone.isVisibleTo(self._page)
        if visible:
            return self._phone.text().strip()
        return str(self._profile.get("phone") or self._phone.text()).strip()

    def _buyer_name(self) -> str:
        return str(self._profile.get("name") or "用户").strip() or "用户"

    def _on_pack_changed(self) -> None:
        pack = self._selected_pack()
        if not pack:
            self._detail.clear()
            self._btn_buy.setText("一键开通")
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
        if self._busy or not pack_id:
            return

        def work():
            ok, quote, _ = fetch_renew_quote(pack_id)
            if not ok:
                return True, "", "一键开通"
            price = int(quote.get("price_yuan") or 0)
            return True, "", primary_action_label(price_yuan=price)

        worker = _CommerceWorker(work)
        thread = threading.Thread(target=worker.run, daemon=True)

        def done(ok: bool, err: str, data: object) -> None:
            if self._busy:
                return
            self._btn_buy.setText(str(data or "一键开通"))

        worker.finished.connect(done)
        thread.start()

    def _load_packs(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._page.report_status("正在加载产品方案…", level=StatusLevel.INFO)

        def work():
            ok, packs, commerce, err = list_sellable_packs()
            if not ok:
                return False, err, None
            return True, "", (packs, commerce)

        worker = _CommerceWorker(work)
        thread = threading.Thread(target=worker.run, daemon=True)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_busy(False)
            if not ok:
                show_error(self._page, err or "加载产品方案失败")
                self._page.report_status("加载产品方案失败", level=StatusLevel.ERROR)
                self._btn_buy.setText("一键开通")
                return
            packs, commerce = [], {}
            if isinstance(data, tuple) and len(data) >= 2:
                packs = data[0] if isinstance(data[0], list) else []
                commerce = data[1] if isinstance(data[1], dict) else {}
            self._packs = packs
            self._commerce = commerce
            self._pack_combo.clear()
            for p in packs:
                pid = str(p.get("plan_id") or p.get("id") or "")
                days = int(p.get("validity_days") or 365)
                label = f"{p.get('name') or pid} · ¥{p.get('price_yuan', 0)} · {days}天"
                self._pack_combo.addItem(label, p)
            self._page.report_status(f"已加载 {len(packs)} 个产品方案", level=StatusLevel.SUCCESS)
            self._on_pack_changed()

        worker.finished.connect(done)
        thread.start()

    def _on_buy(self) -> None:
        if self._busy:
            return
        pack = self._selected_pack()
        if not pack:
            show_warning(self._page, "请先选择产品方案")
            return
        phone = self._buyer_phone()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._page, "请填写 11 位手机号")
            if not self._phone.isVisibleTo(self._page):
                self._phone.show()
            return

        pack_id = str(pack.get("plan_id") or pack.get("id") or "")
        name = self._buyer_name()
        self._set_busy(True)
        self._page.report_status("正在开通…", level=StatusLevel.INFO)

        def work():
            return purchase_pack(pack_id=pack_id, name=name, phone=phone)

        worker = _CommerceWorker(work)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_busy(False)
            meta = data if isinstance(data, dict) else {}
            if not ok:
                order_no = str(meta.get("order_no") or "")
                if meta.get("pending_payment") and order_no:
                    self._pending_order_no = order_no
                    show_warning(
                        self._page,
                        f"订单 {order_no} 已创建。\n\n请在 Portal 完成支付后，点下方「同步已付订单」。",
                    )
                    self._page.report_status(f"待支付订单 {order_no}", level=StatusLevel.WARNING)
                    self._on_pack_changed()
                    return
                show_error(self._page, err or "开通失败")
                self._page.report_status("开通失败", level=StatusLevel.ERROR)
                self._on_pack_changed()
                return
            self._pending_order_no = ""
            self._profile = merge_buyer_profile()
            self._refresh_status_line()
            renewed = "续费" if meta.get("renewed") else "开通"
            show_success(self._page, f"{renewed}成功，已刷新授权。")
            self._page.report_status("授权已更新", level=StatusLevel.SUCCESS)

        worker.finished.connect(done)
        thread.start()

    def _on_sync_paid(self) -> None:
        if self._busy:
            return
        phone = self._buyer_phone()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._page, "请填写 11 位手机号")
            return
        order_no = self._pending_order_no.strip()
        if not order_no:
            show_warning(self._page, "暂无待同步订单；请先创建订单")
            return
        self._set_busy(True)

        def work():
            return sync_paid_order(order_no=order_no, phone=phone)

        worker = _CommerceWorker(work)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_busy(False)
            if not ok:
                show_error(self._page, err or "同步失败")
                self._on_pack_changed()
                return
            meta = data if isinstance(data, dict) else {}
            self._pending_order_no = ""
            self._profile = merge_buyer_profile()
            self._refresh_status_line()
            renewed = "续费" if meta.get("renewed") else "开通"
            show_success(self._page, f"{renewed}成功，已刷新授权。")
            self._page.report_status("授权已更新", level=StatusLevel.SUCCESS)

        worker.finished.connect(done)
        thread.start()
