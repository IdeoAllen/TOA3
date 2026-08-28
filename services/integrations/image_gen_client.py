# -*- coding: utf-8 -*-
"""图像生成（本地 SD WebUI / OpenAI 兼容）。"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config
from services.model_catalog import resolve_image_gen_profile

logger = logging.getLogger(__name__)


class ImageGenClient(IntegrationClient):
    name = "image_gen"

    def __init__(self) -> None:
        super().__init__(integration_config("image_gen"))

    def health_check(self) -> bool:
        if not self.enabled:
            return False
        try:
            prof = resolve_image_gen_profile()
        except KeyError:
            return False
        provider = str(prof.get("provider") or "").strip()
        if provider in ("sd_webui", "comfyui"):
            base = str(prof.get("api_base") or "").strip().rstrip("/")
            return bool(base)
        return bool(str(prof.get("api_base") or "").strip())

    def _api_key(self, prof: dict[str, Any]) -> str:
        from services.integrations.secrets import get_profile_secret

        pid = str(prof.get("id") or "")
        cap = str(prof.get("capability") or "image_gen")
        return str(
            get_profile_secret(cap, pid, "api_key")
            or self._config.get("api_key")
            or os.environ.get("TOA_IMAGE_GEN_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()

    def generate(
        self,
        prompt: str,
        *,
        width: int = 512,
        height: int = 512,
        profile_id: str | None = None,
    ) -> Path:
        self.require_enabled()
        text = str(prompt or "").strip()
        if not text:
            raise self.integration_error("prompt 为空", user_message="请先填写画面描述。")
        prof = resolve_image_gen_profile(profile_id)
        provider = str(prof.get("provider") or "").strip()
        if provider == "sd_webui":
            return self._sd_webui(prof, text, width=width, height=height)
        if provider == "comfyui":
            return self._comfyui(prof, text, width=width, height=height)
        if provider == "openai_images":
            return self._openai_images(prof, text, width=width, height=height)
        raise self.integration_error(
            f"未知 provider: {provider}",
            user_message=f"图像生成配置不支持：{provider}",
        )

    def _sd_webui(
        self,
        prof: dict[str, Any],
        prompt: str,
        *,
        width: int,
        height: int,
    ) -> Path:
        base = str(prof.get("api_base") or "http://127.0.0.1:7860").strip().rstrip("/")
        url = urljoin(base + "/", "sdapi/v1/txt2img")
        steps = int(prof.get("steps") or 20)
        body: dict[str, Any] = {
            "prompt": prompt,
            "width": max(64, min(2048, int(width))),
            "height": max(64, min(2048, int(height))),
            "steps": max(1, min(60, steps)),
            "cfg_scale": 7,
            "sampler_name": str(prof.get("sampler") or "Euler a"),
        }
        ckpt = str(prof.get("model") or "").strip()
        if ckpt:
            body["override_settings"] = {"sd_model_checkpoint": ckpt}
        payload = self._post_json(url, body, headers={"Content-Type": "application/json"})
        images = payload.get("images") or []
        if not images:
            raise self.integration_error("sd_webui 无图像", user_message="本地 WebUI 未返回图像，请检查是否已加载模型。")
        raw = images[0]
        if isinstance(raw, str) and raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        data = base64.b64decode(raw)
        return self._write_output(data, suffix=".png")

    def _comfyui(
        self,
        prof: dict[str, Any],
        prompt: str,
        *,
        width: int,
        height: int,
    ) -> Path:
        from services.integrations.comfyui_client import generate_image

        base = str(prof.get("api_base") or "http://127.0.0.1:8188").strip().rstrip("/")
        steps = int(prof.get("steps") or 20)
        ckpt = str(prof.get("model") or "").strip()
        try:
            data = generate_image(
                base,
                prompt,
                width=width,
                height=height,
                steps=steps,
                ckpt_name=ckpt,
                timeout=max(self.timeout, 180.0),
            )
        except Exception as exc:
            raise self.integration_error(
                str(exc),
                user_message=(
                    f"ComfyUI 生图失败：{exc}\n"
                    "请确认 ComfyUI 已启动、checkpoint 已放入 models/checkpoints，"
                    "或运行 scripts/model_hub_comfyui.py 查看指引。"
                ),
            ) from exc
        return self._write_output(data, suffix=".png")

    def _openai_images(
        self,
        prof: dict[str, Any],
        prompt: str,
        *,
        width: int,
        height: int,
    ) -> Path:
        api_base = str(prof.get("api_base") or "").strip().rstrip("/")
        if not api_base:
            raise self.integration_error(
                "api_base 未配置",
                user_message="请在「能力接入 → 图像生成」填写 API 地址并保存。",
            )
        url = urljoin(api_base + "/", "images/generations")
        model = str(prof.get("model") or "dall-e-3")
        size = str(prof.get("size") or f"{width}x{height}")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self._api_key(prof)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {"model": model, "prompt": prompt, "n": 1, "size": size}
        payload = self._post_json(url, body, headers=headers)
        items = payload.get("data") or []
        if not items:
            raise self.integration_error("无 data", user_message="云端生图未返回图像。")
        item = items[0]
        b64 = str(item.get("b64_json") or "")
        if b64:
            return self._write_output(base64.b64decode(b64), suffix=".png")
        img_url = str(item.get("url") or "")
        if img_url:
            return self._download_url(img_url)
        raise self.integration_error("无图像字段", user_message="生图响应格式无法识别。")

    def _write_output(self, data: bytes, *, suffix: str) -> Path:
        from services.storage_paths import module_output_dir

        out_dir = module_output_dir("media_studio", create=True)
        name = f"image_{time.strftime('%Y%m%d_%H%M%S')}{suffix}"
        path = out_dir / name
        path.write_bytes(data)
        return path.resolve()

    def _download_url(self, url: str) -> Path:
        try:
            import httpx

            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code >= 400:
                    raise self.integration_error(f"HTTP {resp.status_code}")
                return self._write_output(resp.content, suffix=".png")
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(str(exc), user_message=f"下载生图结果失败：{exc}") from exc

    def _post_json(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            import httpx

            with httpx.Client(timeout=max(self.timeout, 120.0)) as client:
                resp = client.post(url, content=data, headers=headers)
                raw = resp.text
                if resp.status_code >= 400:
                    hint = raw[:220].replace("\n", " ")
                    user = f"图像生成失败（HTTP {resp.status_code}）。"
                    if resp.status_code == 429:
                        user = "生图限流，请稍后再试。"
                    if hint:
                        user += f" {hint}"
                    raise self.integration_error(f"HTTP {resp.status_code}: {raw[:300]}", user_message=user)
                return json.loads(raw) if raw else {}
        except ImportError:
            pass
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(str(exc), user_message=f"图像生成失败：{exc}") from exc

        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=max(self.timeout, 120.0)) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise self.integration_error(
                f"HTTP {e.code}: {detail}",
                user_message=f"图像生成失败（HTTP {e.code}）。",
            ) from e
