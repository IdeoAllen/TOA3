# -*- coding: utf-8 -*-
"""TOA3 异常体系：业务错误与 UI 展示分离。"""
from __future__ import annotations


class TOAError(Exception):
    """应用级可恢复错误基类。"""

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        code: str = "TOA_ERROR",
        detail: str | None = None,
    ):
        super().__init__(message)
        self.user_message = user_message or message
        self.code = code
        self.detail = detail or message


class ConfigError(TOAError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="CONFIG_ERROR", **kwargs)


class ThemeError(TOAError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="THEME_ERROR", **kwargs)


class ModuleLoadError(TOAError):
    def __init__(self, module_id: str, message: str, **kwargs):
        super().__init__(message, code="MODULE_LOAD_ERROR", **kwargs)
        self.module_id = module_id


class AuthError(TOAError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="AUTH_ERROR", **kwargs)


class ValidationError(TOAError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="VALIDATION_ERROR", **kwargs)


class IntegrationError(TOAError):
    def __init__(self, service: str, message: str, **kwargs):
        super().__init__(message, code="INTEGRATION_ERROR", **kwargs)
        self.service = service


class SecurityError(TOAError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="SECURITY_ERROR", **kwargs)


def format_exception(exc: BaseException) -> str:
    if isinstance(exc, TOAError):
        return exc.user_message
    return str(exc) or exc.__class__.__name__
