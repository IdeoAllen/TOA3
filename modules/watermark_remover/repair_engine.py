# -*- coding: utf-8 -*-
"""去水印修复引擎：默认轻量 inpaint；LaMa 仅显式请求时启用。"""
from __future__ import annotations

import logging
from typing import Callable, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def repair(
    bgr: np.ndarray,
    mask: np.ndarray,
    *,
    light_fn: Callable[[np.ndarray, np.ndarray], np.ndarray],
    prefer_heavy: bool = False,
) -> Tuple[np.ndarray, str]:
    """默认轻量修复（低配友好）；仅 prefer_heavy=True 且 LaMa 就绪时走强引擎。"""
    if prefer_heavy:
        try:
            from services.local_inpaint_runtime import install_status, inpaint as lama_inpaint

            if install_status().get("ready"):
                out = lama_inpaint(bgr, mask)
                logger.info("去水印实际引擎: lama")
                return out, "lama"
        except Exception as exc:
            logger.warning("LaMa 修复失败，回退轻量: %s", exc)

    out = light_fn(bgr, mask)
    logger.info("去水印实际引擎: light")
    return out, "light"
