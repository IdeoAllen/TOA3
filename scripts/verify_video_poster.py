# -*- coding: utf-8 -*-
"""视频首帧 + 体积格式。"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from modules.column_preview.column_preview_page import _format_byte_size
    from services.video_preview import extract_video_poster_png

    assert _format_byte_size(512) == "512 B"
    assert _format_byte_size(2048).endswith("KB")
    # 截图里的约 765377.9 KB ≈ 747 MB
    assert _format_byte_size(765_377_900).endswith("MB")
    assert "MB" in _format_byte_size(747 * 1024 * 1024)
    assert _format_byte_size(2 * 1024 * 1024 * 1024).endswith("GB")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("verify_video_poster: size OK · skip frame (no ffmpeg)")
        return 0

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "tiny.mp4"
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:s=320x240:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
        if proc.returncode != 0 or not out.is_file():
            print("verify_video_poster: size OK · skip frame (ffmpeg encode fail)")
            return 0
        png = extract_video_poster_png(out)
        assert isinstance(png, (bytes, bytearray)) and len(png) > 100
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    print("verify_video_poster: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
