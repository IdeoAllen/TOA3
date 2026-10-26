# -*- coding: utf-8 -*-
"""支付 Webhook API（微信 / 支付宝 / mock 占位）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services import payment_service as pay_svc
from services import pack_service as packs

router = APIRouter(prefix="/api/toa/payments", tags=["toa-payments"])


@router.post("/webhook/{channel}")
def payment_webhook(
    channel: str,
    data: dict,
    db: Session = Depends(get_db),
    x_toa_webhook_secret: str = Header(default="", alias="X-TOA-Webhook-Secret"),
):
    """支付成功回调 → 订单履约 → 续费/发卡。

    生产：Header ``X-TOA-Webhook-Secret`` = ``TOA_CLOUD_WEBHOOK_SECRET``。
    本地：未配置 secret 时可无签名调用（仅开发）。
    """
    try:
        if packs.webhook_secret():
            result = pay_svc.handle_webhook(
                db,
                channel,
                data or {},
                secret_header=x_toa_webhook_secret,
            )
        else:
            result = pay_svc.handle_webhook_dev(db, channel, data or {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return result
