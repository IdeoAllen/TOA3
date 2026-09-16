# -*- coding: utf-8 -*-
"""验真：MD 组件「编辑插入 + 预览渲染」；TXT/MD 互转。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _md_blocks():
    from modules.quick_notepad.component_blocks import BLOCKS

    return [b for b in BLOCKS if (b.surface or "md") == "md"]


def _verify_md_edit_and_preview(app) -> list[str]:
    from PySide6.QtWidgets import QPlainTextEdit, QTextEdit

    from modules.quick_notepad.component_blocks import (
        insert_markdown_snippet,
        markdown_for_block,
    )
    from modules.quick_notepad.rich_body import refresh_markdown_preview

    fails: list[str] = []
    blocks = _md_blocks()
    assert 10 <= len(blocks) <= 30, f"MD 组件数量异常: {len(blocks)}"

    for b in blocks:
        md = markdown_for_block(b.id)
        if not (md or "").strip():
            fails.append(f"{b.id}: markdown 为空")
            continue

        edit = QPlainTextEdit()
        ok_ins = insert_markdown_snippet(edit, md)
        if not ok_ins:
            fails.append(f"{b.id}: 编辑区未插入")
            edit.close()
            continue
        edit_text = edit.toPlainText()

        src = QTextEdit()
        src.setPlainText(edit_text)
        prev = QTextEdit()
        prev.setReadOnly(True)
        refresh_markdown_preview(src, prev)
        plain = prev.toPlainText()
        html = prev.toHtml()
        html_l = html.lower()
        edit.close()
        src.close()
        prev.close()

        bid = b.id
        if bid in ("h1", "h2", "h3"):
            expect = {"h1": "好想法", "h2": "今日", "h3": "分步"}
            if expect[bid] not in plain and expect[bid] not in html:
                fails.append(f"{bid}: 预览缺标题字")
                continue
        elif bid == "highlight":
            if "高亮" not in plain:
                fails.append(f"{bid}: 预览无高亮字")
                continue
        elif bid == "quote":
            if "引用" not in plain and "摘录" not in plain:
                fails.append(f"{bid}: 预览无引用")
                continue
        elif bid == "code_block":
            if "hello" not in plain.lower() and "hello" not in html_l:
                fails.append(f"{bid}: 预览无代码")
                continue
        elif bid == "table":
            if "模块" not in plain and "模块" not in html:
                fails.append(f"{bid}: 预览无表头")
                continue
        elif bid == "link":
            if "网址" not in plain and "yczh" not in plain.lower() and "yczh" not in html_l:
                fails.append(f"{bid}: 预览无链接")
                continue
        elif bid in ("tip", "callout"):
            if "贴士" not in plain and "重点" not in plain:
                fails.append(f"{bid}: 预览无提示字")
                continue
        _ok(f"{b.id} · 编辑可插 / 预览可读")

    print(f"\nMD 组件 {len(blocks)} 项；失败 {len(fails)}")
    return fails


def _verify_one_body_coerce() -> list[str]:
    from modules.quick_notepad.rich_body import coerce_to_markdown
    from modules.quick_notepad.note_store import _normalize_node, resolve_note_body_for_ui

    fails: list[str] = []
    md = "# 标题\n\n**加粗**正文\n"
    out = coerce_to_markdown(md)
    if "标题" not in out:
        fails.append("coerce md 丢标题")
    else:
        _ok("coerce Markdown 保持正文")

    legacy = "<p>页面<strong>主标题</strong></p>"
    to_md = coerce_to_markdown(legacy)
    if "主标题" not in to_md:
        fails.append("遗留 html→md 失败")
    else:
        _ok("遗留 html→md")

    n = _normalize_node({"title": "x", "bodies": {"md": md, "txt": "旧txt"}})
    body = resolve_note_body_for_ui(n or {})
    if "标题" not in body and "加粗" not in body:
        fails.append("一源合并失败")
    else:
        _ok("一源 body 优先 MD 槽")
    return fails


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    print("== MD 编辑 + 预览 ==")
    fails = _verify_md_edit_and_preview(app)
    print("== 一源合并 ==")
    fails.extend(_verify_one_body_coerce())
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        return 1
    print("VERIFY md edit/preview + one-body OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
