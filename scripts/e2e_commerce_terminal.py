#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端订阅闭环冒烟：下单 → 模拟支付 → 激活。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.commerce_client import create_order, list_sellable_packs, pay_order
from services.config_service import load_config
from services.license_manager import global_license_manager


def main() -> int:
    load_config(force=True)
    ok, packs, commerce, err = list_sellable_packs()
    if not ok:
        print("FAIL list_packs:", err)
        return 1
    if not packs:
        print("FAIL no sellable packs")
        return 1
    pack = packs[0]
    pid = str(pack.get("id") or "")
    phone = "13800138000"
    name = "冒烟用户"
    mid = global_license_manager.get_machine_id()
    print(f"pack={pid} machine={mid[:8]}… mock={commerce.get('mock_payment')}")

    ok, order, err = create_order(pack_id=pid, customer_name=name, phone=phone, machine_id=mid)
    if not ok:
        print("FAIL create_order:", err)
        return 1
    order_no = str(order.get("order_no") or "")
    print("order:", order_no, order.get("status"))

    ok, paid, err = pay_order(order_no=order_no, phone=phone, machine_id=mid)
    if not ok:
        print("FAIL pay:", err)
        return 1
    key = str(paid.get("license_key") or "")
    if not key.startswith("TOA2-"):
        print("FAIL no license_key")
        return 1
    print("license_key:", key[:20], "…")

    act_ok, act_msg, _ = global_license_manager.activate_with_code(key)
    if not act_ok:
        print("FAIL activate:", act_msg)
        return 1
    print("OK activated:", global_license_manager.get_validity_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
