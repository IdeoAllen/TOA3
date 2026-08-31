# -*- coding: utf-8 -*-
"""ImageGen provider: sdcpp（本机简易 · stable-diffusion.cpp）。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from services.local_image_runtime import generate_png, install_status


def is_ready() -> bool:
    return bool(install_status().get("ready"))


def generate_image(
    prompt: str,
    *,
    width: int = 768,
    height: int = 768,
    steps: int = 8,
    cfg_scale: float = 1.0,
    timeout: float = 600.0,
    offload_to_cpu: bool = True,
) -> bytes:
    """生成并返回 PNG 字节。"""
    path = generate_png(
        prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
        timeout=timeout,
        offload_to_cpu=offload_to_cpu,
    )
    data = path.read_bytes()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return data


def generate_to_path(
    prompt: str,
    dest: Path,
    *,
    width: int = 768,
    height: int = 768,
    steps: int = 8,
    cfg_scale: float = 1.0,
    timeout: float = 600.0,
    prof: dict[str, Any] | None = None,
) -> Path:
    cfg = float((prof or {}).get("cfg_scale") or cfg_scale)
    st = int((prof or {}).get("steps") or steps)
    offload = bool((prof or {}).get("offload_to_cpu", True))
    tmp = generate_png(
        prompt,
        width=width,
        height=height,
        steps=st,
        cfg_scale=cfg,
        timeout=timeout,
        offload_to_cpu=offload,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return dest.resolve()
