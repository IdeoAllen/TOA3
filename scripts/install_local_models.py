# -*- coding: utf-8 -*-
"""非交互：安装本机生图 + LaMa（供 Agent / 运维脚本调用）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.local_models_setup import install_all
    from services.local_inpaint_runtime import install_status as lama_st
    from services.local_image_runtime import install_status as img_st
    from services.model_catalog import set_active_profile_id

    def _prog(msg: str, cur: int = 0, total: int = 0) -> None:
        if total > 0:
            pct = int(cur * 100 / total)
            print(f"[{pct:3d}%] {msg}", flush=True)
        else:
            print(msg, flush=True)

    ok, msg = install_all(progress=_prog)
    if img_st().get("ready"):
        try:
            set_active_profile_id("image_gen", "local_z_image_simple")
            print("已设默认生图：本机生图（推荐）", flush=True)
        except Exception as exc:
            print(f"设默认生图失败: {exc}", flush=True)
    print(f"生图: {img_st()}", flush=True)
    print(f"LaMa: {lama_st()}", flush=True)
    print(("OK: " if ok else "FAIL: ") + msg, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
