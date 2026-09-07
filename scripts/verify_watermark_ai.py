#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watermark_ai / LaMa 接入冒烟（不强制本机已下权重）。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.integrations import get_client
    from services.integrations.watermark_ai_client import WatermarkAiClient

    client = get_client("watermark_ai")
    assert isinstance(client, WatermarkAiClient), type(client)
    assert client.enabled, "integrations.yml 应默认启用 watermark_ai"
    hint = client.status_hint()
    assert isinstance(hint, str) and hint.strip(), hint
    ready = client.health_check()
    print(f"  status_hint={hint!r} ready={ready}")

    # 合成小图 + 选区
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("SKIP: no opencv")
        print("VERIFY watermark_ai OK (client only)")
        return 0

    bgr = np.zeros((120, 160, 3), dtype=np.uint8)
    bgr[:] = (40, 80, 120)
    cv2.rectangle(bgr, (100, 90), (155, 115), (255, 255, 255), -1)
    tmp = Path(tempfile.gettempdir()) / "toa3_wm_ai_smoke.png"
    ok, buf = cv2.imencode(".png", bgr)
    assert ok
    buf.tofile(str(tmp))
    region = (100, 90, 55, 25)

    if not ready:
        try:
            client.remove_watermark(str(tmp), region=region)
            print("FAIL: expected IntegrationError when LaMa not ready")
            return 1
        except Exception as exc:
            name = type(exc).__name__
            if "IntegrationError" not in name and "Integration" not in name:
                # core.exceptions.IntegrationError
                from core.exceptions import IntegrationError

                assert isinstance(exc, IntegrationError), exc
            print(f"  not-ready raises OK: {exc}")
    else:
        out = Path(tempfile.gettempdir()) / "toa3_wm_ai_out.png"
        path = client.remove_watermark(str(tmp), region=region, output_path=str(out))
        assert Path(path).is_file(), path
        print(f"  lama ran OK → {path}")

    # 服务层：默认 prefer_ai=False → 必须轻量，不因本机已装 LaMa 就拖慢
    from modules.watermark_remover.watermark_remover_service import remove_watermark

    dest = Path(tempfile.gettempdir()) / "toa3_wm_svc_out.png"
    result = remove_watermark(
        str(tmp),
        str(dest),
        prefer_ai=False,
        region=region,
    )
    assert result.ok, result.message
    assert Path(result.output_path).is_file()
    assert "lama" not in (result.engine or "").lower(), result.engine
    print(f"  default light engine={result.engine} msg={result.message}")

    if ready:
        dest_ai = Path(tempfile.gettempdir()) / "toa3_wm_svc_ai.png"
        ai_result = remove_watermark(
            str(tmp),
            str(dest_ai),
            prefer_ai=True,
            region=region,
        )
        assert ai_result.ok, ai_result.message
        print(f"  opt-in AI engine={ai_result.engine}")

    # mask 构建
    m = WatermarkAiClient._build_mask(120, 160, region=region)
    assert m is not None and m.sum() > 0
    print("VERIFY watermark_ai OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
