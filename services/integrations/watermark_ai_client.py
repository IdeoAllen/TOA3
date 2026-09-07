# -*- coding: utf-8 -*-
"""AI 去水印 / 图像修复：本机 LaMa（经 local_inpaint_runtime）。"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Sequence

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config

logger = logging.getLogger(__name__)

Region = tuple[int, int, int, int]


class WatermarkAiClient(IntegrationClient):
    name = "watermark_ai"

    def __init__(self) -> None:
        super().__init__(integration_config("watermark_ai"))

    def health_check(self) -> bool:
        if not self.enabled:
            return False
        try:
            from services.local_inpaint_runtime import install_status

            return bool(install_status().get("ready"))
        except Exception:
            logger.debug("watermark_ai health_check failed", exc_info=True)
            return False

    def status_hint(self) -> str:
        """给业务页状态条用的短文案。"""
        if not self.enabled:
            return "watermark_ai 未启用（integrations.yml）"
        try:
            from services.local_inpaint_runtime import install_status

            st = install_status()
            if st.get("ready"):
                return f"LaMa 可选 · {st.get('device') or 'cpu'}"
            miss = "、".join(st.get("missing") or []) or "未安装"
            return st.get("user_hint") or f"未装 LaMa（{miss}），本地轻量照常用"
        except Exception as exc:
            return f"LaMa 状态不可用：{exc}"

    def remove_watermark(self, image_path: str, mask: Any = None, **kwargs: Any) -> str:
        """用本机 LaMa 修复；返回输出文件路径。

        kwargs:
          - output_path: 目标路径（可选）
          - region / boxes / brush_mask: 选区（与业务页同源）
        """
        self.require_enabled()
        from services.local_inpaint_runtime import install_status, inpaint as lama_inpaint

        st = install_status()
        if not st.get("ready"):
            miss = "、".join(st.get("missing") or []) or "未知依赖"
            raise self.integration_error(
                f"LaMa 未就绪: {miss}",
                user_message=str(st.get("user_hint") or "请到系统设置 → 安装本机模型下载 LaMa"),
            )

        src = Path(str(image_path))
        if not src.is_file():
            raise self.integration_error(f"找不到图片: {src}")

        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise self.integration_error("需要 OpenCV（opencv-python）") from exc

        bgr = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise self.integration_error(f"无法读取图片: {src}")

        h, w = bgr.shape[:2]
        work_mask = self._build_mask(
            h,
            w,
            mask=mask,
            region=kwargs.get("region"),
            boxes=kwargs.get("boxes"),
            brush_mask=kwargs.get("brush_mask"),
        )
        if work_mask is None or not np.any(work_mask):
            raise self.integration_error(
                "未提供有效选区",
                user_message="请先框选或涂抹水印区域，再使用 AI 去水印。",
            )

        try:
            out = lama_inpaint(bgr, work_mask)
        except Exception as exc:
            logger.exception("LaMa inpaint failed")
            raise self.integration_error(
                str(exc),
                user_message=f"LaMa 修复失败：{exc}",
            ) from exc

        dest = kwargs.get("output_path")
        if dest:
            out_path = Path(str(dest))
        else:
            out_path = Path(tempfile.gettempdir()) / f"toa3_lama_{src.stem}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ext = out_path.suffix.lower() or ".png"
        if ext == ".jpeg":
            ext = ".jpg"
        params: list[int] = []
        if ext in (".jpg", ".jpeg"):
            params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        elif ext == ".png":
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]
        ok, buf = cv2.imencode(ext, out, params)
        if not ok:
            raise self.integration_error("编码输出失败")
        buf.tofile(str(out_path))
        logger.info("watermark_ai LaMa ok → %s device=%s", out_path, st.get("device"))
        return str(out_path)

    @staticmethod
    def _build_mask(
        h: int,
        w: int,
        *,
        mask: Any = None,
        region: Region | None = None,
        boxes: Sequence[Region] | None = None,
        brush_mask: Any = None,
    ):
        import numpy as np

        if brush_mask is not None:
            m = np.asarray(brush_mask)
            if m.ndim == 2 and m.shape[0] == h and m.shape[1] == w and np.any(m):
                return (m > 0).astype(np.uint8) * 255

        if mask is not None:
            m = np.asarray(mask)
            if m.ndim == 2 and m.shape[0] == h and m.shape[1] == w and np.any(m):
                return (m > 0).astype(np.uint8) * 255

        out = np.zeros((h, w), dtype=np.uint8)
        filled = False
        for box in list(boxes or []):
            try:
                x, y, bw, bh = [int(v) for v in box]
            except Exception:
                continue
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            bw = max(1, min(bw, w - x))
            bh = max(1, min(bh, h - y))
            out[y : y + bh, x : x + bw] = 255
            filled = True
        if region is not None and not filled:
            try:
                x, y, bw, bh = [int(v) for v in region]
            except Exception:
                return None
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            bw = max(1, min(bw, w - x))
            bh = max(1, min(bh, h - y))
            out[y : y + bh, x : x + bw] = 255
            filled = True
        return out if filled else None
