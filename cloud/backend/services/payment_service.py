# -*- coding: utf-8 -*-
"""支付回调：微信/支付宝占位 + mock 联调。"""
from __future__ import annotations

import hmac
from typing import Any

from sqlalchemy.orm import Session

from services import order_service as orders
from services import pack_service as packs


def _verify_webhook_secret(provided: str) -> None:
    expected = packs.webhook_secret()
    if not expected:
        raise ValueError("未配置 webhook secret（TOA_CLOUD_WEBHOOK_SECRET）")
    if not hmac.compare_digest(str(provided or "").strip(), expected):
        raise ValueError("Webhook 签名校验失败")


def _normalize_channel(channel: str) -> str:
    ch = str(channel or "mock").strip().lower() or "mock"
    allowed = packs.webhook_allowed_channels()
    if allowed and ch not in allowed:
        raise ValueError(f"不支持的支付通道：{ch}")
    return ch


def _parse_payment_body(body: dict, *, channel: str) -> tuple[str, str, str]:
    order_no = str((body or {}).get("order_no") or "").strip()
    phone = str((body or {}).get("phone") or "").strip()
    tx_id = str(
        (body or {}).get("transaction_id")
        or (body or {}).get("payment_ref")
        or (body or {}).get("out_trade_no")
        or ""
    ).strip()
    if not order_no:
        raise ValueError("缺少 order_no")
    if not tx_id:
        raise ValueError("缺少 transaction_id（幂等键）")
    return order_no, phone, tx_id


def handle_webhook(
    db: Session,
    channel: str,
    body: dict,
    *,
    secret_header: str = "",
    skip_secret: bool = False,
) -> dict[str, Any]:
    """统一支付回调入口。

    占位 JSON 协议（微信/支付宝接入时映射到同字段）::

        {
          "event": "payment.success",
          "order_no": "TOA20260827ABC",
          "phone": "13800138000",
          "transaction_id": "wx_20260827_001",
          "amount_yuan": 199
        }
    """
    ch = _normalize_channel(channel)
    if not skip_secret:
        _verify_webhook_secret(secret_header or str((body or {}).get("secret") or ""))

    event = str((body or {}).get("event") or "payment.success").strip().lower()
    if event not in ("payment.success", "pay.success", "success"):
        raise ValueError(f"忽略的事件：{event}")

    order_no, phone, tx_id = _parse_payment_body(body or {}, channel=ch)
    row = orders.fulfill_order_by_payment(
        db,
        order_no=order_no,
        phone=phone,
        payment_provider=ch,
        payment_ref=tx_id,
    )
    out = orders.order_to_dict(row, include_license_key=True, db=db)
    out["fulfilled"] = True
    out["payment_provider"] = ch
    return out


def handle_webhook_dev(db: Session, channel: str, body: dict) -> dict[str, Any]:
    """开发联调：未配置 secret 时允许无签名（仅限本地）。"""
    if packs.webhook_secret():
        raise ValueError("已配置 webhook secret，请携带 X-TOA-Webhook-Secret")
    return handle_webhook(db, channel, body, skip_secret=True)
