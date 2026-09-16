# -*- coding: utf-8 -*-
"""助教打卡换装服务：枚举目录、着装预设、参考图编辑、旁路落盘。"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger("TOA3.assistant_outfit_swap")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# 硬约束写入每条 prompt：只换服装，水印/其它信息不变
_PRESERVE_RULES = (
    "CRITICAL CONSTRAINTS: Only change the person's clothing/outfit. "
    "Keep the exact same face, hair, skin, body pose, camera angle, and background. "
    "Do NOT remove, alter, blur, move, or regenerate any watermark, timestamp, logo, "
    "corner badge, caption text, or other overlaid information — copy them unchanged. "
    "Do NOT change identity. Photorealistic training check-in photo."
)

CancelCheck = Callable[[], bool]
ProgressCb = Callable[[int, int, str], None]  # done, total, message


@dataclass(frozen=True)
class OutfitPreset:
    id: str
    label: str
    garment: str  # English garment cue for edit models


OUTFIT_PRESETS: tuple[OutfitPreset, ...] = (
    OutfitPreset(
        "suit",
        "西服",
        "formal dark business suit with tie, professional training assistant attire",
    ),
    OutfitPreset(
        "white_shirt",
        "白衬衫",
        "crisp white business shirt, neat collar, professional office look",
    ),
    OutfitPreset(
        "business_casual",
        "商务休闲",
        "smart business-casual blazer over neat shirt, polished but relaxed",
    ),
    OutfitPreset(
        "women_formal",
        "女装商务正装",
        "women's formal business attire, tailored blazer and blouse, professional",
    ),
)


@dataclass
class ItemResult:
    source: str
    ok: bool
    output: str = ""
    error: str = ""


@dataclass
class BatchResult:
    total: int = 0
    ok_count: int = 0
    fail_count: int = 0
    out_dir: str = ""
    items: list[ItemResult] = field(default_factory=list)


def preset_by_id(preset_id: str) -> OutfitPreset | None:
    pid = (preset_id or "").strip()
    for p in OUTFIT_PRESETS:
        if p.id == pid:
            return p
    return None


def build_edit_prompt(preset: OutfitPreset) -> str:
    return (
        f"Change ONLY the clothing to: {preset.garment}. "
        f"{_PRESERVE_RULES}"
    )


def list_images(folder: str | Path, *, recursive: bool = False) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        return []
    paths: list[Path] = []
    iterator = root.rglob("*") if recursive else root.iterdir()
    for p in iterator:
        if not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        # 跳过本模块旁路输出目录内文件，避免二次换装
        if any(part.startswith("_换装_") for part in p.parts):
            continue
        paths.append(p)
    paths.sort(key=lambda x: x.name.lower())
    return paths


def sidecar_output_dir(src_dir: Path, preset: OutfitPreset) -> Path:
    return src_dir / f"_换装_{preset.label}"


def list_edit_capable_profiles() -> list[dict]:
    """支持参考图编辑的 image_gen 配置（进页不强制探测是否 READY）。"""
    from services.model_catalog import list_profiles

    rows: list[dict] = []
    for prof in list_profiles("image_gen"):
        provider = str(prof.get("provider") or "").strip().lower()
        supports = bool(prof.get("supports_edit"))
        if provider in ("openai_images", "evolink_images") or supports:
            rows.append(dict(prof))
    return rows


def pick_default_edit_profile_id() -> str:
    from services.compute_source import list_ready_catalog_profiles, pick_effective_profile_id
    from services.model_catalog import get_active_profile_id

    edit_ids = {str(p.get("id") or "") for p in list_edit_capable_profiles()}
    active = str(get_active_profile_id("image_gen") or "").strip()
    if active in edit_ids:
        return active
    ready = list_ready_catalog_profiles("image_gen")
    for row in ready:
        pid = str(row.get("id") or "")
        if pid in edit_ids:
            return pid
    # 未就绪也回落：优先豆包 Seedream
    if "doubao_seedream" in edit_ids:
        return "doubao_seedream"
    return next(iter(edit_ids), "") or pick_effective_profile_id("image_gen") or ""


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            return max(64, int(w)), max(64, int(h))
    except Exception:
        return 1024, 1024


def swap_one(
    src: Path,
    *,
    preset: OutfitPreset,
    out_dir: Path,
    profile_id: str,
) -> ItemResult:
    from services.integrations import get_client

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / src.name
    try:
        client = get_client("image_gen")
        w, h = _image_size(src)
        # 云端编辑常有边长上限，钳制到合理范围且保持比例
        max_side = 2048
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            w = max(64, int(w * scale))
            h = max(64, int(h * scale))
        prompt = build_edit_prompt(preset)
        tmp = client.edit(
            prompt,
            src,
            width=w,
            height=h,
            profile_id=profile_id or None,
        )
        tmp_path = Path(tmp)
        if tmp_path.resolve() != dest.resolve():
            shutil.copy2(tmp_path, dest)
        return ItemResult(source=str(src), ok=True, output=str(dest))
    except Exception as exc:
        msg = str(getattr(exc, "user_message", None) or exc)
        logger.warning("换装失败 %s: %s", src, msg)
        return ItemResult(source=str(src), ok=False, error=msg)


def run_batch(
    folder: str | Path,
    *,
    preset_id: str,
    profile_id: str,
    recursive: bool = False,
    progress: ProgressCb | None = None,
    cancel_check: CancelCheck | None = None,
) -> BatchResult:
    preset = preset_by_id(preset_id)
    if preset is None:
        raise ValueError("请选择有效的着装预设。")
    root = Path(folder)
    if not root.is_dir():
        raise ValueError("请选择有效的照片目录。")
    if not (profile_id or "").strip():
        raise ValueError("请选择支持参考图编辑的生图模型（如豆包 Seedream）。")

    images = list_images(root, recursive=recursive)
    result = BatchResult(total=len(images), out_dir=str(sidecar_output_dir(root, preset)))
    if not images:
        raise ValueError("目录下没有可处理的图片（jpg/png/webp 等）。")

    out_dir = Path(result.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, src in enumerate(images, start=1):
        if cancel_check and cancel_check():
            result.items.append(
                ItemResult(source=str(src), ok=False, error="已取消")
            )
            result.fail_count += 1
            break
        if progress:
            progress(i - 1, len(images), f"正在处理 {src.name}（{i}/{len(images)}）")
        item = swap_one(src, preset=preset, out_dir=out_dir, profile_id=profile_id)
        result.items.append(item)
        if item.ok:
            result.ok_count += 1
        else:
            result.fail_count += 1
        if progress:
            progress(i, len(images), f"{'完成' if item.ok else '失败'} {src.name}")

    return result
