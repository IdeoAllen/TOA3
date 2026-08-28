# -*- coding: utf-8 -*-
"""认证：开发跳过 / TOA 运营台授权码登录。"""
from __future__ import annotations

import logging
from typing import Any

from core.exceptions import AuthError
from services.config_service import get_auth_config

logger = logging.getLogger(__name__)


def authenticate_standalone() -> dict[str, Any]:
    """单机版入口：local_free，不联网。"""
    from services.license_manager import global_license_manager

    if not global_license_manager.enter_standalone_mode():
        raise AuthError("无法写入本机单机配置")
    name = str(global_license_manager.get_license_info().get("user_name") or "单机用户")
    logger.info("进入单机模式: %s", name)
    return {
        "username": name,
        "display_name": name,
        "role": "user",
        "runtime_mode": "standalone",
        "plan_id": "local_free",
    }


def authenticate(username: str, license_key: str) -> dict[str, Any]:
    """登录校验。开发环境可 skip_login；生产走 global_license_manager + DMS。"""
    auth = get_auth_config()
    if auth.get("skip_login"):
        user = str(username or auth.get("default_user") or "dev")
        role = str(auth.get("default_role") or "user").strip() or "user"
        return {"username": user, "display_name": user, "role": role}

    name = str(username or "").strip()
    key = str(license_key or "").strip().replace(" ", "")
    if not key and not auth.get("allow_empty_password"):
        raise AuthError("请粘贴 TOA 运营台签发的完整 TOA2 授权码")
    if not key:
        if not name:
            raise AuthError("请输入用户名")
        raise AuthError("请输入授权码")
    # 有授权码即可登录；姓名以码内 / DMS 台账为准，用户名可留空

    from services.license_manager import global_license_manager

    ok, message, payload = global_license_manager.activate_with_code(key)
    if not ok:
        raise AuthError(message or "授权码无效或已过期")

    info = payload or {}
    display = str(info.get("name") or name).strip() or name
    role = str(info.get("role") or "user")
    session = {
        "username": display,
        "display_name": display,
        "role": role,
        "features": list(info.get("features") or []),
        "runtime_mode": "network",
    }
    if name and display != name:
        # 允许输入名与授权登记名不完全一致，以授权登记为准并回写展示名
        session["display_name"] = display
        session["username"] = display
    logger.info("用户登录成功: %s (role=%s)", session["username"], role)
    return session
