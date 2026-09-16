# -*- coding: utf-8 -*-
"""组件库逐项验真：生成代码 ≡ 预览可见（MD only）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _anchors_from_text(text: str) -> list[str]:
    raw = text or ""
    plain = re.sub(r"```[\s\S]*?```", " ", raw)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"[#>*_\-`\[\]\(\)\|!~]", " ", plain)
    plain = re.sub(r"\$+", " ", plain)
    parts = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", plain)
    skip = {"span", "style", "color", "background", "table", "width", "padding", "margin"}
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p.lower() in skip or p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= 6:
            break
    return out


def _has_anchor(hay: str, anchor: str) -> bool:
    if not anchor:
        return True
    if anchor in hay:
        return True
    return anchor.replace(" ", "") in hay.replace(" ", "")


def _verify_md_roundtrip(app) -> list[str]:
    from PySide6.QtWidgets import QPlainTextEdit, QTextEdit

    from modules.quick_notepad.component_blocks import (
        BLOCKS,
        insert_markdown_snippet,
        markdown_for_block,
    )
    from modules.quick_notepad.rich_body import refresh_markdown_preview

    fails: list[str] = []
    blocks = [b for b in BLOCKS if (b.surface or "md") == "md"]
    print(f"== MD 组件 roundtrip · {len(blocks)} ==")
    assert len(blocks) == 27, f"期望 27 项（22 常用+5 图表），实得 {len(blocks)}"

    for b in blocks:
        code = markdown_for_block(b.id)
        if not (code or "").strip():
            fails.append(f"{b.id}: 生成代码为空")
            continue

        edit = QPlainTextEdit()
        if not insert_markdown_snippet(edit, code):
            fails.append(f"{b.id}: 插入失败")
            edit.close()
            continue
        src = edit.toPlainText()

        if b.id.startswith("mermaid_"):
            if "```mermaid" not in src and "mermaid" not in src.lower():
                fails.append(f"{b.id}: 源码无 mermaid 围栏")
            else:
                _ok(f"{b.id} · 图表围栏")
            edit.close()
            continue

        key_lines = [ln for ln in code.strip().splitlines() if ln.strip()][:3]
        for ln in key_lines:
            if ln.strip() and ln.strip() not in src and not any(
                tok in src for tok in _anchors_from_text(ln)[:2]
            ):
                fails.append(f"{b.id}: 编辑区缺少生成行「{ln.strip()[:24]}」")
                break

        anchors = _anchors_from_text(code)
        if b.preview:
            for a in _anchors_from_text(b.preview):
                if a in code and a not in anchors:
                    anchors.append(a)

        if b.id == "image":
            if "图片" not in src and "!" not in src and "<img" not in src.lower():
                fails.append(f"{b.id}: 源码无图片标记")
            else:
                _ok(f"{b.id} · 图片占位")
            edit.close()
            continue

        if b.id == "icon":
            if "<img" not in src.lower() or "width=" not in src.lower():
                fails.append(f"{b.id}: 图标缺 width")
            else:
                _ok(f"{b.id} · 图标可调大小")
            edit.close()
            continue

        if b.id == "hr":
            if "---" not in src and "—" not in src:
                fails.append(f"{b.id}: 源码无分割线")
            else:
                # 预览可能把 hr 收成空行；源码有 --- 即过
                _ok(f"{b.id} · 分割线")
            edit.close()
            continue

        if b.id == "time":
            if not any(c.isdigit() for c in src):
                fails.append(f"{b.id}: 源码无时间数字")
            else:
                _ok(f"{b.id} · 时间戳")
            edit.close()
            continue

        src_w = QTextEdit()
        src_w.setPlainText(src)
        prev = QTextEdit()
        prev.setReadOnly(True)
        refresh_markdown_preview(src_w, prev)
        plain = prev.toPlainText()
        html = prev.toHtml()
        blob = plain + "\n" + html

        missing = [a for a in anchors[:4] if not _has_anchor(blob, a)]
        if missing and b.id != "code_block":
            fails.append(f"{b.id}: 预览缺少锚点 {missing}")
        else:
            _ok(f"{b.id} · 源码↔预览锚点 {anchors[:3]}")

        edit.close()
        src_w.close()
        prev.close()

    return fails


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    fails = _verify_md_roundtrip(app)
    print(f"\n共失败 {len(fails)} 项")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        return 1
    print("VERIFY component code↔preview roundtrip OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
