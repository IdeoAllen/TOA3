# -*- coding: utf-8 -*-
"""系统设置 · 订阅购买（功能包 + 假订单支付 + 自动激活）。"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_error, show_info, show_success, show_warning
from services.commerce_client import create_order, list_sellable_packs, pay_order, upgrade_from_order
from services.license_manager import global_license_manager
from services.notify_bus import emit_license_changed
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
            ok, data, err = self._fn(*self._args, **self._kwargs)
            if ok:
                self.finished.emit(True, "", data)
            else:
                self.finished.emit(False, err or "请求失败", None)
        except Exception as e:
            self.finished.emit(False, str(e), None)


class SubscriptionSection(FormSection):
    """终端订阅：选 pack → 下单 → 模拟支付 → 自动激活。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__("订阅购买")
        self._page = parent
        self._lm = global_license_manager
        self._packs: list[dict] = []
        self._commerce: dict = {}
        self._busy = False

        self.add_widget(
            HintLabel(
                "选择功能包并填写手机号，点击「订阅并支付」。\n"
                "同手机号再次购买将自动续费延长到期日（不必换账号）。\n"
                "现阶段为模拟支付；真实支付接入后由 Portal 回调 webhook 履约，终端点「同步已付订单」。"
            )
        )

        self._status = SemanticLabel("", kind="info")
        self.add_widget(self._status)

        form = QFormLayout()
        self._pack_combo = ComboBox()
        self._pack_combo.currentIndexChanged.connect(self._on_pack_changed)
        form.addRow("功能包", self._pack_combo)

        self._name = LineEdit()
        self._name.setPlaceholderText("姓名")
        form.addRow("姓名", self._name)

        self._phone = LineEdit()
        self._phone.setPlaceholderText("11 位手机号")
        form.addRow("手机号", self._phone)

        self._detail = ReadOnlyPlainTextEdit()
        self._detail.setMinimumHeight(88)
        form.addRow("说明", self._detail)

        wrap = QVBoxLayout()
        wrap.addLayout(form)
        self.add_layout(wrap)

        row = QHBoxLayout()
        self._btn_reload = SecondaryButton("刷新功能包")
        self._btn_reload.clicked.connect(self._load_packs)
        row.addWidget(self._btn_reload)
        self._btn_buy = PrimaryButton("订阅并支付")
        self._btn_buy.clicked.connect(self._on_buy)
        row.addWidget(self._btn_buy)
        self._btn_sync = SecondaryButton("同步已付订单")
        self._btn_sync.clicked.connect(self._on_sync_paid)
        row.addWidget(self._btn_sync)
        self._pending_order_no = ""
        row.addStretch(1)
        self.add_layout(row)

        info = self._lm.get_license_info()
        if not self._name.text().strip():
            self._name.setText(str(info.get("user_name") or "").strip())
        if not self._phone.text().strip():
            self._phone.setText(str(info.get("phone") or "").strip())

        self._refresh_status_line()
        self._load_packs()

    def _refresh_status_line(self) -> None:
        text = f"当前：{self._lm.get_validity_text()} · 机器 ID：{self._lm.get_machine_id()}"
        kind = "success" if self._lm.is_licensed() else ("info" if self._lm.is_standalone_mode() else "warning")
        self._status.setText(text)
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_buy.setEnabled(not busy)
        self._btn_reload.setEnabled(not busy)
        self._pack_combo.setEnabled(not busy)
        self._name.setEnabled(not busy)
        self._phone.setEnabled(not busy)
        self._btn_sync.setEnabled(not busy)

    def _selected_pack(self) -> dict | None:
        data = self._pack_combo.currentData()
        return data if isinstance(data, dict) else None

    def _on_pack_changed(self) -> None:
        pack = self._selected_pack()
        if not pack:
            self._detail.clear()
            return
        lines = [
            str(pack.get("name") or ""),
            str(pack.get("description") or pack.get("summary") or ""),
            f"参考价：¥{pack.get('price_yuan', 0)} / {pack.get('default_days') or 365} 天",
        ]
        menus = pack.get("menu_ids") or pack.get("menus") or []
        if menus:
            lines.append(f"包含模块：{', '.join(str(m) for m in menus[:8])}{'…' if len(menus) > 8 else ''}")
        self._detail.setPlainText("\n".join(x for x in lines if x))

    def _load_packs(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._page.report_status("正在加载功能包…", level=StatusLevel.INFO)

        def work():
            ok, packs, commerce, err = list_sellable_packs()
            if not ok:
                return False, None, err
            return True, (packs, commerce), ""

        worker = _CommerceWorker(work)
        thread = threading.Thread(target=worker.run, daemon=True)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_busy(False)
            if not ok:
                show_error(self._page, err or "加载功能包失败")
                self._page.report_status("加载功能包失败", level=StatusLevel.ERROR)
                return
            packs, commerce = [], {}
            if isinstance(data, tuple) and len(data) >= 2:
                packs = data[0] if isinstance(data[0], list) else []
                commerce = data[1] if isinstance(data[1], dict) else {}
            self._packs = packs
            self._commerce = commerce
            self._pack_combo.clear()
            for p in packs:
                pid = str(p.get("id") or "")
                label = f"{p.get('name') or pid} · ¥{p.get('price_yuan', 0)}"
                self._pack_combo.addItem(label, p)
            mock = (commerce.get("mock_payment") or {}).get("note") or ""
            if mock:
                self._page.report_status("功能包已加载（模拟支付）", level=StatusLevel.SUCCESS)
            else:
                self._page.report_status(f"已加载 {len(packs)} 个功能包", level=StatusLevel.SUCCESS)
            self._on_pack_changed()

        worker.finished.connect(done)
        thread.start()

    def _on_buy(self) -> None:
        if self._busy:
            return
        pack = self._selected_pack()
        if not pack:
            show_warning(self._page, "请先选择功能包")
            return
        name = self._name.text().strip()
        phone = self._phone.text().strip()
        if not name:
            show_warning(self._page, "请填写姓名")
            return
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._page, "请填写 11 位手机号")
            return

        pack_id = str(pack.get("id") or "")
        mid = self._lm.get_machine_id()
        mock_ok = bool((self._commerce.get("mock_payment") or {}).get("enabled", True))
        real_on = bool(self._commerce.get("real_payment_enabled"))
        use_mock_pay = mock_ok and not real_on
        self._set_busy(True)
        self._page.report_status("正在创建订单…", level=StatusLevel.INFO)

        def work():
            ok, order, err = create_order(
                pack_id=pack_id,
                customer_name=name,
                phone=phone,
                machine_id=mid,
            )
            if not ok:
                return False, None, err
            order_no = str((order or {}).get("order_no") or "")
            if not order_no:
                return False, None, "订单号为空"
            if not use_mock_pay:
                return True, {"order_only": True, "order": order, "order_no": order_no}, ""
            ok2, paid, err2 = pay_order(order_no=order_no, phone=phone, machine_id=mid)
            if not ok2:
                return False, order, err2 or "支付失败"
            paid = dict(paid or {})
            paid["renewed"] = "续费" in str(paid.get("remark") or "")
            return True, paid, ""

        worker = _CommerceWorker(work)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_busy(False)
            if not ok:
                show_error(self._page, err or "订阅失败")
                self._page.report_status("订阅失败", level=StatusLevel.ERROR)
                return
            paid = data if isinstance(data, dict) else {}
            if paid.get("order_only"):
                order_no = str(paid.get("order_no") or "")
                show_info(
                    self._page,
                    f"订单已创建：{order_no}\n\n请在 Portal 完成支付；支付成功后点「同步已付订单」或重新进入本页。",
                )
                self._pending_order_no = order_no
                self._page.report_status(f"待支付订单 {order_no}", level=StatusLevel.WARNING)
                return
            self._activate_from_payment(paid)

        worker.finished.connect(done)
        threading.Thread(target=worker.run, daemon=True).start()

    def _activate_from_payment(self, paid: dict) -> None:
        license_key = str(paid.get("license_key") or "").strip()
        if not license_key:
            show_error(self._page, "支付成功但未返回授权码，请联系管理员在运营台查看订单。")
            return
        act_ok, act_msg, _ = self._lm.activate_with_code(license_key)
        if not act_ok:
            show_error(
                self._page,
                f"已{'续费' if paid.get('renewed') else '发卡'}但本机激活失败：{act_msg}",
            )
            show_info(self._page, license_key)
            return
        emit_license_changed()
        self._refresh_status_line()
        order_no = str(paid.get("order_no") or "")
        renewed = "续费" if paid.get("renewed") else "开通"
        show_success(self._page, f"{renewed}成功！订单 {order_no}\n\n{self._lm.get_validity_text()}")
        self._page.report_status("订阅已激活", level=StatusLevel.SUCCESS)

    def _on_sync_paid(self) -> None:
        if self._busy:
            return
        phone = self._phone.text().strip()
        if len(phone) != 11 or not phone.isdigit():
            show_warning(self._page, "请填写 11 位手机号")
            return
        order_no = self._pending_order_no.strip()
        if not order_no:
            show_warning(self._page, "暂无待同步订单；请先创建订单或填写订单号")
            return
        mid = self._lm.get_machine_id()
        self._set_busy(True)

        def work():
            ok, data, err = upgrade_from_order(order_no=order_no, phone=phone, machine_id=mid)
            if not ok:
                ok2, st, err2 = pay_order(order_no=order_no, phone=phone, machine_id=mid)
                if ok2:
                    return True, st, ""
                return False, None, err or err2
            return True, data, err

        worker = _CommerceWorker(work)

        def done(ok: bool, err: str, data: object) -> None:
            self._set_busy(False)
            if not ok:
                show_error(self._page, err or "订单尚未支付或同步失败")
                return
            paid = data if isinstance(data, dict) else {}
            self._activate_from_payment(paid)

        worker.finished.connect(done)
        threading.Thread(target=worker.run, daemon=True).start()
