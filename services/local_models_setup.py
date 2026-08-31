# -*- coding: utf-8 -*-
"""本地算力模型 · 生图 + 去水印 统一安装。"""
from __future__ import annotations

from services.local_image_setup import ProgressFn, one_click_setup, status_summary as image_status_summary
from services.local_inpaint_runtime import download_weights, install_status as lama_status


def combined_status_summary() -> str:
    img = image_status_summary()
    lama = lama_status()
    lines = [f"【本机生图】{img}"]
    if lama.get("ready"):
        lines.append(f"【去水印 LaMa】已就绪 · 设备 {lama.get('device') or 'cpu'}")
    elif lama.get("missing"):
        lines.append(f"【去水印 LaMa】缺 {'、'.join(lama['missing'])}")
    else:
        lines.append(f"【去水印 LaMa】{lama.get('user_hint') or '待安装'}")
    return "\n".join(lines)


def install_all(
    *,
    bundle_id: str = "balanced",
    runtime_profile: str = "win_cuda12",
    progress: ProgressFn | None = None,
) -> tuple[bool, str]:
    """一键装齐：LaMa（小）+ 本机生图（大）。"""

    def _prog(msg: str, cur: int = 0, total: int = 0) -> None:
        if progress:
            progress(msg, cur, total)

    st_lama = lama_status()
    if not st_lama.get("ready"):
        _prog("正在下载去水印模型（LaMa）…", 0, 0)
        ok, msg = download_weights(progress=_prog)
        if not ok:
            return False, msg

    _prog("正在安装本机生图（模型较大，请耐心等待）…", 0, 0)
    ok, msg = one_click_setup(
        bundle_id,
        runtime_profile=runtime_profile,
        try_migrate_first=True,
        progress=_prog,
    )
    return ok, msg
