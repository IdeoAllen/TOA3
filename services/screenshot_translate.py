# -*- coding: utf-8 -*-
"""截图翻译：OCR → LLM 译文（经 integrations，禁止业务直连 HTTP）。"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

logger = logging.getLogger("TOA3.screenshot_translate")

TRANSLATE_SYSTEM = (
    "你是翻译助手。将用户给出的屏幕文字译为简体中文；"
    "若原文已是中文则译为英文。只输出译文，不要解释。"
)

# 对照窗占位（尚未点「翻译原文」）
PLACEHOLDER_TRANSLATED = "（原文已复制。点下方「翻译原文」生成译文。）"


def _require_pixmap(pixmap: QPixmap | None) -> QPixmap:
    if pixmap is None or pixmap.isNull():
        raise ValueError("无有效截图")
    return pixmap


def ocr_only(pixmap: QPixmap) -> str:
    """仅 OCR，不调 LLM（翻译按钮先出原文，再由用户点翻译）。

    可在后台线程调用；禁止在 UI 线程对云端 OCR 同步长阻塞时，请用
    :class:`OcrWorker` 或 :func:`services.screenshot_translate_dialog.launch_translate_from_pixmap`。
    """
    pix = _require_pixmap(pixmap)
    from services.integrations import get_client

    ocr = get_client("ocr")
    # 优先内存位图，避免临时文件
    recognize_pixmap = getattr(ocr, "recognize_pixmap", None)
    if callable(recognize_pixmap):
        result = recognize_pixmap(pix)
    else:
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.gettempdir()) / "toa3_shot_translate.png"
        if not pix.save(str(tmp), "PNG"):
            raise RuntimeError("临时截图保存失败")
        result = ocr.recognize_image(str(tmp))
    return str((result or {}).get("text") or "").strip()


def translate_text(source: str, *, profile_id: str | None = None) -> str:
    """将原文译为译文（经 llm integration）。可在后台线程调用。"""
    text = (source or "").strip()
    if not text:
        return ""
    from services.integrations import get_client

    llm = get_client("llm")
    kwargs: dict[str, Any] = {
        "system": TRANSLATE_SYSTEM,
        "temperature": 0.2,
    }
    if profile_id:
        kwargs["profile_id"] = profile_id
    translated = llm.complete(text, **kwargs)
    return str(translated or "").strip()


def ocr_and_translate(pixmap: QPixmap) -> tuple[str, str]:
    """返回 (原文, 译文)。供脚本/批处理；UI 请分步 OCR + 对照窗翻译。"""
    source = ocr_only(pixmap)
    if not source:
        return "", ""
    return source, translate_text(source)


class OcrWorker(QObject):
    """后台 OCR，避免 UI 线程同步长联网/本地重识别。"""

    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self._pixmap = pixmap

    def run(self) -> None:
        try:
            text = ocr_only(self._pixmap)
            self.finished.emit(text)
        except Exception as exc:
            from core.exceptions import format_exception

            msg = getattr(exc, "user_message", None) or format_exception(exc)
            self.failed.emit(str(msg))
