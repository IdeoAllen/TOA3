# -*- coding: utf-8 -*-
"""AI 去水印 / 图像修复（占位，可接本地模型或云端）。"""
from __future__ import annotations

import logging
from typing import Any

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config

logger = logging.getLogger(__name__)


class WatermarkAiClient(IntegrationClient):
    name = "watermark_ai"

    def __init__(self) -> None:
        super().__init__(integration_config("watermark_ai"))

    def health_check(self) -> bool:
        return self.enabled and bool(self._config.get("provider"))

    def remove_watermark(self, image_path: str, mask: Any = None, **kwargs: Any) -> str:
        self.require_enabled()
        raise self.integration_error(
            "去水印模型待接入",
            user_message="AI 去水印尚未配置，当前可使用「去除图片水印」本地框选（迁移中）。",
        )
