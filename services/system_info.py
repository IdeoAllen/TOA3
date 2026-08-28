# -*- coding: utf-8 -*-
"""系统品牌与版本信息（配置 + 用户覆盖 + app/version）。"""
from __future__ import annotations

from pathlib import Path

from app.app_state import AppState
from app.version import APP_NAME, APP_VERSION, build_profile_label
from services.config_service import load_config, project_root, resolve_path
from services.user_system_info import load_user_overrides


def _brand_block() -> dict:
    cfg = load_config()
    base: dict = {}
    for key in ("brand", "brand_and_system", "system_info", "system_info_config"):
        block = cfg.get(key)
        if isinstance(block, dict) and block:
            base = dict(block)
            break
    overrides = load_user_overrides()
    if overrides:
        base.update(overrides)
    return base


def get_system_info() -> dict:
    brand = _brand_block()
    st = AppState.get()
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "build_profile": build_profile_label(),
        "brand_name": str(brand.get("brand_name") or st.brand_name()),
        "brand_alias": str(brand.get("brand_alias") or "运营宝"),
        "brand_abbreviation": str(brand.get("brand_abbreviation") or "TOA"),
        "brand_name_en": str(brand.get("brand_name_en") or brand.get("app_name_en") or ""),
        "slogan": str(brand.get("slogan") or brand.get("main_slogan") or ""),
        "slogan_subtitle": str(
            brand.get("slogan_subtitle") or brand.get("sub_slogan") or ""
        ),
        "author": str(brand.get("author") or ""),
        "author_email": str(
            brand.get("author_email") or brand.get("author_contact") or ""
        ),
        "window_title": str(brand.get("window_title") or ""),
        "config_app_version": str(brand.get("app_version") or ""),
        "app_logo_path": str(brand.get("app_logo_path") or "").strip(),
    }


def logo_path() -> Path | None:
    brand = _brand_block()
    rel = str(brand.get("app_logo_path") or "").strip()
    # 顶栏优先高清 PNG（SVG 内嵌文字在 QtSvg 下易发糊）
    candidates: list[Path] = [
        project_root() / "resources" / "icons" / "brand_logo.png",
        project_root() / "resources" / "icons" / "brand_logo.svg",
    ]
    if rel:
        p = Path(rel)
        if not p.is_absolute():
            p = project_root() / p
        candidates.append(p)
        candidates.append(resolve_path("data_dir") / rel)
    candidates.extend(
        [
            project_root() / "avatars" / "logo.png",
            project_root() / "resources" / "icons" / "app_logo.png",
            project_root() / "resources" / "icons" / "app_logo.ico",
        ]
    )
    toa2 = project_root().parent / "TOA" / "avatars" / "logo.png"
    candidates.append(toa2)
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


def log_directory() -> Path:
    return resolve_path("log_dir")
