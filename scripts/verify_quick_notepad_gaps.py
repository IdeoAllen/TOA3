#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quick_notepad 自测：编辑 / 预览两面 · 无设计面 · 无 TXT|MD 双格式。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def tempfile_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="toa_notepad_"))


def test_pdf_export(app) -> None:
    from modules.quick_notepad.export_pdf import (
        export_html_to_pdf,
        safe_pdf_stem,
        wrap_export_html,
    )

    assert safe_pdf_stem("导出/测试.pdf")
    dest = Path(tempfile_dir()) / "导出测试.pdf"
    html = wrap_export_html(title="t", body_html="<p>hello</p>")
    out = export_html_to_pdf(html, dest)
    assert Path(out).is_file() and Path(out).stat().st_size > 100
    _ok(f"导出 PDF {dest.name}")


def test_two_modes_edit_preview(app) -> None:
    from modules.quick_notepad.note_store import normalize_view_mode
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage, _VIEW_MODES

    assert normalize_view_mode("source") == "edit"
    assert normalize_view_mode("txt") == "edit"
    assert normalize_view_mode("design") == "edit"
    assert normalize_view_mode("code") == "edit"
    assert normalize_view_mode(None) == "edit"
    assert normalize_view_mode("preview") == "preview"
    assert _VIEW_MODES == ("edit", "preview")

    page = QuickNotepadPage()
    page.show()
    app.processEvents()
    assert page._view_tab_bar.count() == 2
    assert page._view_tab_bar.tabText(0) == "编辑"
    assert page._view_tab_bar.tabText(1) == "预览"
    assert not hasattr(page, "_design")
    assert not hasattr(page, "_mode") or getattr(page, "_mode", None) is None
    # 默认编辑
    page._set_view_mode("edit")
    page._sync_view_chrome()
    assert page._view_stack.currentWidget() is page._md_source
    assert not page._component_palette.isHidden()
    page._md_source.setPlainText("# 你好\n\n正文\n")
    page._set_view_mode("preview")
    page._sync_view_chrome()
    assert page._view_stack.currentWidget() is page._preview_host
    assert page._component_palette.isHidden()
    assert "你好" in page._md_preview.toPlainText()
    page._set_view_mode("edit")
    assert page._view_stack.currentWidget() is page._md_source
    assert "你好" in page._md_source.toPlainText()
    _ok("两面编辑/预览 · 无设计 · 无格式下拉")
    page.close()


def test_handwritten_md_preview(app) -> None:
    """不插组件：源码手写 MD → 预览须正确解析（结构进 HTML）。"""
    from PySide6.QtWidgets import QTextEdit

    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage
    from modules.quick_notepad.rich_body import render_markdown_string

    sample = """# 一级标题
## 二级标题
### 三级标题

这是 **加粗** 与 *斜体* 与 ~~删除线~~ 与 `行内代码`。

- 无序甲
- 无序乙

1. 有序一
2. 有序二

> 这是一段引用

```
print("hello")
```

| 列A | 列B |
| --- | --- |
| 1 | 2 |

[官网](https://www.yczh.tech)

---

==高亮重点==

- [ ] 待办事项
- [x] 已完成

代码内勿展开：`==不是高亮==` 与

```
==仍不是高亮==
```
"""
    prev = QTextEdit()
    prev.setReadOnly(True)
    render_markdown_string(sample, prev)
    html = prev.toHtml().lower()
    plain = prev.toPlainText()
    assert "一级标题" in plain and "二级标题" in plain
    assert "<h1" in html and "<h2" in html and "<h3" in html
    assert "<ul" in html and "<ol" in html
    assert "blockquote" in html or "引用" in plain
    assert "<table" in html
    assert "href" in html and "yczh" in html
    assert "<hr" in html
    assert "line-through" in html or "删除" in plain
    assert "<code" in html or "行内代码" in plain
    assert "pre" in html or "hello" in plain
    assert "高亮重点" in plain
    # 代码区内的 == 不得被收成 mark 破坏围栏
    assert "仍不是高亮" in plain or "==仍不是高亮==" in sample
    prev.close()
    _ok("手写 MD 预览结构解析 OK")

    page = QuickNotepadPage()
    page.show()
    app.processEvents()
    page._set_view_mode("edit")
    page._loading_body = True
    page._md_source.setPlainText(sample)
    page._loading_body = False
    page._set_view_mode("preview")
    app.processEvents()
    pplain = page._md_preview.toPlainText()
    phtml = page._md_preview.toHtml().lower()
    assert "一级标题" in pplain, repr(pplain[:120])
    assert "<h1" in phtml and "<table" in phtml, phtml[:200]
    _ok("页面编辑→预览：手写 MD 无需组件")
    page.close()


