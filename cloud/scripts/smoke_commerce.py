#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOA Cloud：功能包 + 假订单 + 发版 冒烟测试。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


def run() -> None:
    with TestClient(app) as c:
        h = c.get("/api/health")
        assert h.status_code == 200

        packs = c.get("/api/toa/packs")
        assert packs.status_code == 200
        body = packs.json()
        sellable = [p for p in body.get("packs", []) if p.get("sellable")]
        assert sellable, "need sellable packs"

        from config import ADMIN_PASSWORD, ADMIN_USERNAME

        login = c.post(
            "/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200, login.text
        token = login.json().get("token")
        auth = {"Authorization": f"Bearer {token}"}

        catalog = c.get("/api/toa/packs/catalog", headers=auth)
        assert catalog.status_code == 200
        assert any(p["id"] == "local_free" for p in catalog.json().get("packs", []))

        pack_id = sellable[0]["id"]
        order = c.post(
            "/api/toa/orders",
            json={
                "pack_id": pack_id,
                "customer_name": "测试用户",
                "phone": "13800138000",
                "license_days": 30,
            },
        )
        assert order.status_code == 200, order.text
        oid = order.json()["id"]
        order_no = order.json()["order_no"]

        client_order = c.post(
            f"/api/toa/orders/by-no/{order_no}/pay",
            json={"phone": "13800138000", "machine_id": "smoke-terminal-01"},
        )
        assert client_order.status_code == 200, client_order.text
        assert client_order.json().get("license_key", "").startswith("TOA2-")

        # 同手机号续费：第二次下单应延长到期
        order_renew = c.post(
            "/api/toa/orders",
            json={
                "pack_id": pack_id,
                "customer_name": "测试用户",
                "phone": "13800138000",
                "license_days": 30,
            },
        )
        assert order_renew.status_code == 200, order_renew.text
        renew_no = order_renew.json()["order_no"]
        paid_renew = c.post(
            f"/api/toa/orders/by-no/{renew_no}/pay",
            json={"phone": "13800138000", "machine_id": "smoke-terminal-01"},
        )
        assert paid_renew.status_code == 200, paid_renew.text
        assert "续费" in (paid_renew.json().get("remark") or "")

        # Webhook 占位（无 secret 开发模式）
        order_wh = c.post(
            "/api/toa/orders",
            json={
                "pack_id": pack_id,
                "customer_name": "Webhook用户",
                "phone": "13700137000",
                "license_days": 7,
            },
        )
        assert order_wh.status_code == 200
        wh_no = order_wh.json()["order_no"]
        wh = c.post(
            "/api/toa/payments/webhook/mock",
            json={
                "event": "payment.success",
                "order_no": wh_no,
                "phone": "13700137000",
                "transaction_id": "mock-wh-smoke-001",
            },
        )
        assert wh.status_code == 200, wh.text
        assert wh.json().get("license_key", "").startswith("TOA2-")

        upgrade = c.post(
            "/api/toa-license/upgrade",
            json={"order_no": wh_no, "phone": "13700137000", "machine_id": "smoke-02"},
        )
        assert upgrade.status_code == 200, upgrade.text
        assert upgrade.json().get("license_key", "").startswith("TOA2-")

        order2 = c.post(
            "/api/toa/orders",
            json={
                "pack_id": pack_id,
                "customer_name": "运营台用户",
                "phone": "13900139000",
                "license_days": 30,
            },
        )
        assert order2.status_code == 200, order2.text
        oid = order2.json()["id"]

        paid = c.post(f"/api/toa/orders/{oid}/mock-pay", headers=auth)
        assert paid.status_code == 200, paid.text
        assert paid.json().get("license_key", "").startswith("TOA2-")

        rel = c.post(
            "/api/toa/releases",
            headers=auth,
            json={
                "product": "TOA3",
                "channel": "stable",
                "version": "3.0.1-test",
                "download_url": "https://www.yczh.tech/downloads/TOA3-Setup-test.exe",
                "is_current": False,
            },
        )
        assert rel.status_code == 200, rel.text

    print("toa_cloud_commerce_smoke: OK")


if __name__ == "__main__":
    run()
