# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_EXPECTED = 27  # 22 常用（含图标）+ 5 图表


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def main() -> int:
    from PySide6.QtWidgets import QApplication, QTextEdit

    from modules.quick_notepad.component_blocks import BLOCKS, markdown_for_block
    from modules.quick_notepad.mermaid_preview import has_mermaid
    from modules.quick_notepad.rich_body import refresh_markdown_preview

    app = QApplication.instance() or QApplication(sys.argv)
    fails: list[str] = []
    md_blocks = [b for b in BLOCKS if (b.surface or "md") == "md"]
    if len(md_blocks) != _EXPECTED:
        fails.append(f"组件数量异常: {len(md_blocks)}（期望 {_EXPECTED}）")

    ids = [b.id for b in md_blocks]
    if len(ids) != len(set(ids)):
        fails.append("组件 id 重复")
    charts = [b for b in md_blocks if b.group == "图表"]
    if len(charts) < 5:
        fails.append(f"图表分组不足: {len(charts)}")

    for b in md_blocks:
        # 常用须有工具栏；图表可空（集中组件库）
        if b.group != "图表" and not (b.toolbar or "").strip():
            fails.append(f"{b.id}: 常用项缺 toolbar")
        if not (b.preview or "").strip() and b.id not in ("hr", "image", "time"):
            fails.append(f"{b.id}: 缺 preview 文案")
        md = markdown_for_block(b.id)
        if not (md or "").strip():
            fails.append(f"{b.id}: 插入为空")
            continue
        if b.id.startswith("mermaid_"):
            if "```mermaid" not in md and "mermaid" not in md.lower():
                fails.append(f"{b.id}: 非 mermaid 围栏")
            else:
                _ok(f"{b.id} · 图表 MD 围栏")
            continue
        if b.id == "icon":
            if "width=" not in md.lower() and "<img" not in md.lower():
                fails.append(f"{b.id}: 图标缺可控宽度")
            else:
                _ok(f"{b.id} · 图标可调大小")
            continue
        if b.id == "image":
            # 模板占位；真插入走对话框写 width
            _ok(f"{b.id} · 图片组件（插入时选大小）")
            continue
        tags = _HTML_TAG.findall(md)
        if tags:
            fails.append(f"{b.id}: 插入含 HTML {tags[:3]}")
            continue
        card = QTextEdit()
        card.setReadOnly(True)
        src = QTextEdit()
        src.setPlainText(md)
        refresh_markdown_preview(src, card)
        card_plain = card.toPlainText()
        prev = QTextEdit()
        prev.setReadOnly(True)
        refresh_markdown_preview(src, prev)
        prev_plain = prev.toPlainText()

        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", s or "")

        if _norm(card_plain) != _norm(prev_plain):
            fails.append(
                f"{b.id}: 卡片≠预览 card={card_plain[:40]!r} prev={prev_plain[:40]!r}"
            )
        else:
            _ok(f"{b.id} · 纯 MD · 卡片=预览")
        card.close()
        src.close()
        prev.close()

    sample_chart = markdown_for_block("mermaid_flow")
    assert has_mermaid(sample_chart)

    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        return 1
    print(f"VERIFY md component consistency OK · {len(md_blocks)} 项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
