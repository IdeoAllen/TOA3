# -*- coding: utf-8 -*-
"""产品愿景文案：config/product.yml → 首页 / 关于公示。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from services.config_service import project_root

_DEFAULTS: dict[str, Any] = {
    "tagline": "办公极简伴侣 · 少点一下，多干一件事",
    "mission_label": "使命",
    "statement": "让办公人员感到极致简便——打开就能用，用完不想换别的软件。",
    "goal": "成为办公室工作人员最爱、最方便、最离不开的桌面办公软件。",
    "integration": (
        "每个能力都对标市面同类工具；我们只是集成到一处，免去到处找"
        "——绝对不能比同类差，否则就是败笔。"
    ),
    "suite_positioning": (
        "办公室人员安装本软件，即等于集成剪贴板、截图、目录、文件、桌面、"
        "业务等常用办公效率工具——一站替代多软件来回切换。"
    ),
    "naming_note": "正式俏皮名稍后共创；现阶段以「运营宝 / TOA」示人。",
    "audience": "培训运营、教务、行政与通用白领",
    "promises": [
        "高频刚需做强；每项对标品类头部，宁少勿滥",
        "同类能力一站集成，少到处找软件",
        "键位跟手、步骤尽量少",
        "本地优先、可离线，结果本机可追溯",
    ],
}


@lru_cache(maxsize=1)
def load_vision() -> dict[str, Any]:
    path = project_root() / "config" / "product.yml"
    data: dict[str, Any] = dict(_DEFAULTS)
    if not path.is_file():
        return data
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        vision = doc.get("vision") or {}
        if isinstance(vision, dict):
            for k, v in vision.items():
                if v is not None and v != "":
                    data[k] = v
    except Exception:
        pass
    return data


def clear_vision_cache() -> None:
    load_vision.cache_clear()


def tagline() -> str:
    """对外使命句（历史字段名 tagline，语义为使命）。"""
    return str(load_vision().get("tagline") or _DEFAULTS["tagline"])


def mission_label() -> str:
    return str(load_vision().get("mission_label") or "使命")


def integration_line() -> str:
    return str(load_vision().get("integration") or _DEFAULTS["integration"])


def vision_display_rows() -> list[tuple[str, str]]:
    """首页 / 关于共用：(标签, 正文)。使命 · 愿景 · 目标 · 定位，文案同源不合并。"""
    v = load_vision()
    rows: list[tuple[str, str]] = []
    tag = str(v.get("tagline") or "").strip()
    if tag:
        rows.append((str(v.get("mission_label") or "使命"), tag))
    for key, label in (
        ("statement", "愿景"),
        ("goal", "目标"),
        ("suite_positioning", "套件"),
        ("integration", "定位"),
    ):
        text = str(v.get(key) or "").strip()
        if text:
            rows.append((label, text))
    return rows


def vision_home_lines() -> list[tuple[str, str]]:
    """兼容旧调用 → vision_display_rows。"""
    return vision_display_rows()


def vision_about_rows() -> list[tuple[str, str]]:
    """兼容旧调用 → vision_display_rows。"""
    return vision_display_rows()


def vision_public_text(*, compact: bool = False) -> str:
    """公示正文（文档 / 兼容旧调用；关于弹窗请用 vision_about_rows）。"""
    v = load_vision()
    tag = str(v.get("tagline") or "")
    statement = str(v.get("statement") or "")
    goal = str(v.get("goal") or "")
    integ = str(v.get("integration") or "")
    naming = str(v.get("naming_note") or "")
    audience = str(v.get("audience") or "")
    promises = v.get("promises") or []
    if not isinstance(promises, list):
        promises = []
    mlabel = str(v.get("mission_label") or "使命")

    if compact:
        parts = [p for p in (f"{mlabel}：{tag}" if tag else "", statement, goal, integ) if p]
        return "\n".join(parts)

    lines = [
        f"【{mlabel}】",
        tag,
        "",
        "【产品愿景】",
        statement,
        "",
        "【我们的目标】",
        goal,
        "",
        "【能力定位】",
        integ,
        "",
        f"服务对象：{audience}" if audience else "",
        "",
        "【我们承诺】",
    ]
    for p in promises:
        s = str(p).strip()
        if s:
            lines.append(f"· {s}")
    if naming:
        lines.extend(["", f"命名：{naming}"])
    return "\n".join(line for line in lines if line is not None).strip()
