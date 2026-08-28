# -*- coding: utf-8 -*-
"""Harness 双表面：内嵌 WebEngine ↔ 系统浏览器（同一 URL）。"""
from __future__ import annotations

import webbrowser

from PySide6.QtGui import QGuiApplication

from services.harness_config import load_harness_config, save_harness_config, web_url

SURFACE_EMBED = "embed"
SURFACE_BROWSER = "browser"


def surface_mode() -> str:
    mode = str(load_harness_config().get("surface_mode") or SURFACE_EMBED).strip().lower()
    return mode if mode in (SURFACE_EMBED, SURFACE_BROWSER) else SURFACE_EMBED


def prefer_embed() -> bool:
    return surface_mode() == SURFACE_EMBED


def prefer_browser() -> bool:
    return surface_mode() == SURFACE_BROWSER


def set_surface_mode(mode: str) -> None:
    m = str(mode or SURFACE_EMBED).strip().lower()
    if m not in (SURFACE_EMBED, SURFACE_BROWSER):
        m = SURFACE_EMBED
    save_harness_config({"surface_mode": m})


def open_in_system_browser() -> str:
    url = web_url()
    webbrowser.open(url)
    return url


def copy_web_url() -> bool:
    url = web_url()
    clip = QGuiApplication.clipboard()
    if clip is None:
        return False
    clip.setText(url)
    return True


def surface_status_label(running: bool, owned: bool) -> str:
    url = web_url()
    if not running:
        return "未运行"
    host = "TOA3 托管" if owned else "外部实例"
    mode = "内嵌" if prefer_embed() else "浏览器优先"
    return f"{host} · {mode} · {url}"
