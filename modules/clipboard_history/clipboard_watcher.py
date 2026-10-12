# -*- coding: utf-8 -*-
"""剪贴板监听（兼容入口；实现已迁至 services.clipboard_watcher）。"""
from __future__ import annotations

from services.clipboard_watcher import ClipboardWatcher, get_clipboard_watcher

__all__ = ["ClipboardWatcher", "get_clipboard_watcher"]
