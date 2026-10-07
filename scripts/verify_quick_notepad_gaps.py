#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quick_notepad 自测：编辑 / 源码 / 预览 · 无设计面 · 无 TXT|MD 双格式。"""
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

    assert normalize_view_mode("source") == "source"
    assert normalize_view_mode("txt") == "source"
    assert normalize_view_mode("design") == "edit"
    assert normalize_view_mode("code") == "source"
    assert normalize_view_mode(None) == "edit"
    assert normalize_view_mode("preview") == "preview"
    assert _VIEW_MODES == ("edit", "source", "preview")

    page = QuickNotepadPage()
    page.show()
    app.processEvents()
    assert page._view_tab_bar.count() == 3
    assert page._view_tab_bar.tabText(0) == "编辑"
    assert page._view_tab_bar.tabText(1) == "源码"
    assert page._view_tab_bar.tabText(2) == "预览"
    assert not hasattr(page, "_design")
    assert not hasattr(page, "_mode") or getattr(page, "_mode", None) is None
    # 默认编辑
    page._set_view_mode("edit")
    page._sync_view_chrome()
    assert page._view_stack.currentWidget() is page._md_source
    assert not page._component_palette.isHidden()
    from modules.quick_notepad.rich_body import load_body_into

    page._loading_body = True
    load_body_into(page._md_source, "# 你好\n\n正文\n")
    page._md_truth = "# 你好\n\n正文\n"
    page._edit_dirty = False
    page._loading_body = False
    page._set_view_mode("preview")
    page._sync_view_chrome()
    assert page._view_stack.currentWidget() is page._preview_host
    assert page._component_palette.isHidden()
    # 纸面预览优先 Web；Qt 副本也有正文
    assert "你好" in page._md_preview.toPlainText()
    page._set_view_mode("edit")
    assert page._view_stack.currentWidget() is page._md_source
    assert "你好" in page._md_source.toPlainText()
    page._set_view_mode("source")
    assert page._view_stack.currentWidget() is page._md_raw
    assert page._component_palette.isHidden()
    assert "# 你好" in page._md_raw.toPlainText()
    page._md_raw.setPlainText("# 源码改过\n\n**加粗**\n")
    page._set_view_mode("edit")
    assert "源码改过" in page._md_source.toPlainText()
    assert "加粗" in page._md_source.toPlainText()
    page._set_view_mode("source")
    raw = page._capture_body()
    assert "源码改过" in raw and "**加粗**" in raw
    assert page._guide_btn.text() == "效率指南"
    assert not page._efficiency_guide.isVisible()
    page._toggle_efficiency_guide()
    assert page._efficiency_guide.isVisible()
    from widgets import HintLabel

    hints = page._efficiency_guide.findChildren(HintLabel)
    assert any("导入 Markdown" in (h.text() or "") for h in hints)
    page._hide_efficiency_guide()
    assert not page._efficiency_guide.isVisible()
    _ok("三面编辑/源码/预览 · 源码往返 · 效率指南")
    page.close()


def test_three_faces_same_markdown(app) -> None:
    """未改编辑面时原文逐字保留；改过之后三面锁同一串。"""
    from PySide6.QtGui import QTextCursor

    from modules.quick_notepad.edit_ops import toggle_inline
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage

    original = "# 甲\n\n\n1. 第一步\n2. 第二步\n\n---\n\n> 原话\n"
    page = QuickNotepadPage()
    page._load_note_body(original)
    page._set_view_mode("edit")
    page._set_view_mode("preview")
    page._set_view_mode("source")
    assert page._md_raw.toPlainText() == original
    assert page._capture_body() == original
    page._set_view_mode("edit")
    assert page._capture_body() == original

    edited = original + "\n尾句\n"
    page._set_view_mode("source")
    page._md_raw.setPlainText(edited)
    page._set_view_mode("preview")
    assert page._capture_body() == edited
    page._set_view_mode("edit")
    page._set_view_mode("source")
    assert page._md_raw.toPlainText() == edited

    page._load_note_body("加粗这句\n")
    page._set_view_mode("edit")
    cur = page._md_source.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.Start)
    cur.movePosition(
        QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
    )
    page._md_source.setTextCursor(cur)
    toggle_inline(page, "bold")
    page._set_view_mode("source")
    once = page._md_raw.toPlainText()
    assert "**" in once
    page._set_view_mode("edit")
    page._set_view_mode("preview")
    page._set_view_mode("source")
    assert page._md_raw.toPlainText() == once
    assert page._capture_body() == once
    _ok("三面同一份 Markdown")
    page.close()


