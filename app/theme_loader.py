# -*- coding: utf-8 -*-
"""主题：JSON 色板 → QSS 文件加载。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / "config" / "themes"
QSS_DIR = ROOT / "resources" / "qss"

DEFAULT_THEME = "dms_blue"

logger = logging.getLogger(__name__)


def project_root() -> Path:
    return ROOT


def list_theme_ids() -> list[str]:
    if not THEMES_DIR.is_dir():
        return [DEFAULT_THEME]
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def theme_display_name(theme_id: str) -> str:
    try:
        doc = load_theme_doc(theme_id)
        return str(doc.get("display_name") or theme_id)
    except Exception:
        return theme_id


def theme_json_path(theme_id: str) -> Path:
    return THEMES_DIR / f"{theme_id}.json"


def qss_path(theme_id: str) -> Path:
    return QSS_DIR / f"{theme_id}.qss"


def load_theme_doc(theme_id: str) -> dict:
    path = theme_json_path(theme_id)
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_palette(theme_id: str) -> dict:
    doc = load_theme_doc(theme_id)
    pal = doc.get("palette") or {}
    return {k: str(v) for k, v in pal.items() if isinstance(v, str)}


def ensure_qss(theme_id: str) -> Path:
    """若 QSS 缺失则从 JSON 自动生成（MVP 避免手工跑脚本）。"""
    out = qss_path(theme_id)
    if out.is_file():
        return out
    QSS_DIR.mkdir(parents=True, exist_ok=True)
    from scripts.gen_qss_from_theme import build_qss, resolve_arrow_placeholders

    doc = load_theme_doc(theme_id)
    pal = doc.get("palette") or {}
    qss = resolve_arrow_placeholders(build_qss(pal), theme_id, pal)
    out.write_text(qss.strip() + "\n", encoding="utf-8")
    logger.info("已自动生成 QSS: %s", out.name)
    return out


def ensure_official_qss() -> int:
    """为所有已同步的官方 JSON 主题生成 QSS。"""
    from services.theme_catalog import official_theme_ids

    n = 0
    for tid in official_theme_ids():
        if not theme_json_path(tid).is_file():
            continue
        if not qss_path(tid).is_file():
            ensure_qss(tid)
            n += 1
    return n


def read_qss(theme_id: str) -> str:
    path = ensure_qss(theme_id)
    return path.read_text(encoding="utf-8")


def apply_theme(app, theme_id: str = DEFAULT_THEME) -> dict:
    """对 QApplication 应用 QSS，并更新 AppState。"""
    qss = read_qss(theme_id)
    app.setStyleSheet(qss)
    palette = load_palette(theme_id)
    try:
        from app.app_state import AppState

        AppState.get().set_theme(theme_id, palette)
    except Exception:
        pass
    return palette


def resolve_default_theme() -> str:
    try:
        from services.config_service import get_ui_config
        from services.theme_catalog import canonicalize_theme

        ui = get_ui_config()
        tid = str(ui.get("theme") or "").strip()
        if tid:
            return canonicalize_theme(tid)
    except Exception:
        pass
    return DEFAULT_THEME
