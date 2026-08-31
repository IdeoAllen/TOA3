# -*- coding: utf-8 -*-
"""无感开通/升级/续费：统一购买弹窗（不再跳转系统设置）。"""
from __future__ import annotations

from app.commerce_dialog import open_purchase_dialog
from services.upgrade_flow import should_offer_purchase


def offer_upgrade_for_module(
    parent,
    *,
    module_id: str = "",
    reason: str = "",
) -> bool:
    if not should_offer_purchase(reason=reason):
        return False
    return open_purchase_dialog(
        parent,
        reason=reason,
        module_id=module_id,
        forced=False,
    )
