#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""media_studio 自测：页内 QMediaPlayer 预览、首尾帧参考槽、队列规格。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def test_imports_and_player(app) -> None:
    from modules.media_studio.media_studio_page import _PreviewCanvas, _VIDEO_EXTS

    assert ".mp4" in _VIDEO_EXTS
    canvas = _PreviewCanvas("empty")
    canvas.resize(480, 360)
    canvas.show()
    app.processEvents()
    assert canvas.has_embedded_player(), "本机应具备 QMediaPlayer + QVideoWidget"
    _ok("页内预览画布已挂载 QMediaPlayer")

    playing = {"v": False}
    failed = {"msg": ""}
    canvas.playback_changed.connect(lambda v: playing.__setitem__("v", bool(v)))
    canvas.playback_failed.connect(lambda m: failed.__setitem__("msg", str(m)))

    missing = ROOT / "output" / "media_studio" / "__verify_missing__.mp4"
    canvas.set_video_path(missing)
    app.processEvents()
    # 缺失文件应保留路径，便于系统打开回退；错误信号可能异步
    assert canvas.video_path() == missing.resolve()
    _ok("set_video_path 记录路径（含缺失文件）")

    canvas.set_placeholder("reset")
    app.processEvents()
    assert canvas.video_path() is None
    assert not canvas.is_video_mode()
    _ok("占位态会清空视频路径并停播")


def _wait_ui(app, page, timeout_ms: int = 5000) -> None:
    page.request_deferred_ui()
    waited = 0
    while not getattr(page, "_ui_ready", False) and waited < timeout_ms:
        app.processEvents()
        from PySide6.QtCore import QThread

        QThread.msleep(20)
        waited += 20
    assert page._ui_ready, "MediaStudioPage UI 未在时限内就绪"


def test_page_video_ref_slots(app) -> None:
    from modules.media_studio.media_studio_page import MediaStudioPage, _KIND_VIDEO

    page = MediaStudioPage()
    page.resize(1200, 800)
    page.show()
    app.processEvents()
    _wait_ui(app, page)
    assert hasattr(page, "_preview")
    assert page._preview.has_embedded_player()
    _ok("MediaStudioPage 预览可内嵌播放")

    assert hasattr(page, "_btn_sys_play")
    assert page._btn_sys_play.text() == "系统打开"
    _ok("提供「系统打开」回退按钮")

    page._kind = _KIND_VIDEO
    page._ref_paths = []
    page._apply_kind_ui()
    assert page._btn_ref.text() == "添加首帧"
    page._ref_paths = [Path("a.png")]
    page._apply_kind_ui()
    assert page._btn_ref.text() == "添加尾帧"
    page._ref_paths = [Path("a.png"), Path("b.png")]
    page._apply_kind_ui()
    assert page._btn_ref.text() == "首尾帧已满"
    assert not page._btn_ref.isEnabled()
    _ok("视频参考槽：首帧 → 尾帧 → 已满")
    page.close()
    page.deleteLater()
    app.processEvents()


def test_queue_spec_video_refs() -> None:
    from modules.media_studio.gen_queue import MediaGenSpec

    spec = MediaGenSpec(
        kind="video",
        prompt="demo",
        profile_id="x",
        image_paths=["a.png", "b.png"],
        width=1280,
        height=720,
        image_size="",
        ratio="16:9",
        resolution="720p",
        duration=5,
    )
    assert len(spec.image_paths) == 2
    _ok("队列规格可携带双图（首尾帧）")


def test_volcengine_last_frame_payload() -> None:
    """不联网：检查火山路径会为第二张图打 last_frame。"""
    import inspect

    from services.integrations.video_gen_client import VideoGenClient

    src = inspect.getsource(VideoGenClient._generate_volcengine)
    assert 'role": "first_frame"' in src or "role': 'first_frame'" in src or 'role": "first_frame"' in src
    assert "last_frame" in src
    _ok("Volcengine 生成路径含 last_frame 接线")


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    print("verify_media_studio")
    try:
        test_imports_and_player(app)
        test_page_video_ref_slots(app)
        test_queue_spec_video_refs()
        test_volcengine_last_frame_payload()
    except AssertionError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
