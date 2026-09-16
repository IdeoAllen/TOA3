#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MXAPI 图像配置契约：catalog 条目 + Key 解析（Harness 凭据可回落）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.model_catalog import list_profiles, load_model_catalog, resolve_image_gen_profile
    from services.model_ready_registry import evaluate_profile
    from services.integrations.image_gen_client import ImageGenClient

    load_model_catalog(force=True)
    need = {
        "mxapi_nano_banana_2": "nano-banana-2",
        "mxapi_gpt_image_2": "gpt-image-2",
        "mxapi_nano_banana_pro": "nano-banana-pro",
    }
    ids = {p["id"] for p in list_profiles("image_gen")}
    for pid, model in need.items():
        assert pid in ids, pid
        prof = resolve_image_gen_profile(pid)
        assert prof.get("vendor") == "MXAPI"
        assert "mxapi.org" in str(prof.get("api_base") or "")
        assert prof.get("model") == model
        assert ImageGenClient._is_mxapi_profile(prof)
        # 本机有 Harness Key 时应收口为 ready；无 Key 时至少条目存在
        _ = evaluate_profile("image_gen", pid, prof)

    client = ImageGenClient()
    key = client._mxapi_api_key(resolve_image_gen_profile("mxapi_nano_banana_2"))
    # 不强求本机必有 Key（CI/干净机），有则长度合理
    if key:
        assert len(key) >= 8

    print("VERIFY mxapi_image_catalog OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
