# -*- coding: utf-8 -*-
"""视频生成：Evolink Seedance 2.0 / 火山方舟 Seedance 1.5。"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config
from services.model_catalog import resolve_profile

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]
CancelFn = Callable[[], bool]


class VideoGenClient(IntegrationClient):
    name = "video_gen"

    def __init__(self) -> None:
        super().__init__(integration_config("video_gen"))

    def health_check(self) -> bool:
        if not self.enabled:
            return False
        try:
            prof = resolve_profile("video_gen")
        except KeyError:
            return False
        return bool(str(prof.get("api_base") or "").strip())

    def _api_key(self, prof: dict[str, Any]) -> str:
        from services.integrations.secrets import get_profile_secret, get_secret

        pid = str(prof.get("id") or "")
        provider = str(prof.get("provider") or "")
        if provider == "evolink_seedance" or "evolink.ai" in str(prof.get("api_base") or ""):
            return str(
                get_profile_secret("video_gen", pid, "api_key")
                or get_secret("video_gen", "api_key")
                or os.environ.get("EVOLINK_API_KEY")
                or os.environ.get("TOA_VIDEO_GEN_API_KEY")
                or self._config.get("api_key")
                or ""
            ).strip()
        return str(
            get_profile_secret("video_gen", pid, "api_key")
            or get_profile_secret("image_gen", "doubao_seedream", "api_key")
            or get_secret("image_gen", "api_key")
            or self._config.get("api_key")
            or os.environ.get("ARK_API_KEY")
            or os.environ.get("TOA_VIDEO_GEN_API_KEY")
            or ""
        ).strip()

    def generate(
        self,
        prompt: str,
        *,
        profile_id: str | None = None,
        image_paths: list[str | Path] | None = None,
        ratio: str = "16:9",
        resolution: str = "720p",
        duration: int = 5,
        watermark: bool = False,
        generate_audio: bool = False,
        web_search: bool = False,
        content_filter: bool | None = None,
        progress: ProgressFn | None = None,
        cancel_check: CancelFn | None = None,
        timeout: float | None = None,
    ) -> Path:
        """文生视频 / 图生视频。返回本机 mp4 路径。"""
        self.require_enabled()
        text = str(prompt or "").strip()
        if not text:
            raise self.integration_error("prompt 为空", user_message="请先填写视频描述。")
        try:
            prof = resolve_profile("video_gen", profile_id)
        except KeyError as exc:
            raise self.integration_error(
                str(exc),
                user_message="未配置视频算力。请到「系统设置 → 模型管理」绑定视频 Key。",
            ) from exc

        provider = str(prof.get("provider") or "").strip()
        api_base = str(prof.get("api_base") or "").strip().rstrip("/")
        if provider == "evolink_seedance" or "evolink.ai" in api_base:
            return self._generate_evolink(
                text,
                prof=prof,
                image_paths=image_paths,
                ratio=ratio,
                resolution=resolution,
                duration=duration,
                generate_audio=generate_audio,
                web_search=web_search,
                content_filter=content_filter,
                progress=progress,
                cancel_check=cancel_check,
                timeout=timeout,
            )
        return self._generate_volcengine(
            text,
            prof=prof,
            image_paths=image_paths,
            ratio=ratio,
            resolution=resolution,
            duration=duration,
            watermark=watermark,
            generate_audio=generate_audio,
            progress=progress,
            cancel_check=cancel_check,
            timeout=timeout,
        )

    def _generate_evolink(
        self,
        text: str,
        *,
        prof: dict[str, Any],
        image_paths: list[str | Path] | None,
        ratio: str,
        resolution: str,
        duration: int,
        generate_audio: bool,
        web_search: bool,
        content_filter: bool | None,
        progress: ProgressFn | None,
        cancel_check: CancelFn | None,
        timeout: float | None,
    ) -> Path:
        api_base = str(prof.get("api_base") or "https://api.evolink.ai/v1").strip().rstrip("/")
        key = self._api_key(prof)
        if not key:
            raise self.integration_error(
                "api_key missing",
                user_message="视频生成尚未绑定 Evolink Key。请到「模型设置」保存 API Key。",
            )

        refs = [Path(p) for p in (image_paths or []) if p and Path(p).is_file()]
        if refs:
            model = str(prof.get("model_img") or "seedance-2.0-image-to-video")
        else:
            model = str(prof.get("model_txt") or prof.get("model") or "seedance-2.0-text-to-video")

        aspect = str(ratio or prof.get("aspect_ratio") or "adaptive").strip()
        if aspect in ("auto", "smart"):
            aspect = "adaptive"
        quality = str(resolution or prof.get("quality") or "720p").lower()
        if quality == "4k":
            quality = "1080p"
        dur = max(4, min(15, int(duration or prof.get("duration") or 5)))
        audio_on = bool(generate_audio if generate_audio is not None else prof.get("generate_audio", True))
        filter_on = (
            bool(content_filter)
            if content_filter is not None
            else bool(prof.get("content_filter", True))
        )
        if web_search and not filter_on:
            raise self.integration_error(
                "web_search with content_filter false",
                user_message="联网搜索不能与「放宽内容限制」同时开启，请保持内容过滤为开启。",
            )

        body: dict[str, Any] = {
            "model": model,
            "prompt": text,
            "duration": dur,
            "quality": quality,
            "aspect_ratio": aspect,
            "generate_audio": audio_on,
            "content_filter": filter_on,
        }
        if refs:
            body["image_urls"] = [self._encode_image(p) for p in refs[:2]]
        if web_search and not refs:
            body["model_params"] = {"web_search": True}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }
        create_url = urljoin(api_base + "/", "videos/generations")
        if progress:
            progress("已提交 Seedance 2.0 任务…")
        payload = self._post_json(create_url, body, headers=headers, provider="evolink")
        task_id = str(payload.get("id") or "").strip()
        if not task_id:
            raise self.integration_error(
                f"no task id: {payload}",
                user_message="视频任务未返回编号，请稍后重试。",
            )

        wait = float(timeout if timeout is not None else max(self.timeout, 900.0))
        deadline = time.time() + wait
        query_url = urljoin(api_base + "/", f"tasks/{task_id}")
        last_status = ""
        while time.time() < deadline:
            if cancel_check and cancel_check():
                raise self.integration_error("cancelled", user_message="已取消生成。")
            data = self._get_json(query_url, headers=headers, provider="evolink")
            status = str(data.get("status") or "").lower()
            pct = data.get("progress")
            if status != last_status or pct is not None:
                last_status = status
                if progress:
                    if isinstance(pct, int) and pct > 0:
                        progress(f"视频生成 {pct}% · {status or '处理中'}…")
                    else:
                        progress(f"视频任务 {status or '处理中'}…")
            if status == "completed":
                results = data.get("results") or []
                video_url = ""
                if isinstance(results, list) and results:
                    video_url = str(results[0] or "")
                if not video_url:
                    raise self.integration_error(
                        "no video url",
                        user_message="任务完成但未返回视频地址。",
                    )
                if progress:
                    progress("正在下载视频…")
                return self._download_video(video_url)
            if status == "failed":
                err = data.get("error") or {}
                detail = ""
                if isinstance(err, dict):
                    detail = str(err.get("message") or err.get("code") or err)
                else:
                    detail = str(err)
                raise self.integration_error(
                    detail or status,
                    user_message=f"视频生成失败：{detail or status}",
                )
            time.sleep(3.0)

        raise self.integration_error(
            "timeout",
            user_message="视频生成超时。可缩短时长后重试，或稍后在 Evolink 控制台查看任务。",
        )

    def _generate_volcengine(
        self,
        text: str,
        *,
        prof: dict[str, Any],
        image_paths: list[str | Path] | None,
        ratio: str,
        resolution: str,
        duration: int,
        watermark: bool,
        generate_audio: bool,
        progress: ProgressFn | None,
        cancel_check: CancelFn | None,
        timeout: float | None,
    ) -> Path:
        api_base = str(prof.get("api_base") or "").strip().rstrip("/")
        model = str(prof.get("model") or "").strip()
        key = self._api_key(prof)
        if not api_base or not model:
            raise self.integration_error(
                "video profile incomplete",
                user_message="视频模型地址或模型名未配置。",
            )
        if not key:
            raise self.integration_error(
                "api_key missing",
                user_message="视频生成尚未绑定 Key。可与 Seedream 共用火山方舟 Key。",
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        refs = [Path(p) for p in (image_paths or []) if p]
        if refs:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._encode_image(refs[0])},
                    "role": "first_frame",
                }
            )

        body: dict[str, Any] = {
            "model": model,
            "content": content,
            "ratio": str(ratio or prof.get("ratio") or "16:9"),
            "resolution": str(resolution or prof.get("resolution") or "720p").lower(),
            "duration": max(2, min(12, int(duration or prof.get("duration") or 5))),
            "watermark": bool(watermark if watermark is not None else prof.get("watermark", False)),
        }
        if "generate_audio" in prof or generate_audio:
            body["generate_audio"] = bool(generate_audio or prof.get("generate_audio"))

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }
        create_url = urljoin(api_base + "/", "contents/generations/tasks")
        if progress:
            progress("已提交视频任务…")
        payload = self._post_json(create_url, body, headers=headers, provider="volcengine")
        task_id = str(payload.get("id") or "").strip()
        if not task_id:
            raise self.integration_error(
                f"no task id: {payload}",
                user_message="视频任务未返回编号，请稍后重试。",
            )

        wait = float(timeout if timeout is not None else max(self.timeout, 600.0))
        deadline = time.time() + wait
        query_url = urljoin(api_base + "/", f"contents/generations/tasks/{task_id}")
        last_status = ""
        while time.time() < deadline:
            if cancel_check and cancel_check():
                raise self.integration_error("cancelled", user_message="已取消生成。")
            data = self._get_json(query_url, headers=headers, provider="volcengine")
            status = str(data.get("status") or "").lower()
            if status != last_status:
                last_status = status
                if progress:
                    progress(f"视频任务 {status or '处理中'}…")
            if status == "succeeded":
                content_obj = data.get("content") or {}
                video_url = ""
                if isinstance(content_obj, dict):
                    video_url = str(content_obj.get("video_url") or "")
                if not video_url:
                    raise self.integration_error(
                        "no video_url",
                        user_message="任务成功但未返回视频地址。",
                    )
                if progress:
                    progress("正在下载视频…")
                return self._download_video(video_url)
            if status in ("failed", "expired", "cancelled"):
                err = data.get("error") or {}
                detail = ""
                if isinstance(err, dict):
                    detail = str(err.get("message") or err.get("code") or err)
                else:
                    detail = str(err)
                raise self.integration_error(
                    detail or status,
                    user_message=f"视频生成失败：{detail or status}",
                )
            time.sleep(3.0)

        raise self.integration_error(
            "timeout",
            user_message="视频生成超时。可到火山方舟控制台查看任务，或缩短时长后重试。",
        )

    @staticmethod
    def _encode_image(path: Path) -> str:
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
        }.get(suffix, "image/png")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    def _download_video(self, url: str) -> Path:
        from services.storage_paths import module_output_dir

        try:
            import httpx
        except ImportError as exc:
            raise self.integration_error(str(exc), user_message="需要 httpx 下载视频") from exc

        with httpx.Client(timeout=max(self.timeout, 180.0), follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                raise self.integration_error(
                    f"HTTP {resp.status_code}",
                    user_message="下载生成视频失败。",
                )
            out_dir = module_output_dir("media_studio", create=True)
            name = f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
            path = out_dir / name
            path.write_bytes(resp.content)
            return path.resolve()

    def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        *,
        provider: str = "",
    ) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            import httpx

            with httpx.Client(timeout=max(self.timeout, 60.0)) as client:
                resp = client.post(url, content=data, headers=headers)
                raw = resp.text
                if resp.status_code >= 400:
                    hint = self._parse_error(raw, provider)
                    user = f"提交视频任务失败（HTTP {resp.status_code}）。"
                    if hint:
                        user += f" {hint}"
                    raise self.integration_error(
                        f"HTTP {resp.status_code}: {raw[:300]}",
                        user_message=user,
                    )
                return json.loads(raw) if raw else {}
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(str(exc), user_message=f"提交视频任务失败：{exc}") from exc

    def _get_json(
        self,
        url: str,
        headers: dict[str, str],
        *,
        provider: str = "",
    ) -> dict[str, Any]:
        try:
            import httpx

            with httpx.Client(timeout=max(self.timeout, 60.0)) as client:
                resp = client.get(url, headers=headers)
                raw = resp.text
                if resp.status_code >= 400:
                    hint = self._parse_error(raw, provider)
                    user = f"查询视频任务失败（HTTP {resp.status_code}）。"
                    if hint:
                        user += f" {hint}"
                    raise self.integration_error(
                        f"HTTP {resp.status_code}: {raw[:300]}",
                        user_message=user,
                    )
                return json.loads(raw) if raw else {}
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(str(exc), user_message=f"查询视频任务失败：{exc}") from exc

    @staticmethod
    def _parse_error(raw: str, provider: str) -> str:
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return raw[:240].replace("\n", " ")
        if not isinstance(data, dict):
            return raw[:240].replace("\n", " ")
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or "")[:240]
        if provider == "volcengine":
            return str(data.get("message") or "")[:240]
        return raw[:240].replace("\n", " ")
