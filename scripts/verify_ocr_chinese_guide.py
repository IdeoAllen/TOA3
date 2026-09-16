#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR 中文引擎引导冒烟：本机探测分支 + ≤2 步文案（无进页联网）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _assert_steps_le2(st, label: str) -> None:
    assert len(st.steps) <= 2, f"{label}: steps={st.steps!r}"
    text = st.guide_text()
    assert text, f"{label}: empty guide"
    # 禁止把「手改 yml」当成小白主路径
    assert "手改 yml" not in text.lower()


def main() -> int:
    from services.integrations.ocr_guide import (
        ENGINE_CONCLUSION,
        chinese_warning_for_result,
        probe_chinese_status,
        resolve_tesseract_path,
    )

    assert ENGINE_CONCLUSION == "tesseract_local"

    # 分支：缺语言包（注入 langs，不依赖本机是否真有 chi_sim）
    missing = probe_chinese_status(force_langs=["eng", "osd"])
    assert missing.code == "missing_lang", missing
    assert missing.chinese_ready is False
    assert len(missing.steps) == 2, missing.steps
    _assert_steps_le2(missing, "missing_lang")
    assert "chi_sim" in missing.guide_text()
    print(f"  missing_lang OK: {missing.steps[0][:48]}…")

    # 分支：有包待启用
    need = probe_chinese_status(force_langs=["eng", "chi_sim"])
    assert need.chinese_ready is True
    assert need.code in ("ready", "need_enable"), need.code
    assert len(need.steps) <= 1, need.steps
    print(f"  chi_sim present → {need.code}")

    # 结果回落提示
    tip = chinese_warning_for_result(
        {
            "chinese_ready": False,
            "config_wants_chinese": True,
            "chinese_hint": "缺 chi_sim，请两步安装。",
        }
    )
    assert tip and "chi_sim" in tip
    assert chinese_warning_for_result({"chinese_ready": True}) == ""
    print("  chinese_warning_for_result OK")

    # 路径解析：不抛、不联网
    path = resolve_tesseract_path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    print(f"  resolve_tesseract_path → {path or '(empty)'}")

    # 本机实况（仅打印，不作为失败条件）
    live = probe_chinese_status()
    print(
        f"  live: code={live.code} tess_ok={live.tesseract_ok} "
        f"chi_sim={live.chinese_ready} langs={live.available_langs}"
    )
    _assert_steps_le2(live, "live") if live.steps else None

    # 进页契约：ocr_tool on_enter 不做探测（静态抽查源码）
    page = (ROOT / "modules" / "ocr_tool" / "ocr_tool_page.py").read_text(encoding="utf-8")
    assert "def on_enter" in page
    assert "probe_chinese_status" not in page.split("def on_enter")[1].split("def ")[0]
    assert "启用中文识别" in page
    assert "打开语言包文件夹" in page
    print("  ocr_tool_page: on_enter 无探测；引导按钮在位")

    print("VERIFY ocr_chinese_guide OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
