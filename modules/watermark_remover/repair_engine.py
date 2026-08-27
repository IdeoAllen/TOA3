# -*- coding: utf-8 -*-
"""去水印修复引擎：TOA3 默认轻量 inpaint；integrations 大模型可后续接入。"""
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
) -> Tuple[np.ndarray, str]:
    """执行修复；当前仅轻量路径，与 TOA2 repair_engine 接口一致。"""
    out = light_fn(bgr, mask)
    logger.info("去水印实际引擎: light")
    return out, "light"
