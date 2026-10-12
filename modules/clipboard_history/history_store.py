# -*- coding: utf-8 -*-
"""剪贴板历史存储（兼容入口；实现已迁至 services.clipboard_history_store）。"""
from __future__ import annotations

from services.clipboard_history_store import *  # noqa: F403
from services.clipboard_history_store import (  # noqa: F401
    clear_history,
    delete_item,
    filter_history,
    find_item,
    image_abs_path,
    list_line,
    load_history,
    load_prefs,
    notepad_handoff,
    privacy_on,
    push_clipboard_image,
    push_image,
    push_text,
    save_history,
    save_prefs,
    set_privacy,
    source_label,
    toggle_pin,
)
