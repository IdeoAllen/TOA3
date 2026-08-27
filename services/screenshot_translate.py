# -*- coding: utf-8 -*-
"""截图翻译：OCR → LLM 译文（经 integrations，禁止业务直连 HTTP）。"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtGui import QPixmap

logger = logging.getLogger("TOA3.screenshot_translate")


def ocr_only(pixmap: QPixmap) -> str:
    """仅 OCR，不调 LLM（翻译按钮先出原文，再由用户点翻译）。"""
    if pixmap is None or pixmap.isNull():
        raise ValueError("无有效截图")

    tmp = Path(tempfile.gettempdir()) / "toa3_shot_translate.png"
    if not pixmap.save(str(tmp), "PNG"):
        raise RuntimeError("临时截图保存失败")

    from services.integrations import get_client

    ocr = get_client("ocr")
    result = ocr.recognize_image(str(tmp))
    return str(result.get("text") or "").strip()


def ocr_and_translate(pixmap: QPixmap) -> tuple[str, str]:
    """返回 (原文, 译文)。失败时译文为空并抛出带 user_message 的异常由调用方处理。"""
    source = ocr_only(pixmap)
    if not source:
        return "", ""

    from services.integrations import get_client

    llm = get_client("llm")
    translated = llm.complete(
        source,
        system=(
            "你是翻译助手。将用户给出的屏幕文字译为简体中文；"
            "若原文已是中文则译为英文。只输出译文，不要解释。"
        ),
        temperature=0.2,
    )
    return source, str(translated or "").strip()
