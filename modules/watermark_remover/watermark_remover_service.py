# -*- coding: utf-8 -*-
"""
去图片水印服务（MVP）。

优先走 integrations.get_client('watermark_ai')；
未配置时对选区（或右下角启发式区域）做 inpaint / 模糊。
OpenCV 可用时用 Telea inpaint；否则 PIL 高斯模糊。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

try:
    import cv2
    import numpy as np

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    _HAS_CV2 = False


@dataclass
class RemoveResult:
    ok: bool
    output_path: str = ""
    engine: str = ""
    message: str = ""


Region = Tuple[int, int, int, int]  # x, y, w, h in image pixels


def _corner_roi(h: int, w: int) -> Region:
    """右下角常见角标区域。"""
    rw, rh = max(80, int(w * 0.38)), max(64, int(h * 0.28))
    return w - rw, h - rh, rw, rh


def _clamp_region(h: int, w: int, region: Region | None) -> Region:
    if region is None:
        return _corner_roi(h, w)
    x, y, bw, bh = region
    x = max(0, min(int(x), w - 1))
    y = max(0, min(int(y), h - 1))
    bw = max(1, min(int(bw), w - x))
    bh = max(1, min(int(bh), h - y))
    return x, y, bw, bh


def _imread_bgr(path: str):
    if not _HAS_CV2:
        return None
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is not None:
        return img
    try:
        with Image.open(path) as pil:
            return cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.error("读取失败 %s: %s", path, exc)
        return None


def _imwrite_bgr(path: str, bgr) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ext = out.suffix.lower() or ".jpg"
    if ext == ".jpeg":
        ext = ".jpg"
    params = []
    if ext in (".jpg", ".jpeg"):
        params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
    elif ext == ".png":
        params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]
    ok, buf = cv2.imencode(ext, bgr, params)
    if not ok:
        raise RuntimeError(f"编码失败: {path}")
    buf.tofile(str(out))


def _inpaint_region_cv2(bgr, region: Region):
    """仅在选区内做局部 inpaint。"""
    h, w = bgr.shape[:2]
    x, y, bw, bh = _clamp_region(h, w, region)
    mask = np.zeros((h, w), dtype=np.uint8)
    roi = bgr[y : y + bh, x : x + bw]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (0, 0), 1.6)
    diff = cv2.absdiff(gray, blur)
    _, th = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edges = cv2.Canny(gray, 40, 120)
    local = cv2.bitwise_or(th, edges)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    local = cv2.dilate(local, k, iterations=2)
    ratio = float(np.count_nonzero(local)) / float(local.size)
    if ratio < 0.004 or ratio > 0.55:
        mask[y : y + bh, x : x + bw] = 255
    else:
        mask[y : y + bh, x : x + bw] = local
    return cv2.inpaint(bgr, mask, 5, cv2.INPAINT_TELEA)


def _blur_region_cv2(bgr, region: Region):
    out = bgr.copy()
    h, w = out.shape[:2]
    x, y, bw, bh = _clamp_region(h, w, region)
    roi = out[y : y + bh, x : x + bw]
    k = max(21, (min(bw, bh) // 8) | 1)
    blurred = cv2.GaussianBlur(roi, (k, k), 0)
    mask = np.zeros((bh, bw), dtype=np.float32)
    pad = max(4, min(bw, bh) // 10)
    mask[pad : bh - pad, pad : bw - pad] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), pad / 2.0)
    m = mask[..., None]
    blended = (blurred.astype(np.float32) * m + roi.astype(np.float32) * (1.0 - m)).astype(
        np.uint8
    )
    out[y : y + bh, x : x + bw] = blended
    return out


def _mild_blur_all_corners(bgr):
    out = bgr.copy()
    h, w = out.shape[:2]
    rw, rh = max(48, int(w * 0.22)), max(40, int(h * 0.18))
    corners = ((0, 0), (w - rw, 0), (0, h - rh), (w - rw, h - rh))
    for x, y in corners:
        bw, bh = min(rw, w - x), min(rh, h - y)
        roi = out[y : y + bh, x : x + bw]
        k = max(11, (min(bw, bh) // 12) | 1)
        soft = cv2.GaussianBlur(roi, (k, k), 0)
        mask = np.zeros((bh, bw), dtype=np.float32)
        pad = max(3, min(bw, bh) // 8)
        mask[pad : bh - pad, pad : bw - pad] = 0.55
        mask = cv2.GaussianBlur(mask, (0, 0), pad / 2.0)
        m = mask[..., None]
        out[y : y + bh, x : x + bw] = (
            soft.astype(np.float32) * m + roi.astype(np.float32) * (1.0 - m)
        ).astype(np.uint8)
    return out


def _blur_region_pil(path: str, dest: str, region: Region | None) -> None:
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        x, y, bw, bh = _clamp_region(h, w, region)
        box = (x, y, x + bw, y + bh)
        crop = rgb.crop(box)
        radius = max(8, min(bw, bh) // 12)
        blurred = crop.filter(ImageFilter.GaussianBlur(radius=radius))
        out = rgb.copy()
        out.paste(blurred, box)
        out_path = Path(dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        save_kw = {}
        ext = out_path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            save_kw["quality"] = 95
        out.save(str(out_path), **save_kw)


def remove_watermark(
    image_path: str | Path,
    output_path: str | Path,
    *,
    prefer_ai: bool = False,
    mild_corner_blur: bool = False,
    region: Region | None = None,
    boxes: list[Region] | None = None,
    brush_mask: object | None = None,
) -> RemoveResult:
    """去除单张图片水印并写到 output_path。

    顺序：watermark_ai → TOA2 处理器（框/涂抹/自动角标检测）→ 旧 inpaint 回退。
    """
    src = str(image_path)
    dest = str(output_path)

    if prefer_ai:
        try:
            from services.integrations import get_client

            client = get_client("watermark_ai")
            # 仅当 LaMa 真就绪才走 AI，避免占位 raise 刷日志
            if getattr(client, "enabled", False) and client.health_check():
                try:
                    out = client.remove_watermark(
                        src,
                        output_path=dest,
                        region=region,
                        boxes=boxes,
                        brush_mask=brush_mask,
                    )
                    if out:
                        p = Path(out)
                        if p.is_file() and str(p.resolve()) != str(Path(dest).resolve()):
                            data = p.read_bytes()
                            Path(dest).parent.mkdir(parents=True, exist_ok=True)
                            Path(dest).write_bytes(data)
                        elif p.is_file():
                            dest = str(p)
                        note = "AI 去水印完成（LaMa）"
                        if mild_corner_blur:
                            note += "（未再做四角模糊；AI 结果优先保留）"
                        return RemoveResult(True, dest, "watermark_ai+lama", note)
                except Exception as exc:
                    logger.info("AI 去水印不可用，回退本地: %s", exc)
        except Exception as exc:
            logger.debug("未加载 watermark_ai: %s", exc)

    # TOA2 完整处理器（角标检测 + 涂抹 + 多级修复）
    if _HAS_CV2:
        try:
            from modules.watermark_remover.watermark_remover_processor import WatermarkRemoverProcessor

            proc = WatermarkRemoverProcessor()
            bgr = proc.imread(src)
            if bgr is None:
                return RemoveResult(False, "", "", f"无法读取图片: {src}")

            use_boxes: list[Region] = list(boxes or [])
            has_brush = False
            mask_np = None
            if brush_mask is not None:
                mask_np = np.asarray(brush_mask)
                if mask_np.ndim == 2 and np.any(mask_np):
                    has_brush = True
                    use_boxes = []

            if not has_brush:
                if not use_boxes and region is not None:
                    use_boxes = [_clamp_region(bgr.shape[0], bgr.shape[1], region)]
                if not use_boxes:
                    detected = proc.detect_boxes(bgr)
                    if detected:
                        use_boxes = list(detected)

            repaired = proc.remove_with_boxes(
                bgr,
                use_boxes,
                mask_np if has_brush else None,
                method="auto",
                radius=5,
            )
            if mild_corner_blur:
                repaired = _mild_blur_all_corners(repaired)
            proc.save_image(dest, repaired)
            engine = "toa2_processor"
            if has_brush:
                engine += "+brush"
            elif use_boxes:
                engine += "+boxes"
            else:
                engine += "+auto_detect"
            return RemoveResult(True, dest, engine, f"本地修复完成（{engine}）")
        except Exception as exc:
            logger.warning("TOA2 处理器失败，回退简易 inpaint: %s", exc)

    if _HAS_CV2:
        bgr = _imread_bgr(src)
        if bgr is None:
            return RemoveResult(False, "", "", f"无法读取图片: {src}")
        engine = "opencv_inpaint"
        try:
            repaired = _inpaint_region_cv2(bgr, region)
        except Exception as exc:
            logger.warning("inpaint 失败，使用选区模糊: %s", exc)
            repaired = _blur_region_cv2(bgr, region)
            engine = "region_blur"
        if mild_corner_blur:
            repaired = _mild_blur_all_corners(repaired)
            engine = f"{engine}+mild_corners"
        try:
            _imwrite_bgr(dest, repaired)
        except Exception as exc:
            return RemoveResult(False, "", engine, f"保存失败: {exc}")
        return RemoveResult(True, dest, engine, f"本地修复完成（{engine}）")

    # 无 OpenCV：PIL 仅对选区模糊
    try:
        _blur_region_pil(src, dest, region)
    except Exception as exc:
        return RemoveResult(False, "", "pil_blur", f"PIL 模糊失败: {exc}")
    return RemoveResult(True, dest, "pil_blur", "本地修复完成（pil_blur，选区模糊）")


@dataclass
class PreviewResult:
    ok: bool
    png_bytes: bytes = b""
    message: str = ""


def preview_remove(
    image_path: str | Path,
    *,
    mild_corner_blur: bool = False,
    region: Region | None = None,
    boxes: list[Region] | None = None,
    brush_mask: object | None = None,
) -> PreviewResult:
    """实时效果预览：仅本地处理器（跳过 AI），返回 PNG 字节。"""
    src = str(image_path)
    if not _HAS_CV2:
        return PreviewResult(False, b"", "预览需要 OpenCV（opencv-python）")

    try:
        from modules.watermark_remover.watermark_remover_processor import WatermarkRemoverProcessor

        proc = WatermarkRemoverProcessor()
        bgr = proc.imread(src)
        if bgr is None:
            return PreviewResult(False, b"", f"无法读取图片: {src}")

        use_boxes: list[Region] = list(boxes or [])
        has_brush = False
        mask_np = None
        if brush_mask is not None:
            mask_np = np.asarray(brush_mask)
            if mask_np.ndim == 2 and np.any(mask_np):
                has_brush = True
                use_boxes = []

        if not has_brush:
            if not use_boxes and region is not None:
                use_boxes = [_clamp_region(bgr.shape[0], bgr.shape[1], region)]
            if not use_boxes:
                return PreviewResult(False, b"", "请先在左侧标记水印区域")

        repaired = proc.remove_with_boxes(
            bgr,
            use_boxes,
            mask_np if has_brush else None,
            method="auto",
            radius=5,
        )
        if mild_corner_blur:
            repaired = _mild_blur_all_corners(repaired)

        ok, buf = cv2.imencode(".png", repaired)
        if not ok:
            return PreviewResult(False, b"", "预览编码失败")
        return PreviewResult(True, bytes(buf), "预览完成")
    except Exception as exc:
        logger.warning("效果预览失败: %s", exc)
        return PreviewResult(False, b"", f"预览失败: {exc}")
