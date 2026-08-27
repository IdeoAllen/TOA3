# -*- coding: utf-8 -*-
"""OCR 三方能力（Tesseract / 云端 API）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config

logger = logging.getLogger(__name__)


class OcrClient(IntegrationClient):
    name = "ocr"

    def __init__(self) -> None:
        super().__init__(integration_config("ocr"))

    def health_check(self) -> bool:
        if not self.enabled:
            return False
        provider = str(self._config.get("provider") or "tesseract")
        if provider == "tesseract":
            path = str(self._config.get("tesseract_path") or "")
            if path:
                return Path(path).is_file()
        return False

    def _prepare_tesseract(self, **kwargs: Any):
        self.require_enabled()
        provider = str(self._config.get("provider") or "tesseract")
        if provider != "tesseract":
            raise self.integration_error(
                f"OCR provider={provider} 尚未实现",
                user_message=f"当前 OCR provider「{provider}」尚未接入，请改用 tesseract。",
            )
        tess_path = str(self._config.get("tesseract_path") or "").strip()
        if not tess_path or not Path(tess_path).is_file():
            raise self.integration_error(
                "tesseract_path 无效或不存在",
                user_message=(
                    "OCR 未就绪：请在 config/integrations.yml 配置可用的 tesseract_path"
                    "（例如 C:\\Program Files\\Tesseract-OCR\\tesseract.exe）。"
                ),
            )
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise self.integration_error(
                f"缺少依赖: {exc}",
                user_message="OCR 需要安装 pytesseract 与 Pillow：pip install pytesseract Pillow",
            ) from exc

        pytesseract.pytesseract.tesseract_cmd = tess_path
        lang = str(kwargs.get("lang") or self._config.get("lang") or "eng")
        try:
            available = set(pytesseract.get_languages(config=""))
        except Exception:
            available = {"eng"}
        parts = [p.strip() for p in lang.replace(",", "+").split("+") if p.strip()]
        usable = [p for p in parts if p in available]
        if not usable:
            usable = ["eng"] if "eng" in available else list(available)[:1]
        lang = "+".join(usable) if usable else "eng"
        return pytesseract, Image, lang, available

    def recognize_image(self, image_path: str, **kwargs: Any) -> dict[str, Any]:
        """识别磁盘图片文字。"""
        pytesseract, Image, lang, available = self._prepare_tesseract(**kwargs)
        src = Path(image_path)
        if not src.is_file():
            raise self.integration_error(
                f"图片不存在: {image_path}",
                user_message=f"找不到图片文件：{image_path}",
            )
        try:
            with Image.open(src) as im:
                text = pytesseract.image_to_string(im, lang=lang)
        except Exception as exc:
            logger.exception("OCR 识别失败")
            raise self.integration_error(
                str(exc),
                user_message=(
                    f"OCR 识别失败：{exc}\n"
                    f"当前语言={lang}；已安装={', '.join(sorted(available)) or '未知'}。"
                    "中文请安装 Tesseract chi_sim 语言包。"
                ),
            ) from exc
        return {
            "text": text or "",
            "path": str(src),
            "lang": lang,
            "provider": "tesseract",
            "engine": "tesseract",
        }

    def recognize_pixmap(self, pixmap, **kwargs: Any) -> dict[str, Any]:
        """识别内存位图（截图直出，无需先选文件）。"""
        import io

        from PySide6.QtCore import QBuffer, QIODevice

        pytesseract, Image, lang, available = self._prepare_tesseract(**kwargs)
        if pixmap is None or getattr(pixmap, "isNull", lambda: True)():
            raise self.integration_error(
                "空位图",
                user_message="没有可识别的截图内容。",
            )
        try:
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            if not pixmap.save(buf, "PNG"):
                raise RuntimeError("位图编码失败")
            im = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")
            text = pytesseract.image_to_string(im, lang=lang)
        except Exception as exc:
            logger.exception("OCR 位图识别失败")
            raise self.integration_error(
                str(exc),
                user_message=(
                    f"OCR 识别失败：{exc}\n"
                    f"当前语言={lang}；已安装={', '.join(sorted(available)) or '未知'}。"
                ),
            ) from exc
        return {
            "text": text or "",
            "path": "",
            "lang": lang,
            "provider": "tesseract",
            "engine": "tesseract",
        }
