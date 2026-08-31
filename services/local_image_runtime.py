# -*- coding: utf-8 -*-
"""本机简易生图运行时（stable-diffusion.cpp + Z-Image Turbo GGUF）。

小白路径：导入离线包或自备二进制+权重 → 媒体工坊写提示词出图。
不暴露 ComfyUI / 工作流概念。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from services.config_service import project_root

logger = logging.getLogger("TOA3.local_image")

_RUNTIME_DIR_NAME = "image-runtime"
_WEIGHT_DIR_REL = Path("data") / "models" / "image" / "z_image_turbo"
_MANIFEST_NAME = "install.json"
_BIN_NAMES = ("sd-cli.exe", "sd.exe", "sd-cli", "sd")


def runtime_root() -> Path:
    env = (os.environ.get("TOA_IMAGE_RUNTIME") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".toa3" / _RUNTIME_DIR_NAME).resolve()


def weights_root() -> Path:
    return (project_root() / _WEIGHT_DIR_REL).resolve()


def manifest_path() -> Path:
    return weights_root() / _MANIFEST_NAME


def find_sd_binary() -> Path | None:
    root = runtime_root()
    if root.is_dir():
        for name in _BIN_NAMES:
            p = root / name
            if p.is_file():
                return p
        for p in root.rglob("*"):
            if p.is_file() and p.name.lower() in {n.lower() for n in _BIN_NAMES}:
                return p
    which = shutil.which("sd-cli") or shutil.which("sd")
    if which:
        return Path(which)
    return None


def _pick_file(directory: Path, *, suffixes: tuple[str, ...], prefer_sub: str = "") -> Path | None:
    if not directory.is_dir():
        return None
    cands: list[Path] = []
    for p in directory.rglob("*"):
        if p.is_file() and p.suffix.lower() in suffixes:
            cands.append(p)
    if not cands:
        return None
    if prefer_sub:
        preferred = [p for p in cands if prefer_sub.lower() in p.name.lower()]
        if preferred:
            cands = preferred
    # 偏好更大文件（更高量化通常更大）但 Q3 也可用；按名称稳定排序
    cands.sort(key=lambda p: (p.stat().st_size, p.name), reverse=True)
    return cands[0]


def find_diffusion_gguf() -> Path | None:
    return _pick_file(weights_root(), suffixes=(".gguf",), prefer_sub="z_image")


def find_diffusion_model() -> Path | None:
    """生图主模型：优先 z_image GGUF，其次完整 safetensors。"""
    hit = find_diffusion_gguf()
    if hit is not None:
        return hit
    root = weights_root()
    cands: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() != ".safetensors":
            continue
        name = p.name.lower()
        if "z_image" in name or "z-image" in name:
            try:
                if p.stat().st_size >= 10_000_000_000:
                    cands.append(p)
            except OSError:
                continue
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_size, reverse=True)
    return cands[0]


def find_vae() -> Path | None:
    root = weights_root()
    for name in ("ae.safetensors", "ae.sft", "ae.gguf"):
        p = root / name
        if p.is_file():
            return p
    return _pick_file(root, suffixes=(".safetensors", ".sft", ".gguf"), prefer_sub="ae")


def find_text_encoder() -> Path | None:
    root = weights_root()
    hit = _pick_file(root, suffixes=(".gguf", ".safetensors"), prefer_sub="qwen")
    if hit and hit != find_diffusion_gguf():
        return hit
    # 排除 diffusion 本体
    diff = find_diffusion_model()
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".gguf", ".safetensors"):
            continue
        if diff and p.resolve() == diff.resolve():
            continue
        name = p.name.lower()
        if "ae." in name or name.startswith("ae"):
            continue
        if "qwen" in name or "llm" in name or "text" in name or "clip" in name:
            return p
    return None


def read_manifest() -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_manifest(data: dict[str, Any]) -> None:
    weights_root().mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    manifest_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def install_status() -> dict[str, Any]:
    """探测 L1 是否可生成。"""
    binary = find_sd_binary()
    diffusion = find_diffusion_model()
    vae = find_vae()
    text_enc = find_text_encoder()
    missing: list[str] = []
    if binary is None:
        missing.append("运行时（sd-cli）")
    if diffusion is None:
        missing.append("生图模型文件")
    if vae is None:
        missing.append("画面还原组件（VAE）")
    if text_enc is None:
        missing.append("文字理解组件")
    ready = not missing
    man = read_manifest()
    return {
        "ready": ready,
        "missing": missing,
        "binary": str(binary) if binary else "",
        "diffusion": str(diffusion) if diffusion else "",
        "vae": str(vae) if vae else "",
        "text_encoder": str(text_enc) if text_enc else "",
        "weights_dir": str(weights_root()),
        "runtime_dir": str(runtime_root()),
        "quant_hint": str(man.get("quant") or man.get("label") or ""),
        "user_hint": (
            "已安装，可在媒体工坊生图"
            if ready
            else "请「导入离线包」或按指引放入模型与运行时（详见安装向导）"
        ),
    }


def recommend_quant_label(vram_gb: float | None = None) -> str:
    """按显存推荐量化档（白话标签）。"""
    if vram_gb is None:
        return "均衡（约 6–8GB 显存 · Q4/Q5）"
    if vram_gb <= 4.5:
        return "低配（约 4GB 显存 · Q3/Q4）"
    if vram_gb <= 8.5:
        return "均衡（约 6–8GB 显存 · Q4/Q5）"
    return "高配（更高显存 · Q5/Q8）"


def import_offline_pack(pack_dir: Path | str) -> tuple[bool, str]:
    """
    从离线包目录导入运行时与权重。

    期望结构（灵活识别）：
      pack/
        manifest.json          # 可选
        runtime/ 或 bin/       # sd-cli*
        models/ 或 weights/ 或 根目录下的 gguf/safetensors
    """
    src = Path(pack_dir).expanduser().resolve()
    if not src.is_dir():
        return False, "请选择有效的离线包文件夹。"

    runtime_dst = runtime_root()
    weights_dst = weights_root()
    runtime_dst.mkdir(parents=True, exist_ok=True)
    weights_dst.mkdir(parents=True, exist_ok=True)

    copied_bin = 0
    copied_w = 0

    # 找二进制
    bin_candidates: list[Path] = []
    for sub in ("runtime", "bin", "sdcpp", "."):
        base = src if sub == "." else src / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.name.lower() in {n.lower() for n in _BIN_NAMES}:
                bin_candidates.append(p)
    for p in bin_candidates:
        dest = runtime_dst / p.name
        shutil.copy2(p, dest)
        copied_bin += 1

    # 找权重
    weight_roots = [src / "models", src / "weights", src / "z_image_turbo", src]
    seen: set[str] = set()
    for base in weight_roots:
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".gguf", ".safetensors", ".sft", ".json"):
                continue
            if p.name == _MANIFEST_NAME and p.parent == src:
                continue
            key = p.name.lower()
            if key in seen:
                continue
            seen.add(key)
            shutil.copy2(p, weights_dst / p.name)
            copied_w += 1

    # 包内 manifest
    for cand in (src / "manifest.json", src / _MANIFEST_NAME):
        if cand.is_file():
            try:
                meta = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    write_manifest({**meta, "source": "offline_pack", "pack_path": str(src)})
            except Exception:
                pass
            break
    else:
        write_manifest({"source": "offline_pack", "pack_path": str(src)})

    st = install_status()
    if st["ready"]:
        return True, "本机生图已就绪，可到「媒体工坊」生成图片。"
    if copied_bin == 0 and copied_w == 0:
        return False, "离线包里未找到运行时或模型文件，请检查文件夹结构。"
    miss = "、".join(st["missing"]) or "组件"
    return False, f"已复制部分文件，仍缺：{miss}。请换完整离线包或补齐后重试。"


def generate_png(
    prompt: str,
    *,
    width: int = 768,
    height: int = 768,
    steps: int = 8,
    cfg_scale: float = 1.0,
    timeout: float = 600.0,
    offload_to_cpu: bool = True,
) -> Path:
    """调用 sd-cli 生成 PNG，写入临时再返回路径（由调用方搬到 output）。"""
    st = install_status()
    if not st["ready"]:
        miss = "、".join(st["missing"]) or "组件"
        raise RuntimeError(f"本机生图尚未装好（缺：{miss}）。请到模型库安装或导入离线包。")

    binary = Path(st["binary"])
    diffusion = Path(st["diffusion"])
    vae = Path(st["vae"])
    text_enc = Path(st["text_encoder"])

    out_dir = weights_root() / "_gen_tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"toa_{time.strftime('%Y%m%d_%H%M%S')}.png"

    cmd = [
        str(binary),
        "--diffusion-model",
        str(diffusion),
        "--vae",
        str(vae),
        "--llm",
        str(text_enc),
        "-p",
        prompt,
        "-o",
        str(out_path),
        "-W",
        str(max(64, min(2048, int(width)))),
        "-H",
        str(max(64, min(2048, int(height)))),
        "--steps",
        str(max(1, min(30, int(steps)))),
        "--cfg-scale",
        str(float(cfg_scale)),
    ]
    if offload_to_cpu:
        cmd.append("--offload-to-cpu")
    # Flash attention when available（失败则由二进制忽略未知参数时仍可能报错，故可选）
    cmd.append("--diffusion-fa")

    logger.info("sdcpp generate: %s", " ".join(cmd[:8]) + " …")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(binary.parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("生图超时，请减小尺寸或换更低配模型档。") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("找不到本机生图程序，请重新导入离线包。") from exc

    if proc.returncode != 0 or not out_path.is_file():
        err = (proc.stderr or proc.stdout or "").strip()
        # 部分构建不支持 --diffusion-fa：去掉重试一次
        if "--diffusion-fa" in cmd and proc.returncode != 0:
            cmd2 = [c for c in cmd if c != "--diffusion-fa"]
            proc2 = subprocess.run(
                cmd2,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(binary.parent),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if proc2.returncode == 0 and out_path.is_file():
                return out_path.resolve()
            err = (proc2.stderr or proc2.stdout or err).strip()
        hint = err[-400:] if err else f"退出码 {proc.returncode}"
        raise RuntimeError(f"本机生图失败：{hint}")

    return out_path.resolve()
