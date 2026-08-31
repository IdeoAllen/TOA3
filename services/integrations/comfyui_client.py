# -*- coding: utf-8 -*-
"""ComfyUI HTTP API（专业档本地生图）。"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

from services.config_service import project_root

logger = logging.getLogger(__name__)

_OBJECT_INFO_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_OBJECT_INFO_TTL_S = 120.0


def _fetch_object_info(base: str, *, timeout: float = 2.0) -> dict[str, Any] | None:
    key = base.strip().rstrip("/")
    now = time.time()
    cached = _OBJECT_INFO_CACHE.get(key)
    if cached and now - cached[0] < _OBJECT_INFO_TTL_S:
        return cached[1]
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(urljoin(key + "/", "object_info"))
            if resp.status_code >= 400:
                return None
            info = resp.json()
            if not isinstance(info, dict):
                return None
            _OBJECT_INFO_CACHE[key] = (now, info)
            return info
    except Exception:
        return None


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


def required_node_types(workflow: str) -> tuple[str, ...]:
    kind = (workflow or "sd15_ckpt").strip().lower()
    if kind in ("z_image_turbo_gguf", "z_image_gguf"):
        return ("UnetLoaderGGUF", "CLIPLoaderGGUF", "VAELoader", "KSampler", "EmptyLatentImage")
    if kind in ("z_image_turbo", "z_image", "zimage", "z_image_unet"):
        return ("UNETLoader", "CLIPLoader", "VAELoader", "KSampler", "EmptyLatentImage")
    return ("CheckpointLoaderSimple", "KSampler", "EmptyLatentImage")


def workflow_ready(base_url: str, workflow: str, *, timeout: float = 2.0) -> bool:
    """ComfyUI 进程在线且工作流所需节点已安装。"""
    base = str(base_url or "").strip().rstrip("/")
    if not base or not health_check(base, timeout=timeout):
        return False
    required = required_node_types(workflow)
    try:
        info = _fetch_object_info(base, timeout=timeout)
        if not info:
            return False
        if not all(node in info for node in required):
            return False
        assets = discover_assets(base, timeout=timeout)
        kind = (workflow or "sd15_ckpt").strip().lower()
        if kind in ("z_image_turbo_gguf", "z_image_gguf"):
            return bool(assets.get("unet_gguf") and assets.get("clip_gguf") and assets.get("vae"))
        if kind in ("z_image_turbo", "z_image", "zimage", "z_image_unet"):
            return bool(assets.get("unet") and assets.get("clip") and assets.get("vae"))
        return bool(assets.get("checkpoints"))
    except Exception:
        return False


def list_model_files(base_url: str, folder: str, *, timeout: float = 3.0) -> list[str]:
    base = str(base_url or "").strip().rstrip("/")
    if not base or not folder:
        return []
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(urljoin(base + "/", f"models/{folder}"))
            if resp.status_code >= 400:
                return []
            data = resp.json()
            if not isinstance(data, list):
                return []
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        return []


def discover_assets(base_url: str, *, timeout: float = 3.0) -> dict[str, list[str]]:
    """扫描 ComfyUI 本机已加载的模型文件名。"""
    checkpoints = list_model_files(base_url, "checkpoints", timeout=timeout)
    diffusion = list_model_files(base_url, "diffusion_models", timeout=timeout)
    text_encoders = list_model_files(base_url, "text_encoders", timeout=timeout)
    vaes = list_model_files(base_url, "vae", timeout=timeout)
    unet_extra = list_model_files(base_url, "unet", timeout=timeout)
    clip_extra = list_model_files(base_url, "clip", timeout=timeout)

    def _pick(names: list[str], *needles: str) -> list[str]:
        out: list[str] = []
        lower_needles = tuple(n.lower() for n in needles)
        for name in names:
            low = name.replace("\\", "/").lower()
            if any(n in low for n in lower_needles):
                out.append(name)
        return out

    unet_all = diffusion + unet_extra
    clip_all = text_encoders + clip_extra
    return {
        "checkpoints": checkpoints,
        "unet": _pick(unet_all, "z_image", "z-image") or unet_all,
        "unet_gguf": [n for n in unet_all if n.lower().endswith(".gguf")],
        "clip": _pick(clip_all, "qwen") or clip_all,
        "clip_gguf": [n for n in clip_all if n.lower().endswith(".gguf")],
        "vae": _pick(vaes, "ae.safetensors") or vaes,
        "diffusion_models": diffusion,
        "text_encoders": text_encoders,
    }


def resolve_workflow_and_assets(
    base_url: str,
    *,
    workflow: str = "",
    ckpt_name: str = "",
    unet: str = "",
    text_encoder: str = "",
    vae: str = "",
    timeout: float = 3.0,
) -> tuple[str, dict[str, str]]:
    """
    按本机实际模型自动选定工作流与文件名。
    优先：显式 workflow → Z-Image safetensors → Z-Image GGUF → SD checkpoint。
    """
    assets = discover_assets(base_url, timeout=timeout)
    kind = (workflow or "").strip().lower()

    def _first(seq: list[str], preferred: str = "") -> str:
        pref = (preferred or "").strip()
        if pref and pref in seq:
            return pref
        if pref:
            for name in seq:
                if name.replace("\\", "/").endswith(pref.replace("\\", "/")):
                    return name
                if Path(name).name == Path(pref).name:
                    return name
        return seq[0] if seq else pref

    if kind in ("sd15_ckpt", "sd15", "checkpoint"):
        ckpt = _first(assets["checkpoints"], ckpt_name)
        if ckpt:
            return "sd15_ckpt", {"ckpt_name": ckpt, "vae": "", "unet": "", "text_encoder": ""}
        if assets["unet"] and assets["clip"] and assets["vae"]:
            logger.info("ComfyUI 无 checkpoint，自动改用 Z-Image safetensors 工作流")
            return "z_image_unet", {
                "unet": _first(assets["unet"], unet),
                "text_encoder": _first(assets["clip"], text_encoder),
                "vae": _first(assets["vae"], vae or "ae.safetensors"),
                "ckpt_name": "",
            }
        raise RuntimeError(
            "ComfyUI 的 checkpoints 目录为空，也没有可用的 Z-Image 模型。"
            "请在 ComfyUI 里放入 checkpoint，或安装 Z-Image（diffusion_models + text_encoders + vae）。"
        )

    if kind in ("z_image_turbo_gguf", "z_image_gguf"):
        if assets["unet_gguf"] and assets["clip_gguf"] and assets["vae"]:
            return "z_image_turbo_gguf", {
                "unet": _first(assets["unet_gguf"], unet),
                "text_encoder": _first(assets["clip_gguf"], text_encoder),
                "vae": _first(assets["vae"], vae or "ae.safetensors"),
                "ckpt_name": "",
            }
        if assets["unet"] and assets["clip"] and assets["vae"]:
            logger.info("ComfyUI 无 GGUF 模型，自动改用 Z-Image safetensors")
            return "z_image_unet", {
                "unet": _first(assets["unet"], unet),
                "text_encoder": _first(assets["clip"], text_encoder),
                "vae": _first(assets["vae"], vae or "ae.safetensors"),
                "ckpt_name": "",
            }
        raise RuntimeError(
            "Z-Image GGUF 模型未找到。请安装 ComfyUI-GGUF 插件并放入对应 .gguf，"
            "或改用本机已有的 z_image_turbo_*.safetensors。"
        )

    if kind in ("", "auto", "z_image_turbo", "z_image", "zimage", "z_image_unet"):
        if assets["unet"] and assets["clip"] and assets["vae"]:
            if (unet or "").lower().endswith(".gguf") and assets["unet_gguf"]:
                return "z_image_turbo_gguf", {
                    "unet": _first(assets["unet_gguf"], unet),
                    "text_encoder": _first(assets["clip_gguf"] or assets["clip"], text_encoder),
                    "vae": _first(assets["vae"], vae or "ae.safetensors"),
                    "ckpt_name": "",
                }
            return "z_image_unet", {
                "unet": _first(assets["unet"], unet),
                "text_encoder": _first(assets["clip"], text_encoder),
                "vae": _first(assets["vae"], vae or "ae.safetensors"),
                "ckpt_name": "",
            }
        if assets["checkpoints"]:
            return "sd15_ckpt", {
                "ckpt_name": _first(assets["checkpoints"], ckpt_name),
                "vae": "",
                "unet": "",
                "text_encoder": "",
            }
        raise RuntimeError(
            "未在 ComfyUI 中找到可用生图模型（checkpoints / Z-Image）。"
            "请先在 ComfyUI 界面确认能出图，再到 TOA 重试。"
        )

    ckpt = _first(assets["checkpoints"], ckpt_name)
    if ckpt:
        return "sd15_ckpt", {"ckpt_name": ckpt, "vae": "", "unet": "", "text_encoder": ""}
    raise RuntimeError(f"不支持的 ComfyUI 工作流：{workflow}")


def _build_sd15_ckpt_workflow(
    prompt: str,
    *,
    negative: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    ckpt_name: str = "",
    cfg_scale: float = 7.0,
) -> dict[str, Any]:
    seed = int(time.time() * 1000) % (2**31)
    ckpt = ckpt_name or "v1-5-pruned-emaonly.safetensors"
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": float(cfg_scale),
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


def _build_z_image_turbo_unet_workflow(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 1024,
    steps: int = 8,
    unet: str = "",
    text_encoder: str = "",
    vae: str = "ae.safetensors",
    cfg_scale: float = 1.0,
) -> dict[str, Any]:
    """Z-Image Turbo safetensors（原生 UNETLoader，无需 GGUF 插件）。"""
    seed = int(time.time() * 1000) % (2**31)
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet or "z_image_turbo_bf16.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": text_encoder or "qwen_3_4b.safetensors",
                "type": "lumina2",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae or "ae.safetensors"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["2", 0]},
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": float(cfg_scale),
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "toa3_zimage", "images": ["8", 0]},
        },
    }


def _build_z_image_turbo_gguf_workflow(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 1024,
    steps: int = 8,
    unet: str = "",
    text_encoder: str = "",
    vae: str = "ae.safetensors",
    cfg_scale: float = 1.5,
) -> dict[str, Any]:
    """Z-Image Turbo GGUF（需 ComfyUI-GGUF 等节点）。"""
    seed = int(time.time() * 1000) % (2**31)
    unet_name = unet or "z_image_turbo-Q5_K_S.gguf"
    te_name = text_encoder or "Qwen3-4B.gguf"
    vae_name = vae or "ae.safetensors"
    return {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": unet_name},
        },
        "2": {
            "class_type": "CLIPLoaderGGUF",
            "inputs": {"clip_name": te_name, "type": "lumina2"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["2", 0]},
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": float(cfg_scale),
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "toa3_zimage", "images": ["8", 0]},
        },
    }


def _load_workflow_asset(name: str) -> dict[str, Any] | None:
    path = project_root() / "assets" / "samples" / "comfyui" / name
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _build_workflow(
    prompt: str,
    *,
    width: int,
    height: int,
    steps: int,
    ckpt_name: str,
    workflow: str,
    unet: str,
    text_encoder: str,
    vae: str,
    cfg_scale: float,
) -> dict[str, Any]:
    kind = (workflow or "sd15_ckpt").strip().lower()
    if kind in ("z_image_unet", "z_image_turbo", "z_image", "zimage"):
        return _build_z_image_turbo_unet_workflow(
            prompt,
            width=width,
            height=height,
            steps=steps,
            unet=unet,
            text_encoder=text_encoder,
            vae=vae,
            cfg_scale=cfg_scale if cfg_scale else 1.0,
        )
    if kind in ("z_image_turbo_gguf", "z_image_gguf"):
        asset = _load_workflow_asset("z_image_turbo_gguf_api.json")
        if asset:
            wf = json.loads(json.dumps(asset))
            for node in wf.values():
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs") or {}
                ct = str(node.get("class_type") or "")
                if ct == "CLIPTextEncode" and "text" in inputs and inputs.get("text") == "{{PROMPT}}":
                    inputs["text"] = prompt
                if ct == "UnetLoaderGGUF" and unet:
                    inputs["unet_name"] = unet
                if ct == "CLIPLoaderGGUF" and text_encoder:
                    inputs["clip_name"] = text_encoder
                if ct == "VAELoader" and vae:
                    inputs["vae_name"] = vae
                if ct == "EmptyLatentImage":
                    inputs["width"] = width
                    inputs["height"] = height
                if ct == "KSampler":
                    inputs["steps"] = steps
                    inputs["cfg"] = cfg_scale
                    inputs["seed"] = int(time.time() * 1000) % (2**31)
            return wf
        return _build_z_image_turbo_gguf_workflow(
            prompt,
            width=width,
            height=height,
            steps=steps,
            unet=unet,
            text_encoder=text_encoder,
            vae=vae,
            cfg_scale=cfg_scale,
        )
    return _build_sd15_ckpt_workflow(
        prompt,
        width=width,
        height=height,
        steps=steps,
        ckpt_name=ckpt_name,
        cfg_scale=cfg_scale if cfg_scale != 1.5 else 7.0,
    )


def _format_comfy_error(resp_text: str) -> str:
    """把 ComfyUI JSON 错误翻成白话。"""
    raw = (resp_text or "").strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return raw[:400]
    err = obj.get("error") if isinstance(obj, dict) else None
    node_errors = obj.get("node_errors") if isinstance(obj, dict) else None
    parts: list[str] = []
    if isinstance(err, dict):
        parts.append(str(err.get("message") or err.get("type") or "提交失败"))
    if isinstance(node_errors, dict):
        for nid, info in node_errors.items():
            if not isinstance(info, dict):
                continue
            for e in info.get("errors") or []:
                if not isinstance(e, dict):
                    continue
                et = str(e.get("type") or "")
                msg = str(e.get("message") or "")
                details = str(e.get("details") or "")
                if et == "value_not_in_list":
                    parts.append(
                        f"节点 {nid} 的模型名不在 ComfyUI 列表中"
                        + (f"（{details}）" if details else "")
                        + "。TOA 会自动选用本机已有模型，请重试；"
                        "或确认 ComfyUI 里该文件仍存在。"
                    )
                elif msg:
                    parts.append(f"节点 {nid}：{msg}")
    return "；".join(parts) if parts else raw[:400]


def generate_image(
    base_url: str,
    prompt: str,
    *,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    ckpt_name: str = "",
    workflow: str = "sd15_ckpt",
    unet: str = "",
    text_encoder: str = "",
    vae: str = "ae.safetensors",
    cfg_scale: float = 7.0,
    timeout: float = 180.0,
) -> bytes:
    """提交工作流并轮询 history，返回 PNG 字节。"""
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("ComfyUI 地址未配置")

    resolved_wf, assets = resolve_workflow_and_assets(
        base,
        workflow=workflow,
        ckpt_name=ckpt_name,
        unet=unet,
        text_encoder=text_encoder,
        vae=vae,
        timeout=min(5.0, timeout),
    )
    use_steps = steps
    use_cfg = float(cfg_scale)
    if resolved_wf.startswith("z_image"):
        if steps >= 15:
            use_steps = 8
        if abs(use_cfg - 7.0) < 0.01 or use_cfg > 3:
            use_cfg = 1.0

    graph = _build_workflow(
        prompt,
        width=max(64, min(2048, int(width))),
        height=max(64, min(2048, int(height))),
        steps=max(1, min(60, int(use_steps))),
        ckpt_name=assets.get("ckpt_name") or ckpt_name,
        workflow=resolved_wf,
        unet=assets.get("unet") or unet,
        text_encoder=assets.get("text_encoder") or text_encoder,
        vae=assets.get("vae") or vae or "ae.safetensors",
        cfg_scale=use_cfg,
    )
    client_id = str(uuid.uuid4())
    body = {"prompt": graph, "client_id": client_id}
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("需要 httpx 调用 ComfyUI") from exc

    logger.info(
        "ComfyUI generate workflow=%s unet=%s clip=%s vae=%s ckpt=%s",
        resolved_wf,
        assets.get("unet") or "",
        assets.get("text_encoder") or "",
        assets.get("vae") or "",
        assets.get("ckpt_name") or "",
    )

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            urljoin(base + "/", "prompt"),
            content=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"提交失败 HTTP {resp.status_code}: {_format_comfy_error(resp.text)}")
        payload = resp.json()
        node_errors = payload.get("node_errors") if isinstance(payload, dict) else None
        if isinstance(node_errors, dict) and node_errors:
            raise RuntimeError(_format_comfy_error(json.dumps(payload, ensure_ascii=False)))
        prompt_id = str(payload.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError("ComfyUI 未返回任务号")

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
                    raise RuntimeError("任务完成但未找到输出图像")
            time.sleep(0.8)
        raise RuntimeError("生图超时，请检查 ComfyUI 是否已加载模型")


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
