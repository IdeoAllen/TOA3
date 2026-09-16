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
        if provider == "sdcpp":
            from services.local_image_runtime import install_status

            return bool(install_status().get("ready"))
        if provider in ("sd_webui", "comfyui"):
            base = str(prof.get("api_base") or "").strip().rstrip("/")
            return bool(base)
        return bool(str(prof.get("api_base") or "").strip())

    def _api_key(self, prof: dict[str, Any]) -> str:
        from services.integrations.secrets import get_profile_secret

        pid = str(prof.get("id") or "")
        cap = str(prof.get("capability") or "image_gen")
        provider = str(prof.get("provider") or "")
        api_base = str(prof.get("api_base") or "")
        if provider == "evolink_images" or "evolink.ai" in api_base:
            return str(
                get_profile_secret(cap, pid, "api_key")
                or get_profile_secret("video_gen", "evolink_seedance_2", "api_key")
                or os.environ.get("EVOLINK_API_KEY")
                or os.environ.get("TOA_IMAGE_GEN_API_KEY")
                or self._config.get("api_key")
                or ""
            ).strip()
        if self._is_mxapi_profile(prof):
            return self._mxapi_api_key(prof)
        return str(
            get_profile_secret(cap, pid, "api_key")
            or self._config.get("api_key")
            or os.environ.get("TOA_IMAGE_GEN_API_KEY")
            or os.environ.get("ARK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()

    @staticmethod
    def _is_mxapi_profile(prof: dict[str, Any]) -> bool:
        pid = str(prof.get("id") or "").lower()
        base = str(prof.get("api_base") or "").lower()
        vendor = str(prof.get("vendor") or "").lower()
        return (
            pid.startswith("mxapi_")
            or "mxapi.org" in base
            or vendor == "mxapi"
        )

    def _mxapi_api_key(self, prof: dict[str, Any]) -> str:
        """MXAPI Key：模型管理 profile → 环境变量 → Harness .credentials.yaml。"""
        from services.integrations.secrets import get_profile_secret

        pid = str(prof.get("id") or "")
        shared = (
            "mxapi_nano_banana_2",
            "mxapi_gpt_image_2",
            "mxapi_nano_banana_pro",
        )
        for candidate in (pid, *shared):
            if not candidate:
                continue
            val = get_profile_secret("image_gen", candidate, "api_key")
            if str(val or "").strip():
                return str(val).strip()
        env = (
            os.environ.get("MXAPI_API_KEY")
            or os.environ.get("TOA_IMAGE_GEN_API_KEY")
            or ""
        ).strip()
        if env:
            return env
        try:
            from services.harness_credentials import load_credential_map

            return str(load_credential_map().get("MXAPI_API_KEY") or "").strip()
        except Exception:
            return ""

    def generate(
        self,
        prompt: str,
        *,
        width: int = 512,
        height: int = 512,
        profile_id: str | None = None,
        image_path: str | Path | None = None,
        image_paths: list[str | Path] | None = None,
    ) -> Path:
        self.require_enabled()
        text = str(prompt or "").strip()
        if not text:
            raise self.integration_error("prompt 为空", user_message="请先填写画面描述。")
        prof = resolve_image_gen_profile(profile_id)
        provider = str(prof.get("provider") or "").strip()
        refs = self._normalize_refs(image_path=image_path, image_paths=image_paths)
        if provider == "sdcpp":
            if refs:
                raise self.integration_error(
                    "sdcpp no edit",
                    user_message="本机简易生图暂不支持参考图，请改选「豆包 · Seedream」或清除参考图。",
                )
            return self._sdcpp(prof, text, width=width, height=height)
        if provider == "sd_webui":
            if refs:
                raise self.integration_error(
                    "sd_webui no edit",
                    user_message="当前本地 WebUI 配置未开参考图，请改选云端 Seedream。",
                )
            return self._sd_webui(prof, text, width=width, height=height)
        if provider == "comfyui":
            if refs:
                raise self.integration_error(
                    "comfyui no edit",
                    user_message="ComfyUI 专业档请在 Comfy 内跑图生图；TOA 多图融合请用「豆包 · Seedream」。",
                )
            return self._comfyui(prof, text, width=width, height=height)
        if provider == "openai_images":
            return self._openai_images(
                prof, text, width=width, height=height, image_paths=refs
            )
        if provider == "evolink_images" or "evolink.ai" in str(prof.get("api_base") or ""):
            return self._evolink_images(
                prof, text, width=width, height=height, image_paths=refs
            )
        raise self.integration_error(
            f"未知 provider: {provider}",
            user_message=f"图像生成配置不支持：{provider}",
        )

    @staticmethod
    def _normalize_refs(
        *,
        image_path: str | Path | None = None,
        image_paths: list[str | Path] | None = None,
    ) -> list[Path]:
        out: list[Path] = []
        seen: set[str] = set()
        for raw in list(image_paths or []) + ([image_path] if image_path else []):
            if raw is None:
                continue
            p = Path(raw)
            key = str(p.resolve()) if p.is_file() else str(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out[:10]

    def edit(
        self,
        prompt: str,
        image_path: str | Path,
        *,
        width: int = 1024,
        height: int = 1024,
        profile_id: str | None = None,
    ) -> Path:
        """参考图编辑 / 图生图（Seedream 等同端点带 image 字段）。"""
        path = Path(image_path)
        if not path.is_file():
            raise self.integration_error(
                "image missing",
                user_message="请先选择一张本地参考图。",
            )
        return self.generate(
            prompt,
            width=width,
            height=height,
            profile_id=profile_id,
            image_path=path,
        )

    def _sdcpp(
        self,
        prof: dict[str, Any],
        prompt: str,
        *,
        width: int,
        height: int,
    ) -> Path:
        from services.integrations import sdcpp_client

        try:
            data = sdcpp_client.generate_image(
                prompt,
                width=width,
                height=height,
                steps=int(prof.get("steps") or 8),
                cfg_scale=float(prof.get("cfg_scale") or 1.0),
                timeout=max(self.timeout, 600.0),
                offload_to_cpu=bool(prof.get("offload_to_cpu", True)),
            )
        except Exception as exc:
            raise self.integration_error(
                str(exc),
                user_message=str(exc) or "本机生图失败，请到模型库安装或导入离线包。",
            ) from exc
        return self._write_output(data, suffix=".png")

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
        workflow = str(prof.get("workflow") or "sd15_ckpt").strip()
        try:
            data = generate_image(
                base,
                prompt,
                width=width,
                height=height,
                steps=steps,
                ckpt_name=ckpt,
                workflow=workflow,
                unet=str(prof.get("unet") or ""),
                text_encoder=str(prof.get("text_encoder") or ""),
                vae=str(prof.get("vae") or "ae.safetensors"),
                cfg_scale=float(prof.get("cfg_scale") or 1.5),
                timeout=max(self.timeout, 180.0),
            )
        except Exception as exc:
            detail = str(exc)
            hint = (
                "请确认 ComfyUI 已启动，且界面里能正常出图。"
                "TOA 会自动匹配本机已有模型；若仍失败，到「模型管理」刷新后再试。"
                "也可改用「本机生图（推荐）」。"
            )
            if "GGUF" in detail or "UnetLoaderGGUF" in detail:
                hint = (
                    "当前环境缺 GGUF 插件。你本机若已是 safetensors 版 Z-Image，"
                    "请选「ComfyUI 专业 · Z-Image / 自动匹配」；或安装 ComfyUI-GGUF。"
                )
            raise self.integration_error(
                detail,
                user_message=f"ComfyUI 生图失败：{detail}\n{hint}",
            ) from exc
        return self._write_output(data, suffix=".png")

    def _openai_images(
        self,
        prof: dict[str, Any],
        prompt: str,
        *,
        width: int,
        height: int,
        image_paths: list[Path] | None = None,
    ) -> Path:
        api_base = str(prof.get("api_base") or "").strip().rstrip("/")
        if not api_base:
            raise self.integration_error(
                "api_base 未配置",
                user_message="请在「系统设置 → 模型管理」填写 API 地址并保存 Key。",
            )
        key = self._api_key(prof)
        if not key:
            raise self.integration_error(
                "api_key missing",
                user_message=(
                    "云端生图尚未绑定 Key。请到「系统设置 → 模型管理」选中该来源并保存 API Key。"
                ),
            )
        url = urljoin(api_base + "/", "images/generations")
        model = str(prof.get("model") or "dall-e-3")
        size = self._resolve_cloud_size(prof, width=width, height=height)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers["Authorization"] = f"Bearer {key}"

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }
        is_ark = (
            "volces.com" in api_base
            or "seedream" in model.lower()
            or "doubao" in model.lower()
        )
        if is_ark:
            body.pop("n", None)
            rf = str(prof.get("response_format") or "url").strip() or "url"
            body["response_format"] = rf
            if "watermark" in prof:
                body["watermark"] = bool(prof.get("watermark"))
            of = str(prof.get("output_format") or "").strip()
            if of:
                body["output_format"] = of
            body["stream"] = False

        refs = [p for p in (image_paths or []) if p is not None]
        if refs:
            if not bool(prof.get("supports_edit", is_ark)):
                raise self.integration_error(
                    "edit unsupported",
                    user_message="当前云端模型不支持参考图编辑，请换「豆包 · Seedream」。",
                )
            encoded = [self._encode_image_for_ark(Path(p)) for p in refs[:10]]
            if len(encoded) == 1:
                body["image"] = encoded[0]
            else:
                body["image"] = encoded

        # MXAPI 同步出图常 40–60s，给足超时
        timeout = max(self.timeout, 600.0 if self._is_mxapi_profile(prof) else 120.0)
        payload = self._post_json(url, body, headers=headers, timeout=timeout)
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

    def _evolink_images(
        self,
        prof: dict[str, Any],
        prompt: str,
        *,
        width: int,
        height: int,
        image_paths: list[Path] | None = None,
    ) -> Path:
        api_base = str(prof.get("api_base") or "https://api.evolink.ai/v1").strip().rstrip("/")
        key = self._api_key(prof)
        if not key:
            raise self.integration_error(
                "api_key missing",
                user_message="请先在「模型管理」保存 Evolink API Key（可与 Seedance 共用）。",
            )
        model = str(prof.get("model") or "grok-imagine-image-2.0")
        resolution = str(prof.get("resolution") or prof.get("size") or "2K")
        if resolution.upper() in ("1K", "2K", "4K"):
            resolution = resolution.upper()
        quality = str(prof.get("quality") or "medium").lower()
        aspect = self._guess_aspect_ratio(width, height)

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": max(1, min(10, int(prof.get("n") or 1))),
            "resolution": resolution,
            "quality": quality,
            "aspect_ratio": aspect,
        }
        refs = [p for p in (image_paths or []) if p is not None and Path(p).is_file()]
        if refs:
            body["image_urls"] = [self._encode_image_for_ark(Path(p)) for p in refs[:3]]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }
        create_url = urljoin(api_base + "/", "images/generations")
        payload = self._post_json(create_url, body, headers=headers)
        task_id = str(payload.get("id") or "").strip()
        if not task_id:
            raise self.integration_error(
                f"no task id: {payload}",
                user_message="生图任务未返回编号，请稍后重试。",
            )

        query_url = urljoin(api_base + "/", f"tasks/{task_id}")
        deadline = time.time() + max(self.timeout, 600.0)
        while time.time() < deadline:
            data = self._get_json(query_url, headers=headers)
            status = str(data.get("status") or "").lower()
            if status == "completed":
                results = data.get("results") or []
                urls = [str(u) for u in results if u] if isinstance(results, list) else []
                if not urls:
                    raise self.integration_error(
                        "no image url",
                        user_message="任务完成但未返回图片地址。",
                    )
                paths: list[Path] = []
                for i, img_url in enumerate(urls):
                    tag = f"_{i + 1}" if len(urls) > 1 else ""
                    paths.append(self._download_url(img_url, tag))
                return paths[0]
            if status == "failed":
                err = data.get("error") or {}
                detail = ""
                if isinstance(err, dict):
                    detail = str(err.get("message") or err.get("code") or err)
                else:
                    detail = str(err)
                raise self.integration_error(
                    detail or status,
                    user_message=f"生图失败：{detail or status}",
                )
            time.sleep(2.0)

        raise self.integration_error("timeout", user_message="生图超时，请稍后重试。")

    @staticmethod
    def _guess_aspect_ratio(width: int, height: int) -> str:
        w, h = max(1, int(width)), max(1, int(height))
        ratio = w / h
        pairs = [
            (1.0, "1:1"),
            (16 / 9, "16:9"),
            (9 / 16, "9:16"),
            (4 / 3, "4:3"),
            (3 / 4, "3:4"),
            (3 / 2, "3:2"),
            (2 / 3, "2:3"),
        ]
        best = "auto"
        best_delta = 999.0
        for target, label in pairs:
            delta = abs(ratio - target)
            if delta < best_delta:
                best_delta = delta
                best = label
        return best if best_delta < 0.08 else "auto"

    def _get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        try:
            import httpx

            with httpx.Client(timeout=max(self.timeout, 60.0)) as client:
                resp = client.get(url, headers=headers)
                raw = resp.text
                if resp.status_code >= 400:
                    raise self.integration_error(
                        f"HTTP {resp.status_code}: {raw[:300]}",
                        user_message=f"查询生图任务失败（HTTP {resp.status_code}）。",
                    )
                return json.loads(raw) if raw else {}
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(str(exc), user_message=f"查询生图任务失败：{exc}") from exc

    @staticmethod
    def _resolve_cloud_size(prof: dict[str, Any], *, width: int, height: int) -> str:
        configured = str(prof.get("size") or "").strip()
        if configured.upper() in ("1K", "2K", "4K"):
            return configured.upper()
        if configured and "x" in configured.lower():
            return configured
        api_base = str(prof.get("api_base") or "").lower()
        model = str(prof.get("model") or "").lower()
        # Seedream 像素下限约 921600，768² 不够 → 默认 2K 档
        if "volces.com" in api_base or "seedream" in model or "doubao" in model:
            return configured or "2K"
        return configured or f"{max(256, int(width))}x{max(256, int(height))}"

    @staticmethod
    def _encode_image_for_ark(path: Path) -> str:
        """Ark 参考图：data URI（本地文件）或原样 URL。"""
        raw = str(path)
        if raw.startswith(("http://", "https://", "data:")):
            return raw
        data = path.read_bytes()
        if len(data) > 28 * 1024 * 1024:
            raise RuntimeError("参考图过大（建议 < 28MB）")
        suffix = path.suffix.lower().lstrip(".") or "png"
        mime = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "bmp": "image/bmp",
        }.get(suffix, "image/png")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    def _write_output(self, data: bytes, *, suffix: str = ".png", name_suffix: str = "") -> Path:
        from services.storage_paths import module_output_dir

        out_dir = module_output_dir("media_studio", create=True)
        name = f"image_{time.strftime('%Y%m%d_%H%M%S')}{name_suffix}{suffix}"
        path = out_dir / name
        path.write_bytes(data)
        return path.resolve()

    def _download_url(self, url: str, name_suffix: str = "") -> Path:
        try:
            import httpx

            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code >= 400:
                    raise self.integration_error(f"HTTP {resp.status_code}")
                ext = ".png"
                ct = str(resp.headers.get("content-type") or "").lower()
                if "jpeg" in ct or "jpg" in ct:
                    ext = ".jpg"
                elif "webp" in ct:
                    ext = ".webp"
                return self._write_output(resp.content, suffix=ext, name_suffix=name_suffix)
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(str(exc), user_message=f"下载生图结果失败：{exc}") from exc

    def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        wait = float(timeout if timeout is not None else max(self.timeout, 120.0))
        try:
            import httpx

            with httpx.Client(timeout=wait) as client:
                resp = client.post(url, content=data, headers=headers)
                raw = resp.text
                if resp.status_code >= 400:
                    hint = raw[:220].replace("\n", " ")
                    user = f"图像生成失败（HTTP {resp.status_code}）。"
                    if resp.status_code == 429:
                        user = "生图限流，请稍后再试。"
                    if resp.status_code == 402:
                        user = "积分不足，请到 MXAPI / 对应平台充值后再试。"
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
            with urllib.request.urlopen(req, timeout=wait) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise self.integration_error(
                f"HTTP {e.code}: {detail}",
                user_message=f"图像生成失败（HTTP {e.code}）。",
            ) from e
