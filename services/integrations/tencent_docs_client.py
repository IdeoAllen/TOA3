# -*- coding: utf-8 -*-
"""腾讯文档对接占位（后续 OAuth / API）。"""
from __future__ import annotations

import logging
from typing import Any

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config

logger = logging.getLogger(__name__)


class TencentDocsClient(IntegrationClient):
    """业务禁止直连 URL；一律 get_client('tencent_docs')。"""

    name = "tencent_docs"

    def __init__(self) -> None:
        super().__init__(integration_config("tencent_docs"))

    def health_check(self) -> bool:
        if not self.enabled:
            return False
        # 占位：有 base_url 即视为已配置待联调
        return bool(str(self._config.get("base_url") or "").strip())

    def list_docs(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.require_enabled()
        raise self.integration_error(
            "腾讯文档 list_docs 待接入",
            user_message="腾讯文档尚未对接，请在 integrations.yml 配置后等待后续版本。",
        )

    def export_doc(self, doc_id: str, *, fmt: str = "docx") -> str:
        self.require_enabled()
        raise self.integration_error(
            "腾讯文档 export_doc 待接入",
            user_message="腾讯文档导出尚未对接。",
        )
