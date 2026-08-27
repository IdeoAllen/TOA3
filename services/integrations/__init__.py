"""三方对接统一入口。"""

from services.integrations.registry import get_client, list_integrations, summary

__all__ = ["get_client", "list_integrations", "summary"]
