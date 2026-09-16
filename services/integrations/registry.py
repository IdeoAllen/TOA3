# -*- coding: utf-8 -*-
"""三方对接注册表。"""
from __future__ import annotations

from services.integrations.config import integration_enabled, load_integrations_config
from services.integrations.dms_license import DmsLicenseClient
from services.integrations.dingtalk_client import DingtalkClient
from services.integrations.image_gen_client import ImageGenClient
from services.integrations.llm_client import LlmClient
from services.integrations.ocr_client import OcrClient
from services.integrations.tencent_docs_client import TencentDocsClient
from services.integrations.video_gen_client import VideoGenClient
from services.integrations.watermark_ai_client import WatermarkAiClient

_REGISTRY = {
    "dms": DmsLicenseClient,
    "ocr": OcrClient,
    "llm": LlmClient,
    "image_gen": ImageGenClient,
    "video_gen": VideoGenClient,
    "watermark_ai": WatermarkAiClient,
    "tencent_docs": TencentDocsClient,
    "dingtalk": DingtalkClient,
}


def list_integrations() -> list[str]:
    return list(_REGISTRY.keys())


def get_client(name: str):
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"未登记的 integration: {name}")
    return cls()


def summary() -> dict[str, bool]:
    cfg = load_integrations_config()
    out: dict[str, bool] = {}
    for name in _REGISTRY:
        out[name] = integration_enabled(name)
    for name, block in cfg.items():
        if name not in out and isinstance(block, dict):
            out[name] = bool(block.get("enabled"))
    return out


def status_lines(*, probe: bool = False) -> list[str]:
    """能力总览文案（人话标签，不直接甩内部 id）。

    probe=False（默认）：只看配置开关，不发起网络请求——设置页打开时必须走这条。
    probe=True：对已启用项调用 health_check（仅用户点「刷新状态」时使用）。
    """
    labels = {
        "dms": "授权服务",
        "ocr": "截图识字",
        "llm": "大模型",
        "image_gen": "图像生成",
        "video_gen": "视频生成",
        "watermark_ai": "智能去水印",
        "tencent_docs": "腾讯文档",
        "dingtalk": "钉钉",
        "email": "邮件",
    }
    lines: list[str] = []
    for name in sorted(summary().keys()):
        client = get_client(name) if name in _REGISTRY else None
        enabled = integration_enabled(name)
        state = "已启用" if enabled else "未启用"
        if enabled and probe and client is not None:
            try:
                ok = bool(client.health_check())
            except Exception:
                ok = False
            state += " · 连通" + ("正常" if ok else "异常/待配置")
        elif enabled:
            state += " · 已配置（点刷新探测）"
        title = labels.get(name, name)
        lines.append(f"{title}：{state}")
    return lines