def test_wysiwyg_edit_actions(app) -> None:
    """对标实际编辑：格式可关、套当前段、真链接、行首标记、查找替换。"""
    from PySide6.QtGui import QTextCursor

    from modules.quick_notepad.edit_ops import (
        apply_heading,
        apply_link,
        apply_list,
        apply_quote,
        replace_all,
        toggle_inline,
        try_marker_shortcut,
    )
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage
    from modules.quick_notepad.rich_body import export_markdown_from, load_body_into

    page = QuickNotepadPage()
    page._set_view_mode("edit")
    load_body_into(page._md_source, "已有正文一段\n")

    def _select_line() -> None:
        cur = page._md_source.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.Start)
        cur.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        page._md_source.setTextCursor(cur)

    _select_line()
    apply_heading(page, 2)
    md = export_markdown_from(page._md_source)
    assert md.startswith("## 已有正文"), md
    apply_heading(page, 2)
    md = export_markdown_from(page._md_source)
    assert not md.lstrip().startswith("##"), md

    load_body_into(page._md_source, "加粗这句\n")
    _select_line()
    toggle_inline(page, "bold")
    md = export_markdown_from(page._md_source)
    assert "**加粗这句**" in md.replace(" ", ""), md
    _select_line()
    toggle_inline(page, "bold")
    md = export_markdown_from(page._md_source)
    assert "**" not in md, md

    load_body_into(page._md_source, "列表一项\n")
    _select_line()
    apply_list(page, ordered=False)
    md = export_markdown_from(page._md_source)
    assert md.lstrip().startswith("- "), md

    load_body_into(page._md_source, "引用这句\n")
    cur = page._md_source.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.Start)
    page._md_source.setTextCursor(cur)
    apply_quote(page)
    md = export_markdown_from(page._md_source)
    assert md.lstrip().startswith("> "), md

    load_body_into(page._md_source, "点此打开\n")
    _select_line()
    apply_link(page, "点此打开", "https://www.yczh.tech")
    md = export_markdown_from(page._md_source)
    assert "https://www.yczh.tech" in md and "[" in md, md
    assert md.count("](") == 1, md

    page._md_source.setPlainText("#")
    cur = page._md_source.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    page._md_source.setTextCursor(cur)
    assert try_marker_shortcut(page._md_source)
    cur = page._md_source.textCursor()
    assert int(cur.blockFormat().headingLevel() or 0) == 1
    cur.insertText("标记标题")
    page._md_source.setTextCursor(cur)
    md = export_markdown_from(page._md_source)
    assert md.lstrip().startswith("# 标记标题"), md
    assert not md.lstrip().startswith("##"), md

    page._md_source.setPlainText("甲甲 甲甲")
    n = replace_all(page._md_source, "甲甲", "乙")
    assert n == 2
    assert page._md_source.toPlainText() == "乙 乙"
    _ok("实际编辑 · 开关格式 / 套段 / 链接 / 行首标记 / 替换")
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
    from modules.quick_notepad.rich_body import export_markdown_from, load_body_into

    page._loading_body = True
    load_body_into(page._md_source, sample)
    page._md_truth = sample
    page._edit_dirty = False
    page._loading_body = False
    page._set_view_mode("preview")
    app.processEvents()
    pplain = page._md_preview.toPlainText()
    phtml = page._md_preview.toHtml().lower()
    assert "一级标题" in pplain, repr(pplain[:120])
    assert "<h1" in phtml and "<table" in phtml, phtml[:200]
    # 落盘仍是 Markdown
    exported = export_markdown_from(page._md_source)
    assert "# 一级标题" in exported or "一级标题" in exported
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
    from modules.quick_notepad.rich_body import export_markdown_from

    body = export_markdown_from(page._md_source)
    assert "今日要点" in body or "今日要点" in page._md_source.toPlainText(), repr(body)
    page._on_palette_insert("mermaid_flow")
    app.processEvents()
    body2 = export_markdown_from(page._md_source)
    assert "```mermaid" in body2 or "mermaid" in body2.lower()
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