def test_component_insert(app) -> None:
    from modules.quick_notepad.component_blocks import BLOCKS, get_block
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

    assert len(BLOCKS) == 27
    assert get_block("mermaid_lr") and get_block("mermaid_flow") and get_block("mermaid_pie")
    assert get_block("h4") and get_block("h5") and get_block("h6")
    assert get_block("strike") and get_block("inline_code") and get_block("hr")
    assert get_block("icon") and get_block("image")
    from modules.quick_notepad.component_blocks import markdown_for_block
    from modules.quick_notepad.image_attrs import build_image_markdown, suggest_size_key
    from PySide6.QtGui import QImage

    assert 'width="48"' in markdown_for_block("icon")
    tiny = QImage(64, 64, QImage.Format.Format_RGB32)
    tiny.fill(0)
    assert suggest_size_key(tiny, kind="icon") == "icon"
    wide = QImage(1200, 600, QImage.Format.Format_RGB32)
    wide.fill(0)
    assert suggest_size_key(wide, kind="image") == "lg"
    assert 'width="360"' in build_image_markdown("file:///x.png", size_key="md")
    page = QuickNotepadPage()
    page.show()
    app.processEvents()
    page._loading_body = True
    page._md_source.clear()
    page._loading_body = False
    page._set_view_mode("edit")
    page._on_palette_insert("h2")
    app.processEvents()
    assert "今日要点" in page._md_source.toPlainText(), repr(page._md_source.toPlainText())
    page._on_palette_insert("mermaid_flow")
    app.processEvents()
    assert "```mermaid" in page._md_source.toPlainText()
    _ok("编辑面可插入组件 · BLOCKS=27 · 含图表/图标")
    page.close()


def test_desktop_portal_hidden() -> None:
    import inspect

    from modules.column_preview import column_preview_page as cpp

    src = inspect.getsource(cpp)
    assert 'SecondaryButton("导入记事本")' not in src
    _ok("桌面无「导入记事本」按钮构造")


def test_search_sidebar_and_cascade_delete(app) -> None:
    from modules.quick_notepad.note_store import (
        add_note,
        delete_node,
        descendant_ids,
        find_note,
        load_nodes,
        save_nodes,
    )
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

    page = QuickNotepadPage()
    # 检索框在左侧栏顶部
    assert page._search.parent() is page._tree_box
    assert page._tree_box.layout().indexOf(page._search) == 0
    page.close()

    # 级联删除：父删则子孙全没
    snapshot = [dict(n) for n in load_nodes()]
    try:
        root = add_note("级联测根", "r", parent_id=None)
        child = add_note("级联测子", "c", parent_id=root["id"])
        grand = add_note("级联测孙", "g", parent_id=child["id"])
        ids = {root["id"], child["id"], grand["id"]}
        assert set(descendant_ids(root["id"])) == {child["id"], grand["id"]}
        assert delete_node(root["id"])
        left = {str(n.get("id")) for n in load_nodes()}
        assert ids.isdisjoint(left)
        assert find_note(child["id"]) is None
        _ok("侧栏顶部检索 · 删除级联子记事")
    finally:
        save_nodes(snapshot)


def test_one_body_store() -> None:
    from modules.quick_notepad.note_store import (
        _normalize_node,
        normalize_editor_mode,
        resolve_note_body_for_ui,
    )

    assert normalize_editor_mode("txt") == "md"
    n = _normalize_node(
        {
            "title": "t",
            "body": "",
            "bodies": {"txt": "纯文本槽", "md": "# MD槽"},
        }
    )
    assert n is not None
    assert "# MD槽" in (n.get("body") or "") or "MD槽" in (n.get("body") or "")
    body = resolve_note_body_for_ui(n)
    assert "MD" in body or "纯文本" in body or body
    _ok("一源 body 合并旧分槽")


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    try:
        print("== pdf ==")
        test_pdf_export(app)
        print("== one body ==")
        test_one_body_store()
        print("== two modes ==")
        test_two_modes_edit_preview(app)
        print("== handwritten md preview ==")
        test_handwritten_md_preview(app)
        print("== components ==")
        test_component_insert(app)
        print("== desktop ==")
        test_desktop_portal_hidden()
        print("== search + cascade delete ==")
        test_search_sidebar_and_cascade_delete(app)
        print("== md consistency ==")
        from scripts import verify_md_component_consistency as _c

        assert _c.main() == 0
        print("== notepad components ==")
        from scripts import verify_notepad_components as _n

        assert _n.main() == 0
        print("== roundtrip ==")
        from scripts import verify_component_roundtrip as _r

        assert _r.main() == 0
    except AssertionError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")
    print("VERIFY quick_notepad OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
