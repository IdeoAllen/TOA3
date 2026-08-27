# -*- coding: utf-8 -*-
"""应用全局状态（单例）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AppState:
    """运行时状态：主题、用户、当前模块。"""

    theme_id: str = "dms_blue"
    username: str = ""
    display_name: str = ""
    role: str = ""
    is_authenticated: bool = False
    current_module_id: str = ""
    palette: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)

    _instance: Optional["AppState"] = None

    @classmethod
    def get(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = AppState()
        return cls._instance

    def set_user(
        self,
        username: str,
        display_name: str | None = None,
        *,
        role: str = "",
    ) -> None:
        self.username = username
        self.display_name = display_name or username
        self.role = str(role or "").strip()
        self.is_authenticated = bool(username)

    def set_theme(self, theme_id: str, palette: dict | None = None) -> None:
        self.theme_id = theme_id
        if palette:
            self.palette = dict(palette)

    def set_module(self, module_id: str) -> None:
        self.current_module_id = module_id

    def brand_name(self) -> str:
        brand = self.config.get("brand") or self.config.get("brand_and_system") or {}
        if isinstance(brand, dict):
            return str(brand.get("brand_name") or brand.get("brand_alias") or "运营宝")
        return "运营宝"

    def app_version(self) -> str:
        try:
            from app.version import APP_VERSION

            return APP_VERSION
        except Exception:
            pass
        brand = self.config.get("brand") or self.config.get("brand_and_system") or {}
        if isinstance(brand, dict):
            ver = str(brand.get("app_version") or "").strip()
            if ver:
                return ver
        return "3.0.0-MVP"