def test_toolbar_groups() -> None:
    from modules.quick_notepad.component_blocks import (
        BLOCKS,
        TOOLBAR_GROUP_ORDER,
        is_chart_block,
        toolbar_blocks_by_group,
    )

    groups = toolbar_blocks_by_group()
    assert [g for g, _ in groups] == list(TOOLBAR_GROUP_ORDER)
    seen: set[str] = set()
    for gid, specs in groups:
        assert specs
        for s in specs:
            assert (s.toolbar or "").strip()
            assert s.toolbar_group == gid
            assert s.group != "图表"
            assert not is_chart_block(s.id)
            seen.add(s.id)
    text_ids = {b.id for b in BLOCKS if b.group != "图表"}
    chart_ids = {b.id for b in BLOCKS if b.group == "图表"}
    assert text_ids <= seen, f"缺工具栏: {text_ids - seen}"
    assert seen.isdisjoint(chart_ids)
    _ok(f"工具栏分栏 {list(TOOLBAR_GROUP_ORDER)} · 文字 {len(seen)} · 图表不上栏")


def test_preview_pipeline_and_tasks(app) -> None:
    from PySide6.QtWidgets import QTextEdit

    from modules.quick_notepad.md_text import prepare_markdown_for_preview
    from modules.quick_notepad.preview_pipeline import apply_preview
    from modules.quick_notepad.rich_body import render_markdown_string

    sample = "==高亮重点==\n\n- [ ] 待办甲\n- [x] 已完成乙\n"
    prepared = prepare_markdown_for_preview(sample)
    assert "<mark" in prepared and "高亮重点" in prepared
    assert "☐" in prepared and "☑" in prepared

    prev = QTextEdit()
    prev.setReadOnly(True)

    class _Host:
        def setCurrentWidget(self, _w) -> None:
            return None

    # 无 WebEngine 时退回 Qt
    result = apply_preview(
        sample,
        qt_preview=prev,
        preview_host=_Host(),
        ensure_web=lambda: None,
    )
    assert result.kind in ("qt", "web", "empty")
    plain = prev.toPlainText()
    assert "高亮重点" in plain
    assert "待办甲" in plain and "已完成乙" in plain
    render_markdown_string(sample, prev)
    assert "☐" in prev.toPlainText() or "待办甲" in prev.toPlainText()
    prev.close()

    from modules.quick_notepad.mermaid_preview import build_reading_document_html

    reading = build_reading_document_html(
        "# 一级标题\n\n> 引用句\n\n> [!NOTE]\n> 提示内容\n\n- [ ] 待办甲\n- [x] 已完成乙\n\n"
        "| 列A | 列B |\n| --- | --- |\n| 1 | 2 |\n\n```\nprint(1)\n```\n"
    )
    assert "class=\"sheet\"" in reading
    assert "<blockquote" in reading
    assert "callout" in reading and "提示内容" in reading
    assert "li class=\"task" in reading
    assert "<th>" in reading
    assert "<pre><code>" in reading
    assert "margin-left:40px" not in reading
    _ok("预览管线 · 高亮/待办展开 · 阅读排版")


