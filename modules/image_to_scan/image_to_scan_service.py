# -*- coding: utf-8 -*-
"""
图片转扫描件服务（自 TOA2 image_to_scan_processor 迁移）。

默认输出「清晰灰度扫描件」：去阴影、提白纸底、保留字迹与表格线。
「黑白强度」拉高才会变成硬二值；硬二值容易伤细节，故默认关闭。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass
class ScanSettings:
    """扫描参数（0–100）。"""

    # 去阴影：越大纸底越白、阴影越少
    shadow_remove: int = 45
    # 清晰度：越大字迹对比越强（仍保持灰度）
    clarity: int = 52
    # 黑白强度：0=清晰灰度扫描（推荐），100=纯黑白二值
    bw_level: int = 0
    # 是否清理边缘大块阴影
    remove_black_blocks: bool = True

    # 兼容旧字段名（页面若仍传 ink/cleanup/contrast）
    @classmethod
    def from_legacy(
        cls,
        *,
        ink_strength: Optional[int] = None,
        cleanup_strength: Optional[int] = None,
        contrast: Optional[int] = None,
        remove_black_blocks: bool = True,
        shadow_remove: Optional[int] = None,
        clarity: Optional[int] = None,
        bw_level: Optional[int] = None,
    ) -> "ScanSettings":
        return cls(
            shadow_remove=int(shadow_remove if shadow_remove is not None else (cleanup_strength if cleanup_strength is not None else 45)),
            clarity=int(clarity if clarity is not None else (contrast if contrast is not None else 52)),
            bw_level=int(bw_level if bw_level is not None else (max(0, 100 - int(ink_strength)) if ink_strength is not None else 0)),
            remove_black_blocks=bool(remove_black_blocks),
        ).clamped()

    def clamped(self) -> "ScanSettings":
        return ScanSettings(
            shadow_remove=int(max(0, min(100, self.shadow_remove))),
            clarity=int(max(0, min(100, self.clarity))),
            bw_level=int(max(0, min(100, self.bw_level))),
            remove_black_blocks=bool(self.remove_black_blocks),
        )


DEFAULT_SETTINGS = ScanSettings()


class ImageToScanProcessor:
    """照片转扫描件（PDF）。"""

    def convert_image(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        *,
        settings: Optional[ScanSettings] = None,
    ) -> Optional[str]:
        try:
            img = self._imread(image_path)
            if img is None:
                raise ValueError(f"无法读取图片: {image_path}")

            scanned = self.to_scan(img, settings=settings or DEFAULT_SETTINGS)
            out = output_path or self.default_output_path(image_path)
            if not out.lower().endswith(".pdf"):
                root, _ = os.path.splitext(out)
                out = f"{root}.pdf"
            os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
            self._save_pdf(out, scanned)
            return out
        except Exception as exc:
            logger.error("转换失败 %s: %s", image_path, exc, exc_info=True)
            return None

    def convert_many(
        self,
        image_paths: List[str],
        output_dir: Optional[str] = None,
        *,
        settings: Optional[ScanSettings] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Tuple[int, int, List[str]]:
        success = 0
        failed: List[str] = []
        total = len(image_paths)
        cfg = settings or DEFAULT_SETTINGS
        for index, path in enumerate(image_paths, start=1):
            if progress_callback:
                progress_callback(index, total, path)
            if output_dir:
                name = os.path.splitext(os.path.basename(path))[0] + "_扫描件.pdf"
                out = os.path.join(output_dir, name)
            else:
                out = self.default_output_path(path)
            if self.convert_image(path, out, settings=cfg):
                success += 1
            else:
                failed.append(path)
        return success, len(failed), failed

    def preview(
        self,
        image_path: str,
        max_side: int = 2400,
        *,
        settings: Optional[ScanSettings] = None,
    ) -> Optional[Image.Image]:
        try:
            pil_img, _ = self.preview_fast(image_path, max_side=max_side, settings=settings)
            return pil_img
        except Exception as exc:
            logger.error("预览失败: %s", exc, exc_info=True)
            return None

    def preview_fast(
        self,
        image_path: str,
        max_side: int = 2400,
        *,
        settings: Optional[ScanSettings] = None,
        cached_bgr: Optional[np.ndarray] = None,
    ) -> Tuple[Optional[Image.Image], Optional[np.ndarray]]:
        """
        预览：用接近导出的分辨率处理，再缩小显示。
        max_side 默认 2400，避免低分辨率预览与导出效果差太多。
        """
        try:
            img = cached_bgr if cached_bgr is not None else self._imread(image_path)
            if img is None:
                raise ValueError(f"无法读取图片: {image_path}")

            h, w = img.shape[:2]
            work = img
            if max_side > 0 and max(h, w) > max_side:
                scale = max_side / float(max(h, w))
                work = cv2.resize(
                    img,
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )

            scanned = self.to_scan(work, settings=settings or DEFAULT_SETTINGS)
            rgb = cv2.cvtColor(scanned, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb), img
        except Exception as exc:
            logger.error("快速预览失败: %s", exc, exc_info=True)
            return None, None

    def to_scan(self, bgr: np.ndarray, *, settings: Optional[ScanSettings] = None) -> np.ndarray:
        """
        彩色图 -> 扫描件。
        默认：灰度清晰扫描（可读）；bw_level 高时再掺入硬二值。
        """
        cfg = (settings or DEFAULT_SETTINGS).clamped()
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        soft = self._soft_scan(gray, cfg)

        if cfg.bw_level <= 8:
            result = soft
        else:
            hard = self._hard_binary(soft, cfg)
            t = (cfg.bw_level - 8) / 92.0
            t = max(0.0, min(1.0, t))
            # 高黑白强度才接近纯二值；中等则混合，减轻断笔
            result = cv2.addWeighted(soft, 1.0 - t, hard, t, 0)

        if cfg.remove_black_blocks and cfg.shadow_remove > 0:
            result = self._bleach_edges(result, cfg.shadow_remove)

        return cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

    def _soft_scan(self, gray: np.ndarray, cfg: ScanSettings) -> np.ndarray:
        """清晰灰度扫描：去阴影 + 提白纸底 + 强化字迹，不做硬阈值。"""
        h, w = gray.shape[:2]
        min_side = min(h, w)

        # 大尺度背景估计，去掉桌面/褶皱阴影
        sigma = max(12.0, min_side * (0.035 + cfg.shadow_remove * 0.00025))
        bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
        bg = np.maximum(bg.astype(np.float32), 1.0)
        norm = cv2.divide(gray.astype(np.float32), bg, scale=255.0)

        # 轻微平滑纸纹（不伤字）
        if cfg.shadow_remove >= 60:
            norm_u8 = cv2.GaussianBlur(np.clip(norm, 0, 255).astype(np.uint8), (3, 3), 0).astype(np.float32)
        else:
            norm_u8 = np.clip(norm, 0, 255)

        # 百分位拉伸：抬高字迹对比，同时保住浅灰表格线
        lo_p = 1.0 + cfg.shadow_remove * 0.03
        hi_p = 99.2 - cfg.clarity * 0.015
        lo = float(np.percentile(norm_u8, lo_p))
        hi = float(np.percentile(norm_u8, hi_p))
        if hi - lo < 8:
            lo, hi = float(norm_u8.min()), float(max(norm_u8.max(), lo + 8))
        stretched = (norm_u8 - lo) * (255.0 / (hi - lo))
        stretched = np.clip(stretched, 0, 255)

        # 纸底漂白：接近白的像素拉成纯白，减少打印黑块感
        paper = 235.0 - cfg.shadow_remove * 0.35  # 45 -> ~219
        paper = max(195.0, min(245.0, paper))
        soft = stretched.copy()
        soft[soft >= paper] = 255.0

        # 清晰度：略压暗墨迹，表格线/字更醒目
        ink_gain = 1.0 + cfg.clarity / 140.0
        soft = 255.0 - (255.0 - soft) * ink_gain
        soft = np.clip(soft, 0, 255).astype(np.uint8)

        # 很轻的局部对比（默认弱，避免噪点）
        if cfg.clarity >= 35:
            clip = 0.8 + cfg.clarity / 120.0
            clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
            boosted = clahe.apply(soft)
            # 与原 soft 混合，防止 CLAHE 把纸纹抬起来
            alpha = 0.25 + cfg.clarity / 250.0
            soft = cv2.addWeighted(soft, 1.0 - alpha, boosted, alpha, 0)

        return soft

    def _hard_binary(self, soft_gray: np.ndarray, cfg: ScanSettings) -> np.ndarray:
        """硬二值（仅在用户提高「黑白强度」时使用）。"""
        blur = cv2.GaussianBlur(soft_gray, (3, 3), 0)
        # C 适中，避免把浅字洗掉
        c = int(round(8 + (100 - cfg.clarity) * 0.06))
        c = max(5, min(14, c))
        block = self._odd_block_size(min(soft_gray.shape[:2]), preferred=41)
        binary = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block,
            c,
        )
        # 只去掉极小噪点，不啃表格线
        if cfg.shadow_remove > 30:
            inv = cv2.bitwise_not(binary)
            num, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
            speck = max(2, int(soft_gray.size * 0.00001))
            for i in range(1, num):
                if stats[i, cv2.CC_STAT_AREA] <= speck:
                    binary[labels == i] = 255
        return binary

    def _bleach_edges(self, gray: np.ndarray, strength: int) -> np.ndarray:
        """清理贴边深色阴影条，避免打印黑边。"""
        result = gray.copy()
        h, w = result.shape[:2]
        s = max(0, min(100, int(strength))) / 100.0
        edge = max(2, int(min(h, w) * (0.006 + 0.012 * s)))

        # 边缘若整体偏暗，提亮到邻近纸色
        border = np.concatenate(
            [
                result[:edge, :].ravel(),
                result[-edge:, :].ravel(),
                result[:, :edge].ravel(),
                result[:, -edge:].ravel(),
            ]
        )
        if border.size and float(np.median(border)) < 180:
            # 用内部区域中位白度填充边缘暗带
            inner = result[edge : h - edge, edge : w - edge]
            paper = int(np.percentile(inner, 90)) if inner.size else 245
            paper = max(220, min(255, paper))
            result[:edge, :] = np.maximum(result[:edge, :], paper)
            result[-edge:, :] = np.maximum(result[-edge:, :], paper)
            result[:, :edge] = np.maximum(result[:, :edge], paper)
            result[:, -edge:] = np.maximum(result[:, -edge:], paper)

        # 四角洪水：把连通到角的深色背景抬白（灰度版）
        mask = np.zeros((h + 2, w + 2), np.uint8)
        flood = result.copy()
        for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if flood[seed[1], seed[0]] < 160:
                cv2.floodFill(flood, mask, seed, 255, loDiff=25 + int(20 * s), upDiff=25 + int(20 * s))
        dark = result < (140 + 40 * (1 - s))
        filled = flood >= 250
        result[dark & filled] = 255
        return result

    @staticmethod
    def _odd_block_size(min_side: int, preferred: int = 41) -> int:
        size = preferred
        if min_side < 400:
            size = 31
        elif min_side > 2000:
            size = 61
        if size % 2 == 0:
            size += 1
        return max(15, min(size, (min_side if min_side % 2 else min_side - 1)))

    @staticmethod
    def default_output_path(image_path: str) -> str:
        root, _ = os.path.splitext(image_path)
        return f"{root}_扫描件.pdf"

    @staticmethod
    def _imread(image_path: str) -> Optional[np.ndarray]:
        img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            return img
        try:
            with Image.open(image_path) as pil:
                return cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        except Exception:
            return None

    @staticmethod
    def _save_pdf(path: str, bgr: np.ndarray) -> None:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        pil = Image.fromarray(gray)
        pil.convert("RGB").save(path, "PDF", resolution=200.0)


def collect_images(folder: str | Path, *, recursive: bool = True) -> List[str]:
    """收集目录下图片路径。"""
    root = Path(folder)
    if not root.is_dir():
        return []
    paths: List[str] = []
    iterator = root.rglob("*") if recursive else root.glob("*")
    for p in iterator:
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            paths.append(str(p))
    paths.sort()
    return paths


def batch_convert_folder(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    settings: Optional[ScanSettings] = None,
    recursive: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[int, int, List[str], str]:
    """
    批量将文件夹内图片转为 PDF 扫描件。

    Returns:
        (success, failed_count, failed_paths, output_dir_str)
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    images = collect_images(source_dir, recursive=recursive)
    processor = ImageToScanProcessor()
    ok, fail_n, failed = processor.convert_many(
        images,
        str(out),
        settings=settings,
        progress_callback=progress_callback,
    )
    return ok, fail_n, failed, str(out)
