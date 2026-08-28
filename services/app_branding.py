# -*- coding: utf-8 -*-
"""应用品牌资源：开发版 / 正式版图标与 Logo 路径。"""
from __future__ import annotations

from pathlib import Path

from services.config_service import project_root
from services.runtime_paths import get_runtime_environment


def is_development_profile() -> bool:
    """源码运行或打包目录含 BUILD_PROFILE.dev 时为开发版。"""
    return get_runtime_environment() == "development"


def brand_icon_stem() -> str:
    return "logo_dev" if is_development_profile() else "logo"


def resolve_app_icon_png() -> Path | None:
    icons = project_root() / "resources" / "icons"
    if is_development_profile():
        dev = icons / "app_logo_dev.png"
        if dev.is_file():
            return dev
    release = icons / "app_logo.png"
    return release if release.is_file() else None


def resolve_app_icon_ico() -> Path | None:
    icons = project_root() / "resources" / "icons"
    avatars = project_root() / "avatars"
    if is_development_profile():
        for p in (avatars / "logo_dev.ico", icons / "app_logo_dev.ico"):
            if p.is_file():
                return p
    for p in (avatars / "logo.ico", icons / "app_logo.ico"):
        if p.is_file():
            return p
    return None


def resolve_brand_logo_png() -> Path | None:
    icons = project_root() / "resources" / "icons"
    if is_development_profile():
        dev = icons / "brand_logo_dev.png"
        if dev.is_file():
            return dev
    for name in ("brand_logo.png", "app_logo.png"):
        p = icons / name
        if p.is_file():
            return p
    avatars = project_root() / "avatars"
    stem = brand_icon_stem()
    p = avatars / f"{stem}.png"
    return p if p.is_file() else None
