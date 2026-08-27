# -*- coding: utf-8 -*-
"""三方对接基类：超时、日志、统一 IntegrationError。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from core.exceptions import IntegrationError

logger = logging.getLogger(__name__)


class IntegrationClient(ABC):
    """所有外部系统客户端的基类。"""

    name: str = "integration"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = dict(config or {})

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled"))

    @property
    def timeout(self) -> float:
        return float(self._config.get("timeout_seconds") or 30)

    def require_enabled(self) -> None:
        if not self.enabled:
            raise IntegrationError(self.name, f"{self.name} 未启用，请在 config/integrations.yml 配置")

    @abstractmethod
    def health_check(self) -> bool:
        """连通性探测（可选实现）。"""

    def integration_error(self, message: str, **kwargs) -> IntegrationError:
        return IntegrationError(self.name, message, **kwargs)