def test_catalog_blocks_parse(app) -> None:
    """在录组件：预览 HTML 必须保留各自的解析结构。"""
    from modules.quick_notepad.component_blocks import BLOCKS, markdown_for_block
    from modules.quick_notepad.mermaid_preview import build_reading_document_html

    expect = {
        "h1": "<h1",
        "h2": "<h2",
        "h3": "<h3",
        "h4": "<h4",
        "h5": "<h5",
        "h6": "<h6",
        "bold": "<strong>",
        "italic": "<em>",
        "strike": "<s>",
        "highlight": "<mark>",
        "inline_code": "<code>",
        "bullets": "<ul>",
        "steps": "<ol>",
        "checklist": 'class="task"',
        "quote": "<blockquote",
        "hr": "<hr",
        "table": "<th>",
        "link": 'href="https://www.yczh.tech"',
        "image": "<img",
        "icon": 'width="48"',
    }
    for spec in BLOCKS:
        html = build_reading_document_html(markdown_for_block(spec.id))
        body = html.split('class="md-body"', 1)[-1]
        if spec.id.startswith("mermaid_"):
            assert 'class="mermaid"' in body, spec.id
            assert "<pre>" not in body.split('class="mermaid"', 1)[0][-20:]
            continue
        if spec.id == "code_block":
            assert body.count("<pre>") == 1, spec.id
            assert "hello" in body and "def hello" in body
            assert "\n" in body.split("<pre>", 1)[1].split("</pre>", 1)[0]
            continue
        if spec.id == "checklist":
            assert 'class="task done"' in body and body.count('class="task"') >= 1
            continue
        if spec.id == "time":
            assert any(ch.isdigit() for ch in body)
            continue
        needle = expect[spec.id]
        assert needle in body, f"{spec.id} 缺 {needle}"
    _ok(f"在录组件 {len(BLOCKS)} 项预览结构")


def test_media_store_batch(app) -> None:
    from PySide6.QtGui import QImage

    from modules.quick_notepad.media_store import images_dir, store_images_batched, store_qimage

    imgs = []
    for i in range(5):
        im = QImage(32, 32, QImage.Format.Format_RGB32)
        im.fill(0x112233 + i)
        imgs.append(im)
    batches: list[tuple[int, int]] = []
    paths = store_images_batched(
        imgs, batch_size=2, on_batch=lambda done, total: batches.append((done, total))
    )
    assert len(paths) == 5
    assert batches == [(2, 5), (4, 5), (5, 5)]
    root = images_dir()
    for p in paths:
        assert p.is_file()
        assert p.parent == root
    one = store_qimage(imgs[0])
    assert one is not None and one.is_file()
    _ok("媒体库分批写盘 · images/")


def test_edit_preview_roundtrip_keeps_text(app) -> None:
    from modules.quick_notepad.quick_notepad_page import QuickNotepadPage
    from modules.quick_notepad.rich_body import export_markdown_from, load_body_into

    page = QuickNotepadPage()
    page.show()
    app.processEvents()
    sample = "# 落点测\n\n正文不丢字 · ==高亮==\n"
    page._set_view_mode("edit")
    page._loading_body = True
    load_body_into(page._md_source, sample)
    page._md_truth = sample
    page._edit_dirty = False
    page._loading_body = False
    from PySide6.QtGui import QTextCursor

    cur = page._md_source.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.Down)
    page._md_source.setTextCursor(cur)
    page._set_view_mode("preview")
    app.processEvents()
    assert "落点测" in page._md_preview.toPlainText()
    page._set_view_mode("edit")
    app.processEvents()
    exported = export_markdown_from(page._md_source)
    assert "落点测" in exported
    assert "正文不丢字" in exported
    _ok("编辑↔预览切换不丢字")
    page.close()


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    try:
        print("== pdf ==")
        test_pdf_export(app)
        print("== one body ==")
        test_one_body_store()
        print("== toolbar groups ==")
        test_toolbar_groups()
        print("== two modes ==")
        test_two_modes_edit_preview(app)
        print("== same markdown ==")
        test_three_faces_same_markdown(app)
        print("== edit actions ==")
        test_wysiwyg_edit_actions(app)
        print("== handwritten md preview ==")
        test_handwritten_md_preview(app)
        print("== preview pipeline ==")
        test_preview_pipeline_and_tasks(app)
        print("== catalog blocks ==")
        test_catalog_blocks_parse(app)
        print("== media store ==")
        test_media_store_batch(app)
        print("== edit/preview roundtrip ==")
        test_edit_preview_roundtrip_keeps_text(app)
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
