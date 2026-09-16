# -*- coding: utf-8 -*-
"""OCR 三方能力（默认本地 Tesseract；云端 provider 未实现）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config
from services.integrations.ocr_guide import resolve_tesseract_path, tessdata_dir_for

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
            path = resolve_tesseract_path(str(self._config.get("tesseract_path") or ""))
            return bool(path and Path(path).is_file())
        return False

    def _prepare_tesseract(self, **kwargs: Any):
        self.require_enabled()
        provider = str(self._config.get("provider") or "tesseract")
        if provider != "tesseract":
            raise self.integration_error(
                f"OCR provider={provider} 尚未实现",
                user_message=(
                    f"当前 OCR provider「{provider}」尚未接入。"
                    "请改用本地 Tesseract（小白默认本机完成，无需云端）。"
                ),
            )
        tess_path = resolve_tesseract_path(str(self._config.get("tesseract_path") or ""))
        if not tess_path or not Path(tess_path).is_file():
            raise self.integration_error(
                "tesseract_path 无效或不存在",
                user_message=(
                    "OCR 未就绪：本机还没有 Tesseract。\n\n"
                    "① 打开安装说明并安装（勾选 Chinese Simplified）：\n"
                    "https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "② 装好后到「图片转文字」点「启用中文识别」。\n\n"
                    "也可用系统设置 → 能力接入 填写 tesseract.exe 路径。"
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
        requested = str(kwargs.get("lang") or self._config.get("lang") or "eng")
        try:
            available = set(pytesseract.get_languages(config=""))
        except Exception:
            # 回退：扫 tessdata 目录（仍本机）
            td = tessdata_dir_for(tess_path)
            available = set()
            if td is not None and td.is_dir():
                for f in td.glob("*.traineddata"):
                    stem = f.stem.strip()
                    if stem and stem not in ("osd", "equ"):
                        available.add(stem)
            if not available:
                available = {"eng"}
        parts = [p.strip() for p in requested.replace(",", "+").split("+") if p.strip()]
        wants_chinese = any(p.lower() in ("chi_sim", "chi_tra") for p in parts)
        usable = [p for p in parts if p in available]
        if not usable:
            usable = ["eng"] if "eng" in available else list(available)[:1]
        lang = "+".join(usable) if usable else "eng"
        chinese_ready = "chi_sim" in available
        meta = {
            "tesseract_path": tess_path,
            "requested_lang": requested,
            "config_wants_chinese": wants_chinese,
            "chinese_ready": chinese_ready,
            "chinese_hint": "",
        }
        if wants_chinese and not chinese_ready:
            td = tessdata_dir_for(tess_path)
            folder = str(td) if td else "Tesseract\\tessdata"
            meta["chinese_hint"] = (
                "本次只用了英文包（缺 chi_sim）。"
                f"两步装中文：① 把 chi_sim.traineddata 放到 {folder}；"
                "② 打开「图片转文字」点「启用中文识别」。"
            )
        return pytesseract, Image, lang, available, meta

    def _pack_result(
        self,
        *,
        text: str,
        path: str,
        lang: str,
        available: set[str],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "text": text or "",
            "path": path,
            "lang": lang,
            "requested_lang": meta.get("requested_lang") or lang,
            "provider": "tesseract",
            "engine": "tesseract",
            "available_langs": sorted(available),
            "chinese_ready": bool(meta.get("chinese_ready")),
            "config_wants_chinese": bool(meta.get("config_wants_chinese")),
            "chinese_hint": str(meta.get("chinese_hint") or ""),
        }

    def recognize_image(self, image_path: str, **kwargs: Any) -> dict[str, Any]:
        """识别磁盘图片文字。"""
        pytesseract, Image, lang, available, meta = self._prepare_tesseract(**kwargs)
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
            hint = ""
            if meta.get("config_wants_chinese") and not meta.get("chinese_ready"):
                hint = "\n" + str(meta.get("chinese_hint") or "中文请安装 Tesseract chi_sim 语言包。")
            raise self.integration_error(
                str(exc),
                user_message=(
                    f"OCR 识别失败：{exc}\n"
                    f"当前语言={lang}；已安装={', '.join(sorted(available)) or '未知'}。"
                    f"{hint}"
                ),
            ) from exc
        return self._pack_result(
            text=text or "",
            path=str(src),
            lang=lang,
            available=available,
            meta=meta,
        )

    def recognize_pixmap(self, pixmap, **kwargs: Any) -> dict[str, Any]:
        """识别内存位图（截图直出，无需先选文件）。"""
        import io

        from PySide6.QtCore import QBuffer, QIODevice

        pytesseract, Image, lang, available, meta = self._prepare_tesseract(**kwargs)
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
            hint = ""
            if meta.get("config_wants_chinese") and not meta.get("chinese_ready"):
                hint = "\n" + str(meta.get("chinese_hint") or "")
            raise self.integration_error(
                str(exc),
                user_message=(
                    f"OCR 识别失败：{exc}\n"
                    f"当前语言={lang}；已安装={', '.join(sorted(available)) or '未知'}。"
                    f"{hint}"
                ),
            ) from exc
        return self._pack_result(
            text=text or "",
            path="",
            lang=lang,
            available=available,
            meta=meta,
        )
