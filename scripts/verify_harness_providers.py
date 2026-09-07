#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness 提供方：llm-pi-ai 不得混入 deepseek-official（否则添加提供方失效）。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _assert_defaults_never_write_official_into_pi() -> None:
    path = ROOT / "services" / "harness_model_defaults.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "ensure_official_default_model"
    )
    body = ast.get_source_segment(text, fn) or ""
    # 不得再出现向 llm-pi-ai.providers 写入 deepseek-official 的旧循环
    assert 'for pid in ("deepseek", _OFFICIAL_PROVIDER)' not in body
    assert "providers.pop(_OFFICIAL_PROVIDER" in body or 'providers.pop("deepseek-official"' in body


def _assert_runtime_settings_clean() -> None:
    from services.harness_model_defaults import (
        _OFFICIAL_PROVIDER,
        ensure_official_default_model,
        settings_path,
    )

    # 自愈：清掉历史脏数据
    ensure_official_default_model()
    path = settings_path()
    if not path.is_file():
        print("VERIFY harness_providers OK (no settings.yaml yet)")
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pi = data.get("llm-pi-ai") or {}
    providers = (pi.get("providers") if isinstance(pi, dict) else None) or {}
    assert isinstance(providers, dict)
    assert _OFFICIAL_PROVIDER not in providers, (
        f"llm-pi-ai.providers 仍含 {_OFFICIAL_PROVIDER}，会导致「添加提供方」点了无反应"
    )


def main() -> int:
    _assert_defaults_never_write_official_into_pi()
    _assert_runtime_settings_clean()
    print("VERIFY harness_providers OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
