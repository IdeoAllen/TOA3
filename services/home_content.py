# -*- coding: utf-8 -*-
"""首页 curated 内容：来自 config/product.yml · home，不随侧栏菜单整表渲染。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from services.config_service import project_root
from services.product_vision import load_vision


@lru_cache(maxsize=1)
def _load_product_root() -> dict[str, Any]:
    path = project_root() / "config" / "product.yml"
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _default_office_pins() -> list[dict[str, str]]:
    return [
        {"id": "quick_notepad", "title": "快速记事", "subtitle": "会议纪要草稿"},
        {"id": "screenshot_tool", "title": "截图工具", "subtitle": "区域 / 全屏"},
        {"id": "clipboard_history", "title": "剪贴板历史", "subtitle": "Alt+Shift+C 速贴"},
        {"id": "quadrant_tasks", "title": "四象限任务", "subtitle": "本地看板"},
        {"id": "pomodoro", "title": "番茄钟", "subtitle": "沉浸专注"},
    ]


def _default_suite_highlights() -> list[dict[str, str]]:
    return [
        {"id": "directory_generator", "title": "目录生成", "subtitle": "交付结构"},
        {"id": "batch_rename", "title": "批量重命名", "subtitle": "整理文件名"},
        {"id": "watermark_remover", "title": "去水印", "subtitle": "框选清理"},
        {"id": "column_preview", "title": "桌面浏览", "subtitle": "列式预览"},
    ]


def _normalize_cards(raw: Any, *, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        return list(fallback)
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or item.get("module_id") or "").strip()
        if not mid:
            continue
        out.append(
            {
                "id": mid,
                "title": str(item.get("title") or item.get("name") or mid),
                "subtitle": str(item.get("subtitle") or item.get("desc") or ""),
            }
        )
    return out or list(fallback)


def home_config() -> dict[str, Any]:
    block = _load_product_root().get("home")
    return block if isinstance(block, dict) else {}


def home_search_hint() -> str:
    return str(
        home_config().get("search_hint")
        or "点击顶栏 ⌂ 或按 Ctrl+K，输入关键字直达任一工作。"
    )


def home_advanced_note() -> str:
    return str(
        home_config().get("advanced_note")
        or (
            "文生图、视频、Harness 等高级算力请到「系统设置 → 模型管理」"
            "自行绑定 Key 或安装本机组件；向导式配置，无需手改配置文件。"
        )
    )


def home_office_pins() -> list[dict[str, str]]:
    return _normalize_cards(home_config().get("office_pins"), fallback=_default_office_pins())


def home_suite_highlights() -> list[dict[str, str]]:
    return _normalize_cards(
        home_config().get("suite_highlights"),
        fallback=_default_suite_highlights(),
    )


def home_promises() -> list[str]:
    promises = load_vision().get("promises") or []
    if not isinstance(promises, list):
        return []
    return [str(p).strip() for p in promises if str(p).strip()]
