# -*- coding: utf-8 -*-
"""运行模式：单机 local_free vs 联网授权。"""
from __future__ import annotations

from functools import lru_cache

STANDALONE = "standalone"
NETWORK = "network"
LOCAL_FREE_PLAN = "local_free"

# 壳层必备（不计入 SKU）
SHELL_MODULE_IDS = frozenset(
    {
        "home",
        "system_settings",
        "notifications",
        "job_scheduler",
        "about",
        "__about__",
    }
)


@lru_cache(maxsize=1)
def local_free_module_ids() -> frozenset[str]:
    from services.feature_packs import expand_features

    expanded = expand_features([LOCAL_FREE_PLAN])
    return frozenset(expanded) | SHELL_MODULE_IDS


def is_standalone_record(info: dict | None) -> bool:
    if not isinstance(info, dict):
        return False
    mode = str(info.get("runtime_mode") or "").strip().lower()
    if mode == STANDALONE:
        return True
    return str(info.get("license_type") or "").strip().lower() == STANDALONE


def standalone_display_name() -> str:
    try:
        from services.edition_profile import edition_label

        label = edition_label()
        if label:
            return f"{label}用户"
    except Exception:
        pass
    return "体验用户"
