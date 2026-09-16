#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clipboard_history 自测：搜索/来源过滤、隐私暂停入库+遮罩、送记事本载荷。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _install_tmp_store(tmp: Path):
    import modules.clipboard_history.history_store as store

    def _mod_dir(module_id: str, *, create: bool = False) -> Path:
        p = tmp / "module" / module_id
        if create:
            p.mkdir(parents=True, exist_ok=True)
        return p

    store.module_data_dir = _mod_dir  # type: ignore[assignment]
    return store


def test_search_and_source_filter(store) -> None:
    store.set_privacy(False)
    store.save_history([])
    assert store.push_text("培训排期表 v2", source="manual")
    assert store.push_text("截图说明文字", source="screenshot")
    assert store.push_text("OCR 识别结果", source="ocr")
    assert store.push_text("自动复制片段", source="auto")

    all_rows = store.load_history()
    assert len(all_rows) == 4, f"期望 4 条，得 {len(all_rows)}"
    hit = store.filter_history(all_rows, query="排期")
    assert len(hit) == 1 and "排期" in (hit[0].get("text") or "")
    _ok("全文搜索命中正文")

    by_cn = store.filter_history(all_rows, query="截图")
    assert len(by_cn) >= 1 and any(x.get("source") == "screenshot" for x in by_cn)
    _ok("搜索可匹配中文来源标签")

    only_shot = store.filter_history(all_rows, source="screenshot")
    assert len(only_shot) == 1 and only_shot[0].get("source") == "screenshot"
    _ok("来源过滤 screenshot")

    line = store.list_line(only_shot[0], privacy=False)
    assert "排期" not in line and "截图" in line
    _ok("列表行含来源标签")


def test_privacy_pause_and_mask(store) -> None:
    store.set_privacy(False)
    store.save_history([])
    seeded = store.push_text("秘密文案 SECRET-TOKEN", source="manual")
    assert seeded is not None
    assert "SECRET-TOKEN" in store.list_line(seeded, privacy=False)

    store.set_privacy(True)
    assert store.privacy_on() is True
    assert store.push_text("开会时复制不该入库", source="auto") is None
    assert store.push_text("截图旁路也不入库", source="screenshot") is None
    assert len(store.load_history()) == 1, "隐私开启后不得新增"
    _ok("隐私时段暂停一切 push_* 入库")

    masked = store.list_line(seeded, privacy=True)
    assert "SECRET-TOKEN" not in masked
    assert "隐私" in masked or "••••" in masked
    _ok("隐私时段列表遮罩正文")

    # 持久化
    assert store.load_prefs().get("privacy") is True
    store.set_privacy(False)
    assert store.privacy_on() is False
    again = store.push_text("恢复后可入库", source="manual")
    assert again is not None
    _ok("关闭隐私后恢复入库且 prefs 持久")


def test_notepad_handoff(store, app) -> None:
    from PySide6.QtGui import QColor, QImage, QPixmap

    store.set_privacy(False)
    store.save_history([])

    text_item = store.push_text("送记事本正文内容", source="manual")
    payload = store.notepad_handoff(text_item)
    assert payload and payload.get("body") == "送记事本正文内容"
    assert payload.get("image_path") is None
    _ok("文本项 notepad_handoff")

    # 空文本
    assert store.notepad_handoff({"kind": "text", "text": "  "}) is None
    _ok("空文本不可送记事")

    pix = QPixmap(64, 48)
    pix.fill(QColor("#0EA5E9"))
    img_item = store.push_image(pix, source="screenshot")
    assert img_item is not None
    img_payload = store.notepad_handoff(img_item)
    assert img_payload and img_payload.get("image_path")
    assert Path(str(img_payload["image_path"])).is_file()
    _ok("图片项 notepad_handoff 带落盘路径")

    # 模拟 stash（不导航）
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

    QuickNotepadPage.stash_incoming(
        str(payload.get("body") or ""),
        title=str(payload.get("title") or ""),
        image_path=None,
    )
    assert QuickNotepadPage._incoming is not None
    assert QuickNotepadPage._incoming[1] == "送记事本正文内容"
    QuickNotepadPage._incoming = None
    _ok("QuickNotepadPage.stash_incoming 可接载荷")

    # 隐私下仍可 handoff（已入库旧项；遮罩不挡送记事）
    store.set_privacy(True)
    assert store.notepad_handoff(text_item) is not None
    store.set_privacy(False)
    _ok("隐私遮罩不阻断送记事载荷")
    _ = app, QImage  # Qt app 已创建；QImage 保兼容


def test_watcher_privacy_bridge(store) -> None:
    from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher

    w = get_clipboard_watcher()
    store.set_privacy(False)
    w.set_privacy(True)
    assert store.privacy_on() is True
    assert w.privacy_on() is True
    w.set_privacy(False)
    assert store.privacy_on() is False
    _ok("watcher.set_privacy 与 store prefs 同步")


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="toa3_clip_verify_") as td:
        tmp = Path(td)
        store = _install_tmp_store(tmp)
        try:
            print("== search / source filter ==")
            test_search_and_source_filter(store)
            print("== privacy pause + mask ==")
            test_privacy_pause_and_mask(store)
            print("== notepad handoff ==")
            test_notepad_handoff(store, app)
            print("== watcher privacy bridge ==")
            test_watcher_privacy_bridge(store)
        except AssertionError as exc:
            return _fail(str(exc))
        except Exception as exc:
            return _fail(f"{type(exc).__name__}: {exc}")
    print("VERIFY clipboard_history OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
