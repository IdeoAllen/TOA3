# -*- coding: utf-8 -*-
"""
去图片水印处理器

本地 OpenCV：角标/半透明文字检测 + 像素级蒙版 + 多级修复，无需大模型。
针对「豆包AI生成」等彩色角标与复杂底纹做了加强。
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("watermark_remover")

Box = Tuple[int, int, int, int]  # x, y, w, h
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


class WatermarkRemoverProcessor:
    """水印检测与修复。"""

    def imread(self, path: str) -> Optional[np.ndarray]:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            return img
        try:
            with Image.open(path) as pil:
                return cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        except Exception as exc:
            logger.error("读取失败 %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------ detect
    def detect_boxes(self, bgr: np.ndarray) -> List[Box]:
        """启发式识别常见角标/半透明水印，返回矩形框（图像坐标）。"""
        if bgr is None or bgr.size == 0:
            return []
        h, w = bgr.shape[:2]
        scored: List[Tuple[float, Box]] = []

        # 四角 ROI 加大：右下/左下优先（AI 角标、时间戳常见）
        rw, rh = max(80, int(w * 0.42)), max(72, int(h * 0.32))
        corners = [
            ((0, 0, rw, rh), 0.85),
            ((w - rw, 0, rw, rh), 1.0),
            ((0, h - rh, rw, rh), 1.15),
            ((w - rw, h - rh, rw, rh), 1.7),
        ]
        for (cx, cy, cw, ch), weight in corners:
            for box, score in self._detect_candidates(bgr, cx, cy, cw, ch, w, h):
                scored.append((score * weight, box))

        # 底部全宽条带（今日水印 / 字幕）
        band_h = max(48, int(h * 0.2))
        band_y = h - band_h
        for box, score in self._detect_candidates(bgr, 0, band_y, w, band_h, w, h, loose=True):
            scored.append((score * 1.1, box))

        # 顶部细条（偶发）
        top_h = max(36, int(h * 0.12))
        for box, score in self._detect_candidates(bgr, int(w * 0.08), 0, int(w * 0.84), top_h, w, h, loose=True):
            scored.append((score * 0.75, box))

        for box, score in self._detect_by_ocr(bgr):
            scored.append((score, box))

        # 专门扫四角浅色文字（豆包AI生成 / 通义 / Midjourney 等）
        for box, score in self._detect_light_corner_text(bgr):
            scored.append((score, box))
        for box, score in self._detect_ai_badge_corners(bgr):
            scored.append((score, box))

        if not scored:
            fallback = self._fallback_corner_box(bgr)
            return [fallback] if fallback else []

        scored.sort(key=lambda t: t[0], reverse=True)
        filtered: List[Tuple[float, Box]] = []
        for score, box in scored:
            x, y, bw, bh = box
            x2, y2 = min(w, x + bw), min(h, y + bh)
            if x2 <= x or y2 <= y:
                continue
            roi = bgr[y:y2, x:x2]
            pm = self._watermark_pixels_in_roi(roi, aggressive=True)
            pix = int(np.count_nonzero(pm)) if pm is not None else 0
            # 浅色角标对比弱时 pix 可能很少，不能轻易丢掉
            if pix < 12 and score < 0.7:
                continue
            box_area = max((x2 - x) * (y2 - y), 1)
            if pix / box_area < 0.003 and box_area > (w * h * 0.06) and score < 1.0:
                continue
            filtered.append((score + min(0.8, pix / 280.0), box))

        if not filtered:
            fallback = self._fallback_corner_box(bgr)
            return [fallback] if fallback else ([scored[0][1]] if scored else [])

        filtered.sort(key=lambda t: t[0], reverse=True)
        # 丢掉过大且不像角标的框（噪声连通域）
        img_area = float(w * h)
        compact: List[Tuple[float, Box]] = []
        for score, box in filtered:
            x, y, bw, bh = box
            area = float(bw * bh)
            aspect = max(bw, bh) / float(max(min(bw, bh), 1))
            # 超过画面 12% 且不是扁长条 → 丢弃
            if area > img_area * 0.12 and aspect < 2.2:
                continue
            if area > img_area * 0.2:
                continue
            # 非角标区的大框降权淘汰
            cx, cy = x + bw / 2.0, y + bh / 2.0
            in_corner = (cx < w * 0.38 or cx > w * 0.62) and (cy < h * 0.35 or cy > h * 0.65)
            in_bottom_band = cy > h * 0.78
            if area > img_area * 0.06 and not (in_corner or in_bottom_band):
                continue
            if not in_corner and not in_bottom_band and score < 1.0:
                continue
            compact.append((score, box))
        if not compact:
            compact = filtered[:1]

        strong = [b for s, b in compact if s >= 0.45]
        boxes = strong if strong else [b for s, b in compact if s > 0.12]
        if not boxes:
            boxes = [compact[0][1]]
        # 若已有明确右下角小框，去掉与之无关的大虚框
        br_boxes = [b for b in boxes if (b[0] + b[2] / 2) > w * 0.55 and (b[1] + b[3] / 2) > h * 0.55 and b[2] * b[3] < img_area * 0.08]
        if br_boxes:
            keep = []
            for b in boxes:
                area = b[2] * b[3]
                if area > img_area * 0.08 and b not in br_boxes:
                    continue
                keep.append(b)
            boxes = keep or br_boxes
        return self._nms_boxes(boxes, iou_thresh=0.32)[:4]

    def detect_mask(self, bgr: np.ndarray, boxes: Sequence[Box] | None = None) -> np.ndarray:
        """像素级水印蒙版：优先抠出文字/色块本身，减少大框糊底。"""
        h, w = bgr.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        use_boxes = list(boxes) if boxes else self.detect_boxes(bgr)
        if not use_boxes:
            return mask

        for x, y, bw, bh in use_boxes:
            x1, y1 = max(0, x), max(0, y)
            x2, y2 = min(w, x + bw), min(h, y + bh)
            if x2 <= x1 or y2 <= y1:
                continue
            roi = bgr[y1:y2, x1:x2]
            local = self._watermark_pixels_in_roi(roi, aggressive=True)
            if local is None or not np.any(local):
                local = self._box_fallback_content_mask(roi)
            if local is None or not np.any(local):
                local = self._light_text_mask(roi)
            if local is None or not np.any(local):
                # 仍失败：取框内中心偏紧区域，后续走邻域贴片而非整框糊抹
                pad_x, pad_y = max(2, int(bw * 0.08)), max(2, int(bh * 0.1))
                yy1, yy2 = y1 + pad_y, max(y1 + pad_y + 1, y2 - pad_y)
                xx1, xx2 = x1 + pad_x, max(x1 + pad_x + 1, x2 - pad_x)
                mask[yy1:yy2, xx1:xx2] = 255
            else:
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                local = cv2.dilate(local, k, iterations=2)
                mask[y1:y2, x1:x2] = cv2.bitwise_or(mask[y1:y2, x1:x2], local)
        return mask

    def _box_fallback_content_mask(self, roi_bgr: np.ndarray) -> Optional[np.ndarray]:
        """框内抠不出颜色时，用边缘+高频残差逼近文字笔画。"""
        if roi_bgr is None or roi_bgr.size == 0:
            return None
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (0, 0), 1.8)
        diff = cv2.absdiff(gray, blur)
        _, th = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.Canny(gray, 30, 100)
        adapt = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 5)
        light = self._light_text_mask(roi_bgr)
        combined = cv2.bitwise_or(th, edges)
        combined = cv2.bitwise_or(combined, adapt)
        if light is not None:
            combined = cv2.bitwise_or(combined, light)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k, iterations=1)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, k, iterations=2)
        ratio = float(np.count_nonzero(combined)) / float(combined.size)
        if ratio < 0.003 or ratio > 0.58:
            return None
        return combined

    def _light_text_mask(self, roi_bgr: np.ndarray) -> Optional[np.ndarray]:
        """抠浅色/半透明角标文字像素（豆包、通义等白字）。"""
        if roi_bgr is None or roi_bgr.size == 0:
            return None
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        _h, s, v = cv2.split(hsv)
        # 多尺度中值，适配不同字号
        masks = []
        for ksize, th in ((15, 12), (25, 14), (35, 16)):
            ksize = min(ksize | 1, max(3, min(gray.shape[:2]) | 1))
            if ksize < 3:
                continue
            med = cv2.medianBlur(gray, ksize)
            bright = ((gray.astype(np.int16) - med.astype(np.int16)) > th).astype(np.uint8) * 255
            dark = ((med.astype(np.int16) - gray.astype(np.int16)) > th).astype(np.uint8) * 255
            masks.append(cv2.bitwise_or(bright, dark))
        if not masks:
            return None
        mask = masks[0]
        for m in masks[1:]:
            mask = cv2.bitwise_or(mask, m)
        # 高亮低饱和（白/灰半透明字）
        pale = cv2.bitwise_and(cv2.inRange(v, 150, 255), cv2.inRange(s, 0, 90))
        local_mean = cv2.blur(gray.astype(np.float32), (21, 21))
        pale_diff = ((gray.astype(np.float32) - local_mean) > 10).astype(np.uint8) * 255
        mask = cv2.bitwise_or(mask, cv2.bitwise_and(pale, pale_diff))
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
        ratio = float(np.count_nonzero(mask)) / float(mask.size)
        if ratio < 0.002 or ratio > 0.45:
            return None
        return mask

    def _detect_light_corner_text(self, bgr: np.ndarray) -> List[Tuple[Box, float]]:
        """专扫四角浅色/白色角标文字（如「豆包AI生成」）。"""
        h, w = bgr.shape[:2]
        regions = [
            (w - max(90, int(w * 0.36)), h - max(56, int(h * 0.16)), max(90, int(w * 0.36)), max(56, int(h * 0.16)), 1.45),
            (0, h - max(56, int(h * 0.16)), max(90, int(w * 0.36)), max(56, int(h * 0.16)), 1.15),
            (w - max(90, int(w * 0.36)), 0, max(90, int(w * 0.36)), max(56, int(h * 0.14)), 1.05),
            (0, 0, max(90, int(w * 0.36)), max(56, int(h * 0.14)), 0.9),
        ]
        found: List[Tuple[Box, float]] = []
        for x, y, rw, rh, base_score in regions:
            x, y = max(0, x), max(0, y)
            rw, rh = min(rw, w - x), min(rh, h - y)
            if rw < 20 or rh < 16:
                continue
            roi = bgr[y : y + rh, x : x + rw]
            mask = self._light_text_mask(roi)
            if mask is None or np.count_nonzero(mask) < 30:
                # 二次：更宽松阈值
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                med = cv2.medianBlur(gray, 21)
                bright = ((gray.astype(np.int16) - med.astype(np.int16)) > 10).astype(np.uint8) * 255
                dark = ((med.astype(np.int16) - gray.astype(np.int16)) > 10).astype(np.uint8) * 255
                mask = cv2.bitwise_or(bright, dark)
                k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
            if mask is None or np.count_nonzero(mask) < 28:
                continue
            # 合并水平文字行：膨胀后取连通域
            k_line = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, rw // 40), 3))
            merged = cv2.dilate(mask, k_line, iterations=1)
            num, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
            area = float(rw * rh)
            local_found = False
            for i in range(1, num):
                bx, by, bw, bh, a = stats[i]
                if a < max(28, area * 0.0015) or a > area * 0.55:
                    continue
                if bw < 10 or bh < 6:
                    continue
                aspect = max(bw, bh) / float(max(min(bw, bh), 1))
                # 角标文字多为扁长条
                if aspect < 1.15 and a < area * 0.015:
                    continue
                pad = max(6, int(min(bw, bh) * 0.2))
                gx = max(0, x + bx - pad)
                gy = max(0, y + by - pad)
                gw = min(w - gx, bw + 2 * pad)
                gh = min(h - gy, bh + 2 * pad)
                score = base_score + (0.15 if aspect >= 2.0 else 0.0)
                found.append(((gx, gy, gw, gh), score))
                local_found = True
            if not local_found and np.count_nonzero(mask) > 60:
                ys, xs = np.where(mask > 0)
                bx, by = int(xs.min()), int(ys.min())
                bw, bh = int(xs.max() - bx + 1), int(ys.max() - by + 1)
                pad = 10
                gx = max(0, x + bx - pad)
                gy = max(0, y + by - pad)
                gw = min(w - gx, bw + 2 * pad)
                gh = min(h - gy, bh + 2 * pad)
                found.append(((gx, gy, gw, gh), base_score * 0.92))
        return found

    def _detect_ai_badge_corners(self, bgr: np.ndarray) -> List[Tuple[Box, float]]:
        """针对右下角「图标+短文案」角标做紧凑定位。"""
        h, w = bgr.shape[:2]
        # 多档右下角窗口，适配不同分辨率
        windows = [
            (0.28, 0.12),
            (0.22, 0.09),
            (0.18, 0.07),
        ]
        found: List[Tuple[Box, float]] = []
        for fw, fh in windows:
            rw, rh = max(64, int(w * fw)), max(28, int(h * fh))
            x, y = w - rw, h - rh
            roi = bgr[y:h, x:w]
            mask = self._light_text_mask(roi)
            if mask is None:
                pm = self._watermark_pixels_in_roi(roi, aggressive=True)
                mask = pm
            if mask is None or np.count_nonzero(mask) < 24:
                continue
            # 水平投影找文字带
            row_sum = np.count_nonzero(mask, axis=1)
            col_sum = np.count_nonzero(mask, axis=0)
            if row_sum.max() < 3 or col_sum.max() < 3:
                continue
            row_th = max(2, int(row_sum.max() * 0.18))
            col_th = max(2, int(col_sum.max() * 0.18))
            rows = np.where(row_sum >= row_th)[0]
            cols = np.where(col_sum >= col_th)[0]
            if len(rows) < 2 or len(cols) < 4:
                continue
            by0, by1 = int(rows.min()), int(rows.max())
            bx0, bx1 = int(cols.min()), int(cols.max())
            bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
            if bw < 18 or bh < 8:
                continue
            # 文字带应相对扁，且靠右下
            if bh > rh * 0.7 and bw < rw * 0.35:
                continue
            pad = max(6, int(min(bw, bh) * 0.22))
            gx = max(0, x + bx0 - pad)
            gy = max(0, y + by0 - pad)
            gw = min(w - gx, bw + 2 * pad)
            gh = min(h - gy, bh + 2 * pad)
            found.append(((gx, gy, gw, gh), 1.55))
            break  # 取最紧凑成功窗口即可
        return found
    def _detect_candidates(
        self,
        bgr: np.ndarray,
        x: int,
        y: int,
        rw: int,
        rh: int,
        full_w: int,
        full_h: int,
        *,
        loose: bool = False,
    ) -> List[Tuple[Box, float]]:
        x = max(0, min(x, full_w - 1))
        y = max(0, min(y, full_h - 1))
        rw = max(1, min(rw, full_w - x))
        rh = max(1, min(rh, full_h - y))
        roi = bgr[y : y + rh, x : x + rw]
        if roi.size == 0:
            return []

        pixel_mask = self._watermark_pixels_in_roi(roi, aggressive=True)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (0, 0), 2.5)
        diff = cv2.absdiff(gray, blur)
        _, th = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.Canny(gray, 50, 140)
        combined = cv2.bitwise_or(th, edges)
        if pixel_mask is not None:
            combined = cv2.bitwise_or(combined, pixel_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
        combined = cv2.dilate(combined, kernel, iterations=1)

        num, _, stats, _ = cv2.connectedComponentsWithStats(combined, connectivity=8)
        area = float(rw * rh)
        min_area = max(40, area * (0.001 if loose else 0.002))
        max_area = area * (0.45 if loose else 0.35)
        found: List[Tuple[Box, float]] = []

        for i in range(1, num):
            bx, by, bw, bh, a = stats[i]
            if a < min_area or a > max_area:
                continue
            if bw < 8 or bh < 6:
                continue
            # 拒绝接近整块 ROI 的巨大连通域
            if bw > rw * 0.85 and bh > rh * 0.55:
                continue
            aspect = max(bw, bh) / float(max(min(bw, bh), 1))
            if aspect > 24 and min(bw, bh) < 10:
                continue

            pad = max(6, int(min(bw, bh) * 0.12))
            gx = max(0, x + bx - pad)
            gy = max(0, y + by - pad)
            gw = min(full_w - gx, bw + 2 * pad)
            gh = min(full_h - gy, bh + 2 * pad)
            box = (int(gx), int(gy), int(gw), int(gh))

            color_hit = 0.0
            if pixel_mask is not None:
                sub = pixel_mask[by : by + bh, bx : bx + bw]
                color_hit = float(np.count_nonzero(sub)) / float(max(bw * bh, 1))
            text_like = 1.15 if 1.6 <= aspect <= 16 else 0.5
            br_bias = 1.0 + 0.45 * ((gx + gw / 2) / full_w) * ((gy + gh / 2) / full_h)
            score = (0.35 + 0.95 * color_hit) * text_like * br_bias
            if color_hit < 0.01:
                if a < area * (0.008 if loose else 0.012):
                    continue
                if aspect < 1.6 and not loose:
                    continue
                score *= 0.45
            found.append((box, float(score)))

        if not found and pixel_mask is not None and np.count_nonzero(pixel_mask) > 60:
            ys, xs = np.where(pixel_mask > 0)
            if len(xs):
                bx, by = int(xs.min()), int(ys.min())
                bw, bh = int(xs.max() - bx + 1), int(ys.max() - by + 1)
                pad = max(8, int(min(bw, bh) * 0.15))
                gx = max(0, x + bx - pad)
                gy = max(0, y + by - pad)
                gw = min(full_w - gx, bw + 2 * pad)
                gh = min(full_h - gy, bh + 2 * pad)
                found.append(((gx, gy, gw, gh), 1.2))
        return found

    def _watermark_pixels_in_roi(self, roi_bgr: np.ndarray, *, aggressive: bool = False) -> Optional[np.ndarray]:
        """在 ROI 内抠半透明/彩色/浅色水印像素。"""
        if roi_bgr is None or roi_bgr.size == 0:
            return None
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        _h, s, v = cv2.split(hsv)
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

        red1 = cv2.inRange(hsv, (0, 35, 55), (14, 255, 255))
        red2 = cv2.inRange(hsv, (160, 35, 55), (180, 255, 255))
        magenta = cv2.inRange(hsv, (140, 25, 55), (170, 255, 255))
        cyan = cv2.inRange(hsv, (85, 35, 65), (110, 255, 255))
        yellow = cv2.inRange(hsv, (18, 45, 75), (40, 255, 255))
        strong = cv2.bitwise_or(cv2.bitwise_or(red1, red2), magenta)
        strong = cv2.bitwise_or(strong, cv2.bitwise_or(cyan, yellow))

        med = cv2.medianBlur(gray, 21)
        bright_th = 12 if aggressive else 20
        dark_th = 12 if aggressive else 20
        bright = ((gray.astype(np.int16) - med.astype(np.int16)) > bright_th).astype(np.uint8) * 255
        dark = ((med.astype(np.int16) - gray.astype(np.int16)) > dark_th).astype(np.uint8) * 255
        low_sat = cv2.inRange(s, 0, 85 if aggressive else 55)
        mono = cv2.bitwise_and(cv2.bitwise_or(bright, dark), low_sat)

        med_bgr = cv2.medianBlur(roi_bgr, 21)
        resid = cv2.absdiff(roi_bgr, med_bgr)
        resid_g = cv2.cvtColor(resid, cv2.COLOR_BGR2GRAY)
        _, resid_th = cv2.threshold(
            resid_g, max(10 if aggressive else 16, int(np.median(resid_g) + 8)), 255, cv2.THRESH_BINARY
        )

        mask = cv2.bitwise_or(strong, cv2.bitwise_and(mono, resid_th))
        if aggressive:
            bright_only = cv2.bitwise_and(bright, cv2.inRange(v, 130, 255))
            mask = cv2.bitwise_or(mask, cv2.bitwise_and(bright_only, resid_th))
            # 半透明白字：即使残差弱也纳入偏亮像素
            soft_bright = cv2.bitwise_and(bright, cv2.inRange(s, 0, 100))
            mask = cv2.bitwise_or(mask, soft_bright)
            light = self._light_text_mask(roi_bgr)
            if light is not None:
                mask = cv2.bitwise_or(mask, light)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)

        ratio = float(np.count_nonzero(mask)) / float(mask.size)
        min_ratio = 0.00035 if aggressive else 0.0008
        if ratio < min_ratio:
            return None
        if ratio > 0.42:
            mask = cv2.morphologyEx(strong, cv2.MORPH_CLOSE, k, iterations=2)
            if float(np.count_nonzero(mask)) / float(mask.size) < min_ratio:
                mask = cv2.bitwise_and(mono, resid_th)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
                if float(np.count_nonzero(mask)) / float(mask.size) < min_ratio:
                    return None
        return mask

    def _fallback_corner_box(self, bgr: np.ndarray) -> Optional[Box]:
        h, w = bgr.shape[:2]
        # 先用 AI 角标专用检测
        badges = self._detect_ai_badge_corners(bgr)
        if badges:
            return badges[0][0]
        light = self._detect_light_corner_text(bgr)
        if light:
            # 优先右下角
            light.sort(key=lambda t: (t[0][0] + t[0][2] / 2) / w * (t[0][1] + t[0][3] / 2) / h, reverse=True)
            return light[0][0]
        rw, rh = max(72, int(w * 0.26)), max(36, int(h * 0.1))
        x, y = w - rw, h - rh
        roi = bgr[y:h, x:w]
        pm = self._watermark_pixels_in_roi(roi, aggressive=True)
        if pm is None or not np.any(pm):
            return (max(0, w - rw - 6), max(0, h - rh - 6), rw, rh)
        ys, xs = np.where(pm > 0)
        bx, by = int(xs.min()), int(ys.min())
        bw, bh = int(xs.max() - bx + 1), int(ys.max() - by + 1)
        pad = max(8, int(min(bw, bh) * 0.2))
        gx = max(0, x + bx - pad)
        gy = max(0, y + by - pad)
        gw = min(w - gx, bw + 2 * pad)
        gh = min(h - gy, bh + 2 * pad)
        return (gx, gy, gw, gh)

    def suggest_bottom_right_box(self, bgr: np.ndarray) -> Box:
        """快捷：右下角常见水印区域（即使用户未自动识别到也可一键框选）。"""
        h, w = bgr.shape[:2]
        fb = self._fallback_corner_box(bgr)
        if fb:
            return fb
        rw, rh = max(140, int(w * 0.24)), max(52, int(h * 0.085))
        return (max(0, w - rw - 8), max(0, h - rh - 8), rw, rh)
    def _detect_by_ocr(self, bgr: np.ndarray) -> List[Tuple[Box, float]]:
        try:
            import pytesseract
            # 包在但引擎不在时直接跳过，避免每次识别空耗/抛错
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                return []
        except Exception:
            return []
        h, w = bgr.shape[:2]
        # 只扫四角，加速
        rw, rh = max(80, int(w * 0.35)), max(60, int(h * 0.2))
        regions = [
            (w - rw, h - rh, rw, rh),
            (0, h - rh, rw, rh),
            (w - rw, 0, rw, rh),
            (0, 0, rw, rh),
        ]
        keywords = ("水印", "AI", "生成", "豆包", "通义", "文心", "剪映", "今日", "watermark", "generated", "doubao")
        found: List[Tuple[Box, float]] = []
        for x, y, cw, ch in regions:
            roi = bgr[y : y + ch, x : x + cw]
            try:
                rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                data = pytesseract.image_to_data(rgb, lang="chi_sim+eng", output_type=pytesseract.Output.DICT)
            except Exception:
                continue
            n = len(data.get("text") or [])
            for i in range(n):
                text = (data["text"][i] or "").strip()
                if not text:
                    continue
                conf = float(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1
                if conf < 35 and not any(k.lower() in text.lower() for k in keywords):
                    continue
                hit = any(k.lower() in text.lower() for k in keywords) or conf >= 55
                if not hit and len(text) < 2:
                    continue
                bx, by, bw, bh = int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i])
                if bw < 8 or bh < 8:
                    continue
                pad = 10
                gx = max(0, x + bx - pad)
                gy = max(0, y + by - pad)
                gw = min(w - gx, bw + 2 * pad)
                gh = min(h - gy, bh + 2 * pad)
                score = 1.4 if any(k.lower() in text.lower() for k in keywords) else 0.7
                found.append(((gx, gy, gw, gh), score))
        return found

    @staticmethod
    def _nms_boxes(boxes: Sequence[Box], iou_thresh: float = 0.35) -> List[Box]:
        if not boxes:
            return []
        arr = sorted(
            ((int(b[0]), int(b[1]), int(b[2]), int(b[3])) for b in boxes),
            key=lambda b: b[2] * b[3],
            reverse=True,
        )
        keep: List[Box] = []
        for box in arr:
            if all(WatermarkRemoverProcessor._iou(box, k) < iou_thresh for k in keep):
                keep.append(box)
        return keep

    @staticmethod
    def _iou(a: Box, b: Box) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter <= 0:
            return 0.0
        union = aw * ah + bw * bh - inter
        return inter / float(max(union, 1))

    @staticmethod
    def boxes_to_mask(shape_hw: Tuple[int, int], boxes: Sequence[Box]) -> np.ndarray:
        h, w = shape_hw
        mask = np.zeros((h, w), dtype=np.uint8)
        for x, y, bw, bh in boxes:
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(w, int(x + bw))
            y2 = min(h, int(y + bh))
            if x2 > x1 and y2 > y1:
                mask[y1:y2, x1:x2] = 255
        return mask

    @staticmethod
    def merge_mask(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> np.ndarray:
        if a is None and b is None:
            raise ValueError("蒙版为空")
        if a is None:
            return b.copy()
        if b is None:
            return a.copy()
        return cv2.bitwise_or(a, b)

    # ------------------------------------------------------------------ inpaint / texture fill
    @staticmethod
    def _adaptive_feather_px(mask: np.ndarray, *, min_px: float = 3.0, max_px: float = 12.0) -> float:
        """按水印区域大小估算羽化宽度，减轻修复区与背景的硬边。"""
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return min_px
        bw = int(xs.max() - xs.min() + 1)
        bh = int(ys.max() - ys.min() + 1)
        side = float(min(bw, bh))
        return float(np.clip(side * 0.14, min_px, max_px))

    @staticmethod
    def _smoothstep01(x: np.ndarray) -> np.ndarray:
        x = np.clip(x.astype(np.float32), 0.0, 1.0)
        return x * x * (3.0 - 2.0 * x)

    @staticmethod
    def _composite_strict(
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
        *,
        feather_px: float = 1.0,
    ) -> np.ndarray:
        """只改蒙版内像素；蒙版外 100% 保留原图。羽化在蒙版内侧用 smoothstep 过渡。"""
        m = mask
        if m.ndim == 3:
            m = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY)
        m = (m > 0).astype(np.uint8) * 255
        if not np.any(m):
            return original.copy()
        feather = float(feather_px)
        if feather <= 0:
            out = original.copy()
            out[m > 0] = repaired[m > 0]
            return out
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        alpha = np.clip(dist / float(max(feather, 1e-3)), 0.0, 1.0)
        alpha = WatermarkRemoverProcessor._smoothstep01(alpha)
        alpha = np.where(m > 0, alpha, 0.0).astype(np.float32)[..., None]
        return np.clip(
            original.astype(np.float32) * (1.0 - alpha) + repaired.astype(np.float32) * alpha,
            0,
            255,
        ).astype(np.uint8)

    def _polish_boundary(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
        *,
        feather_px: float | None = None,
    ) -> np.ndarray:
        """在修复区边缘带做轻量颜色/纹理过渡，专门压交界处痕迹。"""
        m = (mask > 0).astype(np.uint8) * 255
        if not np.any(m):
            return repaired.copy()
        feather = feather_px if feather_px is not None else self._adaptive_feather_px(m)
        base = self._composite_strict(original, repaired, m, feather_px=feather)

        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dil_k = max(3, int(round(feather * 0.55)) | 1)
        kd = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dil_k, dil_k))
        outer = cv2.dilate(m, kd, iterations=1)
        inner = cv2.erode(m, k, iterations=1)
        band = cv2.subtract(outer, inner)
        if np.count_nonzero(band) < 12:
            return base

        # 边缘带：向邻域色调对齐 + 轻微双边，避免一条「贴图边」
        ring = cv2.subtract(outer, m)
        if np.count_nonzero(ring) < 8:
            ring = band
        matched = self._lab_transfer_masked(original, base, outer, ring)
        soft = cv2.bilateralFilter(matched, 5, 48, 48)

        dist_in = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        # 内侧：完全用 matched；边缘带：向原图过渡
        dist_out = cv2.distanceTransform(255 - m, cv2.DIST_L2, 3)
        blend_w = np.clip(dist_out / float(max(feather * 0.85, 1.0)), 0.0, 1.0)
        blend_w = self._smoothstep01(blend_w)
        blend_w = np.where(band > 0, blend_w, 0.0).astype(np.float32)[..., None]

        inner_alpha = np.clip(dist_in / float(max(feather, 1.0)), 0.0, 1.0)
        inner_alpha = self._smoothstep01(inner_alpha)
        inner_alpha = np.where(m > 0, inner_alpha, 0.0).astype(np.float32)[..., None]

        out = base.astype(np.float32)
        out = out * (1.0 - blend_w) + (
            soft.astype(np.float32) * inner_alpha + original.astype(np.float32) * (1.0 - inner_alpha)
        ) * blend_w
        return np.clip(out, 0, 255).astype(np.uint8)

    def inpaint(
        self,
        bgr: np.ndarray,
        mask: np.ndarray,
        *,
        method: str = "telea",
        radius: int = 5,
    ) -> np.ndarray:
        if mask is None or not np.any(mask):
            return bgr.copy()
        m = mask
        if m.ndim == 3:
            m = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY)
        m = (m > 0).astype(np.uint8) * 255

        method_l = str(method).lower()
        if method_l in ("auto", "quality", "hq", "texture"):
            return self._texture_fill(bgr, m)
        flag = cv2.INPAINT_TELEA if method_l != "ns" else cv2.INPAINT_NS
        # 算法可略扩便于填边，写回时再严格裁回用户蒙版
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        m_work = cv2.dilate(m, k, iterations=1)
        repaired = cv2.inpaint(bgr, m_work, max(1, int(radius)), flag)
        feather = self._adaptive_feather_px(m, min_px=2.5, max_px=8.0)
        return self._composite_strict(bgr, repaired, m, feather_px=feather)

    def _texture_fill(self, bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """邻域纹理贴回；最终严格只覆盖用户蒙版，并柔化交界。"""
        user_m = (mask > 0).astype(np.uint8) * 255
        try:
            repaired = self._texture_fill_impl(bgr, user_m)
        except Exception as exc:
            logger.warning("纹理贴回失败，回退 NS inpaint: %s", exc)
            repaired = cv2.inpaint(bgr, user_m, 5, cv2.INPAINT_NS)
        feather = self._adaptive_feather_px(user_m)
        blended = self._composite_strict(bgr, repaired, user_m, feather_px=feather)
        return self._polish_boundary(bgr, blended, user_m, feather_px=feather)

    def _texture_fill_impl(self, bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        h, w = bgr.shape[:2]
        m = (mask > 0).astype(np.uint8) * 255
        out = bgr.copy()
        num, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, num):
            x, y, bw, bh, a = stats[i]
            if a < 8:
                continue
            # 给贴片搜索留足邻域（衣服纹理多在水印内侧）
            pad = max(24, int(max(bw, bh) * 0.85))
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(w, x + bw + pad), min(h, y + bh + pad)
            local = (labels[y1:y2, x1:x2] == i).astype(np.uint8) * 255
            if not np.any(local):
                continue
            filled = self._fill_region_with_neighbor(out, x1, y1, x2, y2, local)
            roi = out[y1:y2, x1:x2]
            roi[local > 0] = filled[local > 0]
            out[y1:y2, x1:x2] = roi

        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edge = cv2.subtract(m, cv2.erode(m, k, iterations=1))
        if np.count_nonzero(edge) > 16:
            edge_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            edge_band = cv2.subtract(cv2.dilate(edge, edge_k, iterations=1), cv2.erode(m, k, iterations=2))
            edge_fix = cv2.inpaint(out, edge_band, 3, cv2.INPAINT_NS)
            edge_feather = max(2.5, self._adaptive_feather_px(m, min_px=2.5, max_px=6.0) * 0.5)
            out = self._composite_strict(out, edge_fix, edge_band, feather_px=edge_feather)

        out = self._color_match_masked(bgr, out, m)
        return out

    def _fill_region_with_neighbor(
        self,
        bgr: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        local_mask: np.ndarray,
    ) -> np.ndarray:
        """
        轻量高质量填充：
        1) 用洞边界环做 exemplar 贴片匹配（像周围衣服）
        2) 匹配差时退回 NS inpaint（比 Telea 少糊疤）
        3) 可再叠一层贴片高频，减轻塑料感
        写回严格限于 local_mask。
        """
        h, w = bgr.shape[:2]
        bw, bh = x2 - x1, y2 - y1
        tgt = bgr[y1:y2, x1:x2]
        if bw < 2 or bh < 2:
            return tgt.copy()

        mask_area = int(np.count_nonzero(local_mask))
        if mask_area < 8:
            return tgt.copy()

        # 窄环：只看洞外紧邻像素，避免把水印颜色算进参考
        ring = self._neighbor_ring(local_mask, max(3, min(9, (min(bw, bh) // 6) | 1)))
        if np.count_nonzero(ring) < 16:
            return self._ns_fill_roi(tgt, local_mask)

        # 先 NS 打底（结构连续），后面用贴片补纹理
        base = self._ns_fill_roi(tgt, local_mask)

        best = self._find_best_patch_offset(bgr, x1, y1, x2, y2, local_mask, ring)
        if best is None:
            return base

        dx, dy, ring_mad = best
        src = bgr[y1 + dy : y2 + dy, x1 + dx : x2 + dx]
        if src.shape[:2] != tgt.shape[:2]:
            return base

        patched = tgt.copy()
        patched[local_mask > 0] = src[local_mask > 0]
        patched = self._lab_transfer_masked(tgt, patched, local_mask, ring)

        # 环匹配好 → 以贴片为主；一般 → NS 底 + 贴片纹理；差 → 只用 NS
        if ring_mad <= 18:
            mix = 0.92
        elif ring_mad <= 32:
            mix = 0.70
        elif ring_mad <= 48:
            mix = 0.45
        else:
            return base

        # 贴片高频：保留 NS 低频颜色过渡，叠贴片细节
        base_f = base.astype(np.float32)
        patch_f = patched.astype(np.float32)
        ksize = 5 if min(bw, bh) < 80 else 9
        base_blur = cv2.GaussianBlur(base_f, (ksize, ksize), 0)
        patch_blur = cv2.GaussianBlur(patch_f, (ksize, ksize), 0)
        detail = patch_f - patch_blur
        hybrid = base_blur + detail
        hybrid = mix * patch_f + (1.0 - mix) * hybrid
        hybrid = np.clip(hybrid, 0, 255)

        # 内侧羽化，避免硬边疤痕（加宽 + smoothstep）
        dist = cv2.distanceTransform(local_mask, cv2.DIST_L2, 3)
        feather = max(3.5, min(9.0, min(bw, bh) * 0.12))
        alpha = np.clip(dist / feather, 0.0, 1.0)
        alpha = self._smoothstep01(alpha)
        alpha = np.where(local_mask > 0, alpha, 0.0).astype(np.float32)[..., None]
        blended = tgt.astype(np.float32) * (1.0 - alpha) + hybrid * alpha

        # seamlessClone 再润一遍（失败则忽略）
        if 20 <= max(bw, bh) <= 360 and mask_area >= 40 and ring_mad <= 40:
            try:
                pad = 12
                canvas = np.pad(tgt, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
                src_pad = np.pad(src, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
                mask_pad = np.pad(local_mask, ((pad, pad), (pad, pad)), mode="constant")
                mask_pad[:3, :] = 0
                mask_pad[-3:, :] = 0
                mask_pad[:, :3] = 0
                mask_pad[:, -3:] = 0
                if np.count_nonzero(mask_pad) >= 24:
                    cc = (canvas.shape[1] // 2, canvas.shape[0] // 2)
                    cloned = cv2.seamlessClone(src_pad, canvas, mask_pad, cc, cv2.MIXED_CLONE)
                    cloned_roi = cloned[pad : pad + bh, pad : pad + bw].astype(np.float32)
                    cloned_roi = self._lab_transfer_masked(
                        tgt, np.clip(cloned_roi, 0, 255).astype(np.uint8), local_mask, ring
                    ).astype(np.float32)
                    blended = tgt.astype(np.float32) * (1.0 - alpha) + cloned_roi * alpha
            except Exception:
                pass

        out = tgt.copy()
        out[local_mask > 0] = np.clip(blended, 0, 255).astype(np.uint8)[local_mask > 0]
        return out

    @staticmethod
    def _neighbor_ring(local_mask: np.ndarray, ring_k: int) -> np.ndarray:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ring_k, ring_k))
        ring = cv2.subtract(cv2.dilate(local_mask, k, iterations=1), local_mask)
        if np.count_nonzero(ring) < 12:
            k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            ring = cv2.subtract(cv2.dilate(local_mask, k3, iterations=1), local_mask)
        return ring

    @staticmethod
    def _ns_fill_roi(tgt: np.ndarray, local_mask: np.ndarray) -> np.ndarray:
        r = 4 if min(tgt.shape[:2]) < 90 else 6
        filled = cv2.inpaint(tgt, local_mask, r, cv2.INPAINT_NS)
        out = tgt.copy()
        out[local_mask > 0] = filled[local_mask > 0]
        return out

    def _find_best_patch_offset(
        self,
        bgr: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        local_mask: np.ndarray,
        ring: np.ndarray,
    ) -> Optional[Tuple[int, int, float]]:
        """在邻域找边界环最像的平移贴片；优先向图像内侧（衣服区域）。"""
        h, w = bgr.shape[:2]
        bw, bh = x2 - x1, y2 - y1
        tgt = bgr[y1:y2, x1:x2]
        mask_area = max(int(np.count_nonzero(local_mask)), 1)
        full_mask = np.zeros((h, w), dtype=np.uint8)
        full_mask[y1:y2, x1:x2] = local_mask

        # 角标水印：优先朝画面中心搜（右下→往左上）
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        prefer_dx = 1.0 if cx > w * 0.55 else (-1.0 if cx < w * 0.45 else 0.0)
        prefer_dy = 1.0 if cy > h * 0.55 else (-1.0 if cy < h * 0.45 else 0.0)
        # prefer_* >0 表示区域偏右/下，应向负方向搜
        bias_x = -prefer_dx
        bias_y = -prefer_dy

        max_dist = float(max(bw, bh) * 2.2 + 28)
        span = int(min(max(bw, bh) * 2.0, 180))
        step = max(2, min(bw, bh) // 8)

        candidates: List[Tuple[int, int]] = []
        # 方向优先采样
        for frac in (0.15, 0.25, 0.4, 0.55, 0.75, 1.0, 1.25, 1.55, 1.9):
            dx = max(3, int(bw * frac))
            dy = max(3, int(bh * frac))
            directed = [
                (int(bias_x * dx), int(bias_y * dy)),
                (int(bias_x * dx), 0),
                (0, int(bias_y * dy)),
                (int(bias_x * dx), int(-bias_y * dy * 0.4)),
            ]
            candidates.extend(directed)
            candidates.extend([(-dx, 0), (0, -dy), (dx, 0), (0, dy), (-dx, -dy), (dx, -dy), (-dx, dy), (dx, dy)])

        for dy in range(-span, span + 1, step):
            for dx in range(-span, span + 1, step):
                if dx == 0 and dy == 0:
                    continue
                if (dx * dx + dy * dy) ** 0.5 > max_dist:
                    continue
                candidates.append((dx, dy))

        ring_idx = ring > 0
        if int(np.count_nonzero(ring_idx)) < 12:
            return None
        tgt_ring = tgt[ring_idx].astype(np.float32)

        best_dx = best_dy = 0
        best_mad = 1e9
        seen = set()
        for dx, dy in candidates:
            key = (int(dx), int(dy))
            if key in seen:
                continue
            seen.add(key)
            dist = float((dx * dx + dy * dy) ** 0.5)
            if dist < 3 or dist > max_dist:
                continue
            sx1, sy1, sx2, sy2 = x1 + dx, y1 + dy, x2 + dx, y2 + dy
            if sx1 < 0 or sy1 < 0 or sx2 > w or sy2 > h:
                continue
            overlap_ratio = float(np.count_nonzero(full_mask[sy1:sy2, sx1:sx2])) / float(mask_area)
            if overlap_ratio > 0.06:
                continue
            src = bgr[sy1:sy2, sx1:sx2]
            # 源贴片在洞位置上的像素不能大部分仍是洞
            src_inside = src[local_mask > 0]
            if src_inside.size < 8:
                continue
            src_ring = src[ring_idx].astype(np.float32)
            mad = float(np.mean(np.abs(src_ring - tgt_ring)))
            # 轻微偏好朝内侧、距离近
            toward = 0.0
            if bias_x != 0 and dx * bias_x > 0:
                toward -= 2.5
            if bias_y != 0 and dy * bias_y > 0:
                toward -= 2.5
            score = mad + dist * 0.08 + overlap_ratio * 40.0 + toward
            if score < best_mad:
                best_mad = score
                best_dx, best_dy = int(dx), int(dy)

        if best_mad > 70:
            return None
        # best_mad 里含了距离惩罚，回传近似纯 MAD
        src = bgr[y1 + best_dy : y2 + best_dy, x1 + best_dx : x2 + best_dx]
        pure_mad = float(np.mean(np.abs(src[ring_idx].astype(np.float32) - tgt_ring)))
        return best_dx, best_dy, pure_mad

    @staticmethod
    def _lab_transfer_masked(
        ref_bgr: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
        ring: np.ndarray,
    ) -> np.ndarray:
        """把修复区色调对齐到邻域环（中位数，抗水印残色干扰）。"""
        if not np.any(ring) or not np.any(mask):
            return repaired
        ref_lab = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        out_lab = cv2.cvtColor(repaired, cv2.COLOR_BGR2LAB).astype(np.float32)
        for c in range(3):
            neigh = ref_lab[:, :, c][ring > 0]
            inside = out_lab[:, :, c][mask > 0]
            if neigh.size < 12 or inside.size < 4:
                continue
            shift = float(np.median(neigh) - np.median(inside))
            ch = out_lab[:, :, c]
            ch[mask > 0] = np.clip(ch[mask > 0] + shift, 0, 255)
            out_lab[:, :, c] = ch
        return cv2.cvtColor(np.clip(out_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)

    @staticmethod
    def _color_match_masked(src: np.ndarray, repaired: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """用蒙版外一圈邻域校正修复区色偏（略加宽环带）。"""
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        dil = cv2.dilate(mask, k, iterations=1)
        ring = cv2.subtract(dil, mask)
        if not np.any(ring):
            return repaired
        return WatermarkRemoverProcessor._lab_transfer_masked(src, repaired, mask, ring)

    def remove_with_boxes(
        self,
        bgr: np.ndarray,
        boxes: Sequence[Box],
        brush_mask: Optional[np.ndarray] = None,
        *,
        method: str = "auto",
        radius: int = 5,
        use_pixel_mask: bool = False,
    ) -> np.ndarray:
        """
        去除水印。框选与涂抹由调用方保证互斥。
        已配置 LaMa 插件 → 大模型；否则 → 邻域贴片轻量修复。
        """
        try:
            has_boxes = bool(boxes)
            has_brush = brush_mask is not None and np.any(brush_mask)
            if has_boxes and has_brush:
                has_boxes = False
            if has_boxes:
                mask = self.boxes_to_mask(bgr.shape[:2], boxes)
            elif has_brush:
                mask = (brush_mask > 0).astype(np.uint8) * 255
            else:
                return bgr.copy()

            def _light(img, m):
                return self.inpaint(img, m, method="texture", radius=radius)

            from .repair_engine import repair

            out, engine = repair(bgr, mask, light_fn=_light)
            logger.info("去水印引擎: %s", engine)
            feather = self._adaptive_feather_px(mask)
            blended = self._composite_strict(bgr, out, mask, feather_px=feather)
            if engine == "light":
                return self._polish_boundary(bgr, blended, mask, feather_px=feather)
            return blended
        except Exception as exc:
            logger.warning("remove_with_boxes 失败，回退简单 inpaint: %s", exc)
            mask = self.boxes_to_mask(bgr.shape[:2], boxes) if boxes else np.zeros(bgr.shape[:2], dtype=np.uint8)
            if brush_mask is not None and np.any(brush_mask):
                mask = (brush_mask > 0).astype(np.uint8) * 255
            if not np.any(mask):
                return bgr.copy()
            repaired = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
            return self._composite_strict(bgr, repaired, mask, feather_px=1.0)

    @staticmethod
    def default_output_path(image_path: str) -> str:
        root, ext = os.path.splitext(image_path)
        ext = ext if ext.lower() in IMAGE_EXTENSIONS else ".jpg"
        return f"{root}_去水印{ext}"

    def save_image(self, path: str, bgr: np.ndarray) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        ext = os.path.splitext(path)[1].lower() or ".jpg"
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
        buf.tofile(path)
