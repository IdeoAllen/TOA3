# -*- coding: utf-8 -*-
"""我的扩展：统一跳转到系统侧栏「扩展」（避免多入口杂乱）。"""
from __future__ import annotations

from pathlib import Path

from core.user_messages import show_error


MODULE_ID = "user_extensions"


def _shell_of(widget):
    w = widget
    while w is not None and not hasattr(w, "navigate"):
        w = w.parent() if hasattr(w, "parent") else None
    return w


def set_harness_workspace(root: Path) -> None:
    from services.harness_toolkit import harness

    harness.ensure_workspace(root)


def open_extension_hub(parent=None) -> None:
    """打开系统 → 扩展（可打包销售的 feature_id=user_extensions）。"""
    shell = _shell_of(parent)
    if shell is None:
        show_error(parent, "无法打开扩展管理")
        return
    if hasattr(shell, "select_domain"):
        try:
            shell.select_domain("system", navigate_first=False)
        except Exception:
            pass
    if hasattr(shell, "navigate"):
        try:
            shell.navigate(MODULE_ID)
            return
        except Exception as exc:
            show_error(parent, f"无法打开扩展：{exc}")
            return
    show_error(parent, "无法打开扩展管理")


def open_new_plugin_scaffold(parent=None) -> Path | None:
    open_extension_hub(parent)
    return None
