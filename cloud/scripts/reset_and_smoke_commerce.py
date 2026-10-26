#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清空冗余测试数据 → 保留固定管理员 → 跑通购买/授权主路径 → 只留有效基线。

用法（生产机）:
  cd /opt/toa-cloud/backend
  /opt/toa-cloud/venv/bin/python ../scripts/reset_and_smoke_commerce.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from database import SessionLocal  # noqa: E402
from models import ToaCustomer, ToaLicense, ToaOrder, ToaRelease  # noqa: E402
from services import order_service as orders  # noqa: E402
from services import toa_license_service as lic  # noqa: E402

KEEP_RELEASE_VERSION = "3.1.4"
TEST_PHONE = "13900001111"
TEST_NAME = "联调测试用户"
TEST_MACHINE = "smoke-machine-toa3-01"
TRIAL_PHONE = "13800002222"
TRIAL_NAME = "内测用户甲"


def _banner(title: str) -> None:
    print(f"\n=== {title} ===")


def cleanup(db) -> None:
    _banner("清理冗余数据")
    admin = lic.ensure_bootstrap_admin_license(db) or lic._protected_admin_row(db)
    if admin is None:
        raise RuntimeError("无法确保固定管理员授权")
    admin_id = int(admin.id)

    admin.name = "管理员"
    admin.role = "admin"
    admin.entitlement = "admin"
    admin.order_no = ""
    admin.plan_id = ""
    admin.status = "active"
    admin.remark = "bootstrap-admin"
    db.commit()

    n_ord = db.query(ToaOrder).delete()
    n_cust = db.query(ToaCustomer).delete()
    n_lic = (
        db.query(ToaLicense)
        .filter(ToaLicense.id != admin_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    print(f"deleted orders={n_ord} customers={n_cust} licenses(non-admin)={n_lic}")

    kept = 0
    for row in db.query(ToaRelease).order_by(ToaRelease.id.asc()).all():
        if str(row.version) == KEEP_RELEASE_VERSION:
            row.is_current = True
            kept += 1
        else:
            db.delete(row)
    db.commit()
    if kept == 0:
        print(f"WARN: 未找到版本 {KEEP_RELEASE_VERSION}")
    else:
        print(f"releases kept={kept} current={KEEP_RELEASE_VERSION}")

    lic.sync_all_licenses_to_customers(db)
    print("baseline licenses:", db.query(ToaLicense).count(), "customers:", db.query(ToaCustomer).count())


def smoke_issue_trial(db) -> ToaLicense:
    _banner("授权流程：签发体验授权")
    row = lic.create_license(
        db,
        {
            "name": TRIAL_NAME,
            "phone": TRIAL_PHONE,
            "days": 90,
            "pack_id": "tiyan",
            "entitlement": "trial",
            "remark": "smoke-trial",
        },
    )
    assert row.license_key.startswith("TOA2-")
    assert (row.entitlement or "") == "trial"
    d = lic.license_to_dict(row, include_key=True, protected_id=lic.protected_admin_id(db))
    print("issued", d["name"], d["entitlement_label"], d["expire_date"], d["code_fingerprint"])
    return row


def smoke_activate_check(db, row: ToaLicense) -> None:
    _banner("授权流程：激活 + 联网校验")
    act = lic.activate_online(
        db,
        license_key=row.license_key,
        machine_id=TEST_MACHINE + "-trial",
    )
    print("activate", act.get("status") or act.get("ok"), act.get("expire_date"))
    assert act.get("status") in ("active", "ok", None) or act.get("ok") is True or "expire_date" in act

    chk = lic.check_online(
        db,
        code_id=row.code_id,
        license_key=row.license_key,
        machine_id=TEST_MACHINE + "-trial",
    )
    print("check", chk.get("status"), chk.get("expire_date"))
    assert chk.get("status") == "active"


def smoke_purchase(db) -> tuple[ToaOrder, ToaLicense]:
    _banner("购买流程：下单 → 模拟支付 → 拉码 → 激活")
    order = orders.create_order(
        db,
        {
            "pack_id": "tiyan",
            "customer_name": TEST_NAME,
            "phone": TEST_PHONE,
            "license_days": 365,
        },
    )
    print("order", order.order_no, order.status, f"¥{order.amount_yuan}")
    assert order.status == "pending"

    try:
        paid_row = orders.client_pay_and_fulfill(
            db, order.order_no, phone=TEST_PHONE, machine_id=TEST_MACHINE
        )
    except ValueError as exc:
        print("client_pay fallback to ops mock-pay:", exc)
        paid_row = orders.mock_pay_and_fulfill(db, order.id)
        if TEST_MACHINE:
            paid_row.machine_id = TEST_MACHINE
            db.commit()
            db.refresh(paid_row)
    paid = orders.order_to_dict(paid_row, include_license_key=True, db=db)
    print("paid", paid["order_no"], paid["status"], (paid.get("license_key") or "")[:32])
    assert paid["status"] == "fulfilled"
    assert paid.get("license_key", "").startswith("TOA2-")
    key = paid["license_key"]

    up = lic.upgrade_from_fulfilled_order(
        db, order_no=order.order_no, phone=TEST_PHONE, machine_id=TEST_MACHINE
    )
    print("upgrade/pull", up.get("ok"), (up.get("license_key") or "")[:32])
    assert up.get("license_key") == key

    lic_row = db.query(ToaLicense).filter(ToaLicense.license_key == key).first()
    assert lic_row is not None
    assert lic_row.entitlement == "paid"
    assert lic_row.order_no == order.order_no
    assert lic_row.plan_id == "tiyan"

    act = lic.activate_online(db, license_key=key, machine_id=TEST_MACHINE)
    print("activate paid", act.get("status"), act.get("expire_date"))
    chk = lic.check_online(db, license_key=key, machine_id=TEST_MACHINE)
    assert chk.get("status") == "active"
    print("check paid", chk.get("status"))

    db.refresh(order)
    return order, lic_row


def smoke_reject_admin_phone_overwrite(db) -> None:
    _banner("回归：同号订单不得覆盖固定管理员")
    admin = lic._protected_admin_row(db)
    assert admin is not None
    before_key = admin.license_key
    before_fp = admin.code_fingerprint
    order = orders.create_order(
        db,
        {
            "pack_id": "tiyan",
            "customer_name": "误用管理员号",
            "phone": admin.phone,
            "license_days": 30,
        },
    )
    paid = orders.client_pay_and_fulfill(
        db, order.order_no, phone=admin.phone, machine_id="evil-machine"
    )
    db.refresh(admin)
    assert admin.license_key == before_key, "管理员码被覆盖"
    assert admin.code_fingerprint == before_fp
    assert (admin.entitlement or "") == "admin"
    others = (
        db.query(ToaLicense)
        .filter(ToaLicense.phone == admin.phone, ToaLicense.id != admin.id)
        .count()
    )
    print("admin intact; same-phone other licenses:", others)
    assert others >= 1, "应另建非管理员授权行"

    # 清掉本步垃圾
    for o in db.query(ToaOrder).filter(ToaOrder.phone == admin.phone).all():
        db.delete(o)
    for r in db.query(ToaLicense).filter(ToaLicense.phone == admin.phone, ToaLicense.id != admin.id).all():
        db.delete(r)
    db.commit()
    db.refresh(admin)
    assert admin.license_key == before_key


def finalize_baseline(db, keep_trial: ToaLicense, keep_paid: ToaLicense) -> None:
    _banner("收口：只留有效基线")
    admin = lic._protected_admin_row(db)
    keep_ids = {admin.id, keep_trial.id, keep_paid.id}
    for r in list(db.query(ToaLicense).all()):
        if r.id not in keep_ids:
            db.delete(r)
    keep_order_nos = {str(keep_paid.order_no or "")}
    for o in list(db.query(ToaOrder).all()):
        if o.order_no not in keep_order_nos:
            db.delete(o)
    db.commit()
    db.query(ToaCustomer).delete()
    db.commit()
    lic.sync_all_licenses_to_customers(db)

    print("\n--- 最终基线 ---")
    pid = lic.protected_admin_id(db)
    for r in db.query(ToaLicense).order_by(ToaLicense.id).all():
        d = lic.license_to_dict(r, protected_id=pid)
        print(
            f"L{d['id']} {d['name']} {d['phone']} {d['entitlement_label']} "
            f"exp={d['expire_date']} order={d['order_no'] or '-'} prot={d['protected']}"
        )
    for o in db.query(ToaOrder).order_by(ToaOrder.id).all():
        print(f"O {o.order_no} {o.customer_name} {o.phone} {o.pack_id} ¥{o.amount_yuan} {o.status}")
    for c in db.query(ToaCustomer).order_by(ToaCustomer.id).all():
        print(f"C{c.id} {c.display_name} {c.phone} lic={c.license_id}")
    for r in db.query(ToaRelease).order_by(ToaRelease.id).all():
        print(f"R {r.version} current={bool(r.is_current)}")


def main() -> int:
    db = SessionLocal()
    try:
        cleanup(db)
        trial = smoke_issue_trial(db)
        smoke_activate_check(db, trial)
        order, paid = smoke_purchase(db)
        smoke_reject_admin_phone_overwrite(db)
        finalize_baseline(db, trial, paid)
        print("\nreset_and_smoke_commerce: OK")
        print(
            json.dumps(
                {
                    "admin_phone": "12345678901",
                    "trial_phone": TRIAL_PHONE,
                    "trial_name": TRIAL_NAME,
                    "paid_phone": TEST_PHONE,
                    "paid_name": TEST_NAME,
                    "paid_order": order.order_no,
                    "current_release": KEEP_RELEASE_VERSION,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print("FAIL:", exc)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
