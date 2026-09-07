#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大模型助手极简范式冒烟：选模型列表 + 两步绑定校验。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from modules.llm_assistant.llm_simple_setup_dialog import (
        _SIMPLE_SOURCES,
        bind_text_llm_simple,
    )
    from services.model_catalog import get_active_profile_id, list_profiles, set_active_profile_id

    ids = {str(p.get("id") or "") for p in list_profiles("text_llm")}
    for pid, _label, _kind in _SIMPLE_SOURCES:
        assert pid in ids, f"catalog missing {pid}"

    prev = get_active_profile_id("text_llm")

    ok, msg = bind_text_llm_simple("deepseek", api_key="")
    assert not ok, msg
    assert "Key" in msg or "密钥" in msg or "粘贴" in msg, msg
    print(f"  cloud without key rejected: {msg}")

    ok2, msg2 = bind_text_llm_simple("ollama_local", api_key="", model="llama3.2")
    assert ok2, msg2
    assert get_active_profile_id("text_llm") == "ollama_local"
    print(f"  ollama bind OK: {msg2}")

    # 尽量恢复原默认，避免污染本机偏好
    if prev and prev != "ollama_local":
        try:
            set_active_profile_id("text_llm", prev)
        except Exception:
            pass

    print("VERIFY llm_simple_paradigm OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
