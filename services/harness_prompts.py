# -*- coding: utf-8 -*-
"""Harness 快捷指令模板。"""
from __future__ import annotations

from typing import Any

from services.harness_config import load_harness_config

_DEFAULT_PROMPTS: list[dict[str, str]] = [
    {
        "label": "去做扩展",
        "text": (
            "请引导用户去 TOA 创建扩展，不要让他改占位脚本、不要二次编辑超长提示词。\n"
            "正确入口：顶栏「系统」→「扩展」→「自定义插件」。\n"
            "必填：① 名称 ② 需求描述（场景、痛点、作用、主路径）。\n"
            "点「创建并去开发」后系统会自动投喂 skill「toa3-sop-user-extension」，"
            "智能体只改扩展沙箱目录。\n"
            "若用户已在聊天里写了需求，请复述要点并请其到扩展页粘贴后创建。"
        ),
    },
    {
        "label": "工作场景",
        "text": (
            "用户想用 TOA「工作场景」玩法，而不是从零架构。"
            "请提示：打开 TOA → 顶栏「系统」→「扩展」→ 选场景模板（日报/粘贴整理/台卡）→「复制为我的扩展」；"
            "若要加深，再点「回到开发」。不要改宿主。用户补充需求："
        ),
    },
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
    """合并配置与默认项；「去做扩展」「工作场景」置顶。"""
    pinned = [dict(_DEFAULT_PROMPTS[0]), dict(_DEFAULT_PROMPTS[1])]
    cfg = load_harness_config(force=True)
    raw = cfg.get("quick_prompts")
    out: list[dict[str, str]] = list(pinned)
    seen = {p["label"] for p in pinned}
    # 旧标签「一句话扩展」视为已废弃，不覆盖新「去做扩展」
    deprecated = {"一句话扩展"}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            text = str(item.get("text") or "").strip()
            if not label or not text or label in deprecated:
                continue
            if label == pinned[0]["label"]:
                out[0] = {"label": label, "text": text}
                continue
            if label == pinned[1]["label"]:
                out[1] = {"label": label, "text": text}
                continue
            if label in seen:
                continue
            seen.add(label)
            out.append({"label": label, "text": text})
    for p in _DEFAULT_PROMPTS[2:]:
        if p["label"] not in seen:
            out.append(dict(p))
            seen.add(p["label"])
    return out


def prompt_by_label(label: str) -> dict[str, str] | None:
    key = (label or "").strip()
    for p in list_quick_prompts():
        if p.get("label") == key:
            return p
    return None
