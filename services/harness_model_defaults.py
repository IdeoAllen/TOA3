# -*- coding: utf-8 -*-
"""DSH settings.yaml：默认模型与官方 API Key 对齐。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from services.harness_config import dsh_home_path

logger = logging.getLogger(__name__)

# WorkBuddy 内置通道；无其私有凭证时历史会话/对话会「加载不到」
_MODLENS_PROVIDERS = frozenset({"deepseek-modlens", "modlens"})
_OFFICIAL_PROVIDER = "deepseek-official"
_OFFICIAL_MODEL = "deepseek-v4-pro"


def settings_path() -> Path:
    return dsh_home_path() / "settings.yaml"


def ensure_official_default_model() -> tuple[bool, str]:
    """若默认模型仍指向 WorkBuddy ModLens，改为官方 DeepSeek + DEEPSEEK_API_KEY。

    全新 DSH 目录无 settings.yaml 时直接写入官方默认。
    返回 (是否改写了文件, 说明)。
    """
    path = settings_path()
    raw = ""
    created = False
    if not path.is_file():
        data: dict[str, Any] = {}
        created = True
    else:
        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                data = {}
        except (OSError, yaml.YAMLError) as exc:
            return False, str(exc)

    cur = data.get("agent-default-model")
    if not isinstance(cur, dict):
        cur = {}
    provider = str(cur.get("provider") or "").strip().lower()
    model = str(cur.get("model") or "").strip()
    changed = created

    if provider in _MODLENS_PROVIDERS or not provider:
        data["agent-default-model"] = {
            "model": model if model.startswith("deepseek-") else _OFFICIAL_MODEL,
            "provider": _OFFICIAL_PROVIDER,
            "reasoningEffort": cur.get("reasoningEffort") or "high",
        }
        changed = True

    # llm-pi-ai 只接受 pi-ai 目录内的路由（如 deepseek / zai-coding-cn）。
    # 禁止写入 deepseek-official：它属于 llm-deepseek；混入会导致整个
    # llm-pi-ai 命名空间注册失败，「添加提供方」按钮点了无反应。
    pi = data.get("llm-pi-ai")
    if isinstance(pi, dict):
        providers = pi.get("providers")
        if isinstance(providers, dict) and _OFFICIAL_PROVIDER in providers:
            providers.pop(_OFFICIAL_PROVIDER, None)
            changed = True
            if not providers:
                # 空 dict 可保留；勿删整个 llm-pi-ai（用户可能还有其它路由）
                pass
        # 可选：确保官方 DeepSeek（pi-ai 目录路由）指向本机 Key
        if isinstance(providers, dict):
            entry = providers.get("deepseek")
            if isinstance(entry, dict) and not str(entry.get("apiKeyEnv") or "").strip():
                entry["apiKeyEnv"] = "DEEPSEEK_API_KEY"
                changed = True

    if not changed:
        return False, f"默认模型已是 {cur.get('provider')}/{cur.get('model')}"

    bak = path.with_suffix(".yaml.bak-toa3")
    try:
        if raw and not bak.is_file():
            bak.write_text(raw, encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                data, allow_unicode=True, default_flow_style=False, sort_keys=False
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        return False, str(exc)

    new = data.get("agent-default-model") or {}
    if created:
        msg = f"已写入默认模型 {new.get('provider')}/{new.get('model')}"
    else:
        msg = f"已将默认模型改为 {new.get('provider')}/{new.get('model')}（原为 ModLens/空，官方 Key 接不上）"
    logger.info(msg)
    return True, msg
