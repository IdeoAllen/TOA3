# -*- coding: utf-8 -*-
"""Office 结构化预览：Word HTML / Excel 表 / PPT 卡片。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_samples(tmp: Path) -> tuple[Path, Path, Path]:
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation

    docx_path = tmp / "sample.docx"
    doc = Document()
    doc.add_heading("桌面预览样例", level=1)
    doc.add_paragraph("这是一段正文，含 ")
    p = doc.add_paragraph()
    run = p.add_run("加粗")
    run.bold = True
    p.add_run(" 与普通文字。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A1"
    table.cell(0, 1).text = "B1"
    table.cell(1, 0).text = "A2"
    table.cell(1, 1).text = "B2"
    doc.save(docx_path)

    xlsx_path = tmp / "sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "销售"
    ws.append(["品名", "数量", "单价"])
    ws.append(["苹果", 3, 2.5])
    ws.append(["梨", 5, 3.0])
    ws2 = wb.create_sheet("库存")
    ws2.append(["SKU", "库存"])
    ws2.append(["A01", 10])
    wb.save(xlsx_path)

    pptx_path = tmp / "sample.pptx"
    prs = Presentation()
    layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "第一页标题"
    slide.placeholders[1].text = "要点一\n要点二"
    slide2 = prs.slides.add_slide(layout)
    slide2.shapes.title.text = "第二页"
    slide2.placeholders[1].text = "更多内容"
    prs.save(pptx_path)
    return docx_path, xlsx_path, pptx_path


def main() -> int:
    from services.office_preview import read_office_preview, read_office_structured

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        docx_path, xlsx_path, pptx_path = _make_samples(tmp)

        w = read_office_structured(docx_path)
        assert w.family == "word", w.family
        assert "<h1" in w.html_body or "<h2" in w.html_body, w.html_body[:200]
        assert "加粗" in w.html_body
        assert "<table" in w.html_body
        kind, plain = read_office_preview(docx_path)
        assert "Word" in kind and "桌面预览" in plain

        x = read_office_structured(xlsx_path)
        assert x.family == "excel", x.family
        assert len(x.sheets) >= 2
        assert x.sheets[0].name == "销售"
        assert any("苹果" in c for r in x.sheets[0].rows for c in r)

        p = read_office_structured(pptx_path)
        assert p.family == "ppt", p.family
        assert len(p.slides) >= 2
        assert "第一页" in p.slides[0].title

    print("verify_office_structured: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
