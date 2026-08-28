# -*- coding: utf-8 -*-
"""Harness 快捷指令模板。"""
from __future__ import annotations

from typing import Any

from services.harness_config import load_harness_config

_DEFAULT_PROMPTS: list[dict[str, str]] = [
    {
        "label": "读架构",
        "text": "请阅读当前工作区目录结构，按 modules/services/app 分层总结职责与入口，标出我下一步改代码应先读哪些文件。",
    },
    {
        "label": "最小修复",
        "text": "根据下列现象做根因分析，给出最小 diff 修复方案（先说明再改）：",
    },
    {
        "label": "写验收",
        "text": "为下列功能写 5 条可手测的验收步骤（含失败提示），格式：操作 → 期望：",
    },
    {
        "label": "对照 TOA2",
        "text": "对照 TOA2 同类模块，列出 TOA3 还缺的能力与建议迁移顺序：",
    },
    {
        "label": "生成脚本",
        "text": "写一段可在本机直接运行的 Python/PowerShell 脚本完成下列任务，附运行说明：",
    },
]


def list_quick_prompts() -> list[dict[str, str]]:
    cfg = load_harness_config()
    raw = cfg.get("quick_prompts")
    if isinstance(raw, list) and raw:
        out: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            text = str(item.get("text") or "").strip()
            if label and text:
                out.append({"label": label, "text": text})
        if out:
            return out
    return list(_DEFAULT_PROMPTS)


def prompt_by_label(label: str) -> dict[str, str] | None:
    key = (label or "").strip()
    for p in list_quick_prompts():
        if p.get("label") == key:
            return p
    return None
