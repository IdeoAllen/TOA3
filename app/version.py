# -*- coding: utf-8 -*-
"""TOA3 版本号（单一来源）。"""
APP_VERSION = "3.1.1"
APP_NAME = "TOA3"


def build_profile_label() -> str:
    """发行类型：开发版 / 正式版（单机）/ 正式版（网络）。"""
    try:
        from services.runtime_paths import get_runtime_environment

        env = get_runtime_environment()
    except Exception:
        env = "release"
    if env == "development":
        return "开发版"
    try:
        from services.edition_profile import edition_id

        eid = edition_id()
    except Exception:
        eid = ""
    if eid == "standalone":
        return "正式版（单机）"
    return "正式版（网络）"


def version_caption(*, short: bool = False) -> str:
    """登录页 / 关于页用的可读版本串。"""
    profile = build_profile_label()
    if short:
        return f"v{APP_VERSION} · {profile}"
    return f"TOA3 v{APP_VERSION} · {profile}"
