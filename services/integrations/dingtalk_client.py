# -*- coding: utf-8 -*-
"""钉钉对接占位。"""
from __future__ import annotations

from typing import Any

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config


class DingtalkClient(IntegrationClient):
    name = "dingtalk"

    def __init__(self) -> None:
        super().__init__(integration_config("dingtalk"))

    def health_check(self) -> bool:
        return bool(self.enabled and self._config.get("webhook_url"))

    def send_markdown(self, title: str, text: str, **kwargs: Any) -> bool:
        self.require_enabled()
        raise self.integration_error(
            "钉钉通知待接入",
            user_message="钉钉尚未配置，请在 integrations.yml 填写 webhook 后接入。",
        )
