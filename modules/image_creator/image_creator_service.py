# -*- coding: utf-8 -*-
"""空白 / 纯色 / 噪点图创建服务。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")


def ensure_pillow() -> Tuple[bool, str]:
    try:
        import PIL  # noqa: F401

        return True, ""
    except ImportError:
        return False, "未安装 Pillow，请执行: pip install Pillow"


def parse_hex_color(text: str) -> Tuple[int, int, int]:
    m = _HEX.match((text or "").strip())
    if not m:
        raise ValueError(f"颜色须为 #RRGGBB，收到：{text!r}")
    h = m.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def create_image(
    width: int,
    height: int,
    *,
    fill: str = "#FFFFFF",
    mode: str = "solid",
    output_dir: str | Path,
    basename: Optional[str] = None,
) -> str:
    """创建 PNG 并返回路径。mode: solid | noise。"""
    ok, msg = ensure_pillow()
    if not ok:
        raise RuntimeError(msg)

    from PIL import Image
    import random

    w = max(1, min(int(width), 20000))
    h = max(1, min(int(height), 20000))
    rgb = parse_hex_color(fill)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = basename or f"blank_{w}x{h}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    if not name.lower().endswith(".png"):
        name += ".png"
    dest = out_dir / name

    if mode == "noise":
        # 以 fill 为基色，叠加轻噪点
        pixels = []
        for _ in range(w * h):
            n = random.randint(-40, 40)
            pixels.append(tuple(max(0, min(255, c + n)) for c in rgb))
        img = Image.new("RGB", (w, h))
        img.putdata(pixels)
    else:
        img = Image.new("RGB", (w, h), rgb)

    img.save(str(dest), "PNG")
    logger.info("created image %s", dest)
    return str(dest)
