# -*- coding: utf-8 -*-
"""本机去水印 · LaMa 运行时（big-lama.pt + PyTorch）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from services.config_service import project_root
from services.local_image_setup import _download_file, _noop_progress, load_bundle_config

logger = logging.getLogger("TOA3.local_inpaint")

_MODEL = None
_DEVICE = "cpu"
_MODEL_PATH = ""
_DEVICE_CACHED: str | None = None


def weights_root() -> Path:
    cfg = load_bundle_config()
    spec = cfg.get("inpaint_lama") or {}
    rel = str(spec.get("weights_dir") or "data/models/image/inpaint/lama")
    return (project_root() / rel).resolve()


def weights_path() -> Path | None:
    cfg = load_bundle_config()
    spec = (cfg.get("inpaint_lama") or {}).get("weights") or {}
    name = str(spec.get("filename") or "big-lama.pt")
    root = weights_root()
    preferred = root / name
    min_bytes = int(spec.get("min_bytes") or 50_000_000)
    if preferred.is_file() and preferred.stat().st_size >= min_bytes:
        return preferred
    if root.is_dir():
        for p in root.glob("*"):
            if p.is_file() and p.suffix.lower() in (".pt", ".pth", ".ckpt"):
                try:
                    if p.stat().st_size >= min_bytes:
                        return p
                except OSError:
                    continue
    return None


def _detect_device() -> str:
    """探测一次并缓存；不兼容 GPU 安静回落 CPU，避免每次状态查询刷警告。"""
    global _DEVICE_CACHED
    if _DEVICE_CACHED is not None:
        return _DEVICE_CACHED
    try:
        import torch

        if not torch.cuda.is_available():
            _DEVICE_CACHED = "cpu"
            return _DEVICE_CACHED
        try:
            x = torch.zeros(1, device="cuda")
            del x
            torch.cuda.synchronize()
            _DEVICE_CACHED = "cuda"
        except Exception as exc:
            logger.info("CUDA 不可用，LaMa 将用 CPU（可选增强，默认不强制）: %s", exc)
            _DEVICE_CACHED = "cpu"
    except Exception:
        _DEVICE_CACHED = "cpu"
    return _DEVICE_CACHED


def install_status() -> dict[str, Any]:
    has_torch = False
    try:
        import torch  # noqa: F401

        has_torch = True
    except Exception:
        pass
    w = weights_path()
    # 未就绪时不必探 CUDA，减轻低配/进页探测成本
    device = _detect_device() if (has_torch and w is not None) else "cpu"
    missing: list[str] = []
    if not has_torch:
        missing.append("PyTorch")
    if w is None:
        missing.append("LaMa 权重")
    ready = not missing
    return {
        "ready": ready,
        "missing": missing,
        "weights": str(w) if w else "",
        "weights_dir": str(weights_root()),
        "device": device,
        "user_hint": (
            f"LaMa 已就绪（{device}）；勾选「AI 增强」走 lama，不勾仍为 light"
            if ready
            else "未装 LaMa 不影响 light；需要时在去水印页点「安装 AI…」"
        ),
    }


def download_weights(*, progress=None) -> tuple[bool, str]:
    cfg = load_bundle_config()
    spec = (cfg.get("inpaint_lama") or {}).get("weights") or {}
    url = str(spec.get("url") or "").strip()
    filename = str(spec.get("filename") or "big-lama.pt")
    min_bytes = int(spec.get("min_bytes") or 50_000_000)
    if not url:
        return False, "未配置 LaMa 下载地址。"
    dest = weights_root() / filename
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        return True, "LaMa 权重已存在。"
    prog = progress or _noop_progress
    weights_root().mkdir(parents=True, exist_ok=True)
    _download_file(url, dest, progress=prog, label=filename)
    if dest.stat().st_size < min_bytes:
        dest.unlink(missing_ok=True)
        return False, "LaMa 权重下载不完整，请重试。"
    return True, "LaMa 去水印模型已就绪。"


def _pad_mod(x: int, mod: int = 8) -> int:
    return x if x % mod == 0 else x + (mod - x % mod)


def _get_model():
    global _MODEL, _DEVICE, _MODEL_PATH
    w = weights_path()
    if w is None:
        raise FileNotFoundError("未找到 big-lama.pt")
    import torch

    device = _detect_device()
    if _MODEL is not None and _MODEL_PATH == str(w) and _DEVICE == device:
        return _MODEL
    model = torch.jit.load(str(w), map_location="cpu")
    model.eval()
    model.to(device)
    _MODEL = model
    _DEVICE = device
    _MODEL_PATH = str(w)
    return _MODEL


def inpaint(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """LaMa 修复；mask 非 0 为待修复区。"""
    if bgr is None or mask is None or not np.any(mask):
        return bgr.copy() if bgr is not None else bgr

    import torch

    model = _get_model()
    device = _DEVICE

    m = mask
    if m.ndim == 3:
        m = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY)
    user_m = (m > 0).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.dilate(user_m, k, iterations=1)

    h, w = bgr.shape[:2]
    max_side = 1536 if device == "cuda" else 1024
    scale = min(1.0, max_side / float(max(h, w)))
    if scale < 0.999:
        tw, th = max(1, int(w * scale)), max(1, int(h * scale))
        small = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA)
        smask = cv2.resize(m, (tw, th), interpolation=cv2.INTER_NEAREST)
    else:
        small, smask = bgr, m
        tw, th = w, h

    ph, pw = _pad_mod(th), _pad_mod(tw)
    if ph != th or pw != tw:
        pad_img = np.zeros((ph, pw, 3), dtype=np.uint8)
        pad_mask = np.zeros((ph, pw), dtype=np.uint8)
        pad_img[:th, :tw] = small
        pad_mask[:th, :tw] = smask
    else:
        pad_img, pad_mask = small, smask

    rgb = cv2.cvtColor(pad_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    mask_f = (pad_mask > 0).astype(np.float32)
    img_t = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(device)
    mask_t = torch.from_numpy(mask_f).unsqueeze(0).unsqueeze(0).to(device)

    with torch.no_grad():
        out = model(img_t, mask_t)
        if isinstance(out, (tuple, list)):
            out = out[0]
        out = out[0].permute(1, 2, 0).detach().float().cpu().numpy()

    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    out = out[:th, :tw]
    out_bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)

    if scale < 0.999:
        out_full = cv2.resize(out_bgr, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        out_full = out_bgr

    dist = cv2.distanceTransform(user_m, cv2.DIST_L2, 3)
    alpha = np.clip(dist / 1.0, 0.0, 1.0)
    alpha = np.where(user_m > 0, alpha, 0.0).astype(np.float32)[..., None]
    return np.clip(
        bgr.astype(np.float32) * (1.0 - alpha) + out_full.astype(np.float32) * alpha,
        0,
        255,
    ).astype(np.uint8)
