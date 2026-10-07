# -*- coding: utf-8 -*-
"""视频首帧海报图（桌面预览等）。优先 OpenCV，其次本机 ffmpeg。"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_EDGE = 960


def extract_video_poster_png(path: Path, *, max_edge: int = _MAX_EDGE) -> bytes:
    """提取视频首帧为 PNG 字节；失败抛异常。"""
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    err: Exception | None = None
    try:
        return _poster_via_cv2(path, max_edge=max_edge)
    except Exception as exc:
        err = exc
        logger.debug("cv2 video poster failed: %s", exc)
    try:
        return _poster_via_ffmpeg(path, max_edge=max_edge)
    except Exception as exc:
        logger.debug("ffmpeg video poster failed: %s", exc)
        if err is not None:
            raise RuntimeError(f"无法提取视频首帧：{err}") from exc
        raise RuntimeError(f"无法提取视频首帧：{exc}") from exc


def _poster_via_cv2(path: Path, *, max_edge: int) -> bytes:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("需要 OpenCV：pip install opencv-python-headless") from exc

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        # Windows 中文路径偶发失败：复制到短临时名再试
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / f"v{path.suffix.lower() or '.mp4'}"
            shutil.copy2(path, tmp)
            cap.release()
            cap = cv2.VideoCapture(str(tmp))
            if not cap.isOpened():
                raise RuntimeError("OpenCV 无法打开视频")
            return _read_frame_png(cap, max_edge=max_edge)
    try:
        return _read_frame_png(cap, max_edge=max_edge)
    finally:
        cap.release()


def _read_frame_png(cap, *, max_edge: int) -> bytes:
    import cv2
    import numpy as np

    frame = None
    # 跳过开头若干黑帧/空帧
    for _ in range(12):
        ok, fr = cap.read()
        if not ok or fr is None:
            break
        if fr.size == 0:
            continue
        # 过暗则再读下一帧
        if float(np.mean(fr)) < 8.0:
            frame = fr
            continue
        frame = fr
        break
    if frame is None:
        # 再试中间位置
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total > 10:
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, total // 10))
                ok, fr = cap.read()
                if ok and fr is not None:
                    frame = fr
        except Exception:
            pass
    if frame is None:
        raise RuntimeError("无法读取视频帧")

    h, w = frame.shape[:2]
    edge = max(h, w)
    if edge > max_edge > 0:
        scale = max_edge / float(edge)
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".png", frame)
    if not ok:
        raise RuntimeError("编码海报图失败")
    return bytes(buf)


def _poster_via_ffmpeg(path: Path, *, max_edge: int) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "poster.png"
        scale = (
            f"scale='min({max_edge},iw)':'min({max_edge},ih)':force_original_aspect_ratio=decrease"
        )
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "0.5",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            scale,
            "-y",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=45, check=False)
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
            # 无 -ss 再试一次（部分文件 0.5s 无关键）
            cmd2 = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                scale,
                "-y",
                str(out),
            ]
            proc = subprocess.run(cmd2, capture_output=True, timeout=45, check=False)
            if proc.returncode != 0 or not out.is_file():
                err = (proc.stderr or b"").decode("utf-8", errors="ignore")[:200]
                raise RuntimeError(err or "ffmpeg 提取失败")
        return out.read_bytes()
