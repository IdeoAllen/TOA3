# -*- coding: utf-8 -*-
"""截图翻译门禁：import / 结构 / 空态；无真 OCR Key 亦可跑。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def _check_no_direct_http(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    banned = ("requests.", "urllib.request", "httpx.", "aiohttp.")
    for token in banned:
        if token in text:
            fail(f"{path.name} 疑似直连 HTTP: {token}")
            return
    if "get_client(" not in text and path.name == "screenshot_translate.py":
        fail(f"{path.name} 未走 integrations get_client")
        return
    ok(f"{path.name} 无直连 HTTP 痕迹")


def _check_overlay_hook() -> None:
    overlay = ROOT / "services" / "screenshot_overlay.py"
    text = overlay.read_text(encoding="utf-8")
    if "launch_translate_from_pixmap" not in text:
        fail("screenshot_overlay 未挂 launch_translate_from_pixmap")
    else:
        ok("overlay 翻译按钮挂异步入口")
    if 'icon_key="translate"' not in text and "icon_key='translate'" not in text:
        fail("overlay 工具栏缺少 translate 图标按钮")
    else:
        ok("overlay 工具栏有 translate 按钮")
    # 主路径不应再同步 ocr_only 于 _on_translate
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ScreenshotOverlay":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_on_translate":
                    src = ast.get_source_segment(text, item) or ""
                    if "ocr_only(" in src:
                        fail("_on_translate 仍同步调用 ocr_only")
                    else:
                        ok("_on_translate 无同步 ocr_only")
                    return
    fail("未找到 ScreenshotOverlay._on_translate")


def _check_service_api() -> None:
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from services import screenshot_translate as st
    from services.screenshot_translate_dialog import (
        TranslateResultDialog,
        launch_translate_from_pixmap,
    )

    assert callable(st.ocr_only)
    assert callable(st.translate_text)
    assert callable(st.ocr_and_translate)
    assert st.OcrWorker is not None
    assert callable(launch_translate_from_pixmap)
    ok("service API 可 import")

    # 空态：空 pixmap
    try:
        st.ocr_only(QPixmap())
        fail("ocr_only(空图) 应抛错")
    except ValueError:
        ok("ocr_only(空图) 抛 ValueError")
    except Exception as exc:
        fail(f"ocr_only(空图) 异常类型不对: {type(exc).__name__}: {exc}")

    # 对照窗结构：空原文 → 翻译禁用
    dlg = TranslateResultDialog(None, source="", translated="", offer_translate=True)
    if dlg._btn_tr.isEnabled():
        fail("空原文时「翻译原文」应禁用")
    else:
        ok("空原文禁用翻译按钮")
    dlg.close()

    # 有原文 → 可翻译；占位译文不可当「真译文」复制态
    dlg2 = TranslateResultDialog(
        None,
        source="Hello world",
        translated=st.PLACEHOLDER_TRANSLATED,
        offer_translate=True,
    )
    if not dlg2._btn_tr.isEnabled():
        fail("有原文时应可点翻译")
    else:
        ok("有原文可点翻译")
    if dlg2._btn_copy_dst.isEnabled():
        fail("占位译文时「复制译文」应禁用")
    else:
        ok("占位译文禁用复制译文")
    dlg2.close()

    # ocr_pending 空态
    dlg3 = TranslateResultDialog(None, ocr_pending=True, offer_translate=True)
    if dlg3._btn_tr.isEnabled():
        fail("OCR 进行中不应启用翻译")
    else:
        ok("OCR pending 禁用翻译")
    if "正在识别" not in dlg3._src.toPlainText():
        fail("OCR pending 原文区应提示正在识别")
    else:
        ok("OCR pending 文案")
    dlg3.close()

    # 空 pixmap launch 不崩（只警告）
    launch_translate_from_pixmap(None, QPixmap())
    ok("launch 空图安全返回")

    _ = app  # keep ref


def main() -> int:
    svc = ROOT / "services" / "screenshot_translate.py"
    dlg = ROOT / "services" / "screenshot_translate_dialog.py"
    if not svc.is_file() or not dlg.is_file():
        fail("缺少 screenshot_translate 服务文件")
        return 1

    _check_no_direct_http(svc)
    _check_no_direct_http(dlg)
    _check_overlay_hook()
    try:
        _check_service_api()
    except Exception as exc:
        fail(f"API/空态测异常: {exc}")

    print("-" * 40)
    if FAILURES:
        print("VERIFY screenshot_translate FAILED:", "; ".join(FAILURES))
        return 1
    print("VERIFY screenshot_translate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
