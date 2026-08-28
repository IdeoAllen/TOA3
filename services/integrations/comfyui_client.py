# -*- coding: utf-8 -*-
"""ComfyUI HTTP API（本地生图，对标 ComfyUI 节点工作流）。"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

logger = logging.getLogger(__name__)


def health_check(base_url: str, *, timeout: float = 2.0) -> bool:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return False
    url = urljoin(base + "/", "system_stats")
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            return resp.status_code < 500
    except Exception:
        return False


def _build_txt2img_workflow(
    prompt: str,
    *,
    negative: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    ckpt_name: str = "",
) -> dict[str, Any]:
    seed = int(time.time() * 1000) % (2**31)
    ckpt = ckpt_name or "v1-5-pruned-emaonly.safetensors"
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative or "low quality", "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "toa3", "images": ["8", 0]},
        },
    }


def generate_image(
    base_url: str,
    prompt: str,
    *,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    ckpt_name: str = "",
    timeout: float = 180.0,
) -> bytes:
    """提交工作流并轮询 history，返回 PNG 字节。"""
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("ComfyUI api_base 未配置")
    workflow = _build_txt2img_workflow(
        prompt,
        width=max(64, min(2048, int(width))),
        height=max(64, min(2048, int(height))),
        steps=max(1, min(60, int(steps))),
        ckpt_name=ckpt_name,
    )
    client_id = str(uuid.uuid4())
    body = {"prompt": workflow, "client_id": client_id}
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("需要 httpx 调用 ComfyUI") from exc

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            urljoin(base + "/", "prompt"),
            content=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"ComfyUI prompt 失败 HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        prompt_id = str(payload.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError("ComfyUI 未返回 prompt_id")

        deadline = time.time() + timeout
        while time.time() < deadline:
            hist = client.get(urljoin(base + "/", f"history/{prompt_id}"))
            if hist.status_code == 200:
                data = hist.json()
                if prompt_id in data:
                    images = _extract_images_from_history(data[prompt_id])
                    if images:
                        fn, subfolder, img_type = images[0]
                        qs = urlencode(
                            {"filename": fn, "subfolder": subfolder, "type": img_type}
                        )
                        view = client.get(urljoin(base + "/", f"view?{qs}"))
                        if view.status_code < 400 and view.content:
                            return view.content
                    raise RuntimeError("ComfyUI 完成但未找到输出图像")
            time.sleep(0.8)
        raise RuntimeError("ComfyUI 生图超时，请检查是否已加载 checkpoint")


def _extract_images_from_history(entry: dict[str, Any]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    outputs = entry.get("outputs") or {}
    if not isinstance(outputs, dict):
        return out
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get("images") or []:
            if not isinstance(img, dict):
                continue
            fn = str(img.get("filename") or "")
            if fn:
                out.append(
                    (
                        fn,
                        str(img.get("subfolder") or ""),
                        str(img.get("type") or "output"),
                    )
                )
    return out
