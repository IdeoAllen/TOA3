# -*- coding: utf-8 -*-
"""导出 Excel：按单元格内容自适应列宽与行高，避免打开后再手调。"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def _display_width(text: str) -> float:
    """Excel 列宽近似：ASCII≈1，中日韩等全角≈2。"""
    w = 0.0
    for ch in str(text):
        o = ord(ch)
        if o <= 0x1F:
            continue
        if o > 0x7F:
            w += 2.0
        else:
            w += 1.0
    return w


def autofit_worksheet(
    ws,
    *,
    min_width: float = 8.0,
    max_width: float = 64.0,
    min_row_height: float = 18.0,
    max_row_height: float = 140.0,
    pad: float = 2.2,
) -> None:
    """按内容设置列宽、行高，并给多行/过长单元格开启自动换行。"""
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    if ws.max_row is None or ws.max_column is None:
        return
    if ws.max_row < 1 or ws.max_column < 1:
        return

    col_widths: dict[int, float] = {}
    for col_idx in range(1, int(ws.max_column) + 1):
        best = min_width
        for row in ws.iter_rows(
            min_row=1,
            max_row=int(ws.max_row),
            min_col=col_idx,
            max_col=col_idx,
        ):
            cell = row[0]
            if cell.value is None:
                continue
            val = str(cell.value)
            for line in val.splitlines() or [val]:
                best = max(best, _display_width(line) + pad)
        col_widths[col_idx] = min(max_width, best)
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths[col_idx]

    for row_idx in range(1, int(ws.max_row) + 1):
        lines_needed = 1
        for cell in ws[row_idx]:
            if cell.value is None:
                continue
            val = str(cell.value)
            explicit = val.count("\n") + 1
            col_w = col_widths.get(cell.column, min_width) or min_width
            wrap_lines = 1
            for line in val.splitlines() or [val]:
                dw = _display_width(line)
                wrap_lines = max(wrap_lines, int(math.ceil(dw / max(col_w, 1.0))))
            need = max(explicit, wrap_lines)
            lines_needed = max(lines_needed, need)
            if need > 1 or "\n" in val:
                prev = cell.alignment
                cell.alignment = Alignment(
                    wrap_text=True,
                    vertical="center",
                    horizontal=prev.horizontal if prev and prev.horizontal else "general",
                )
        ws.row_dimensions[row_idx].height = min(
            max_row_height,
            max(min_row_height, 15.0 * lines_needed + 3.0),
        )


def autofit_workbook(wb) -> None:
    for ws in wb.worksheets:
        autofit_worksheet(ws)


def autofit_xlsx_file(path: str | Path) -> Path:
    """对已写出的 xlsx 再打开并自适应后保存。"""
    from openpyxl import load_workbook

    p = Path(path)
    wb = load_workbook(p)
    autofit_workbook(wb)
    wb.save(p)
    return p


def dataframe_to_xlsx(
    df: Any,
    path: str | Path,
    *,
    sheet_name: str = "Sheet1",
    index: bool = False,
    header: bool = True,
) -> Path:
    """pandas DataFrame → xlsx，并按内容自适应列宽行高。"""
    import pandas as pd

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        df.to_excel(writer, index=index, header=header, sheet_name=sheet_name[:31] or "Sheet1")
        autofit_workbook(writer.book)
    return dest


def finalize_excel_writer(writer) -> None:
    """在 ``with pd.ExcelWriter(...) as writer`` 块末尾调用。"""
    book = getattr(writer, "book", None)
    if book is not None:
        autofit_workbook(book)
