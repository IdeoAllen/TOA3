# -*- coding: utf-8 -*-
"""Excel/CSV 列选择行转列（对标 TOA2，含经销商简称规则）。"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

DEFAULT_BRANDS = [
    "宝马", "奔驰", "奥迪", "丰田", "本田", "大众", "日产", "福特",
    "别克", "现代", "起亚", "马自达", "奇瑞", "吉利", "长城", "比亚迪",
    "特斯拉", "蔚来", "小鹏", "理想", "五菱", "长安",
]

COMPANY_TYPES = [
    "汽车销售", "汽车贸易", "汽车服务", "汽车有限公司", "汽车销售服务",
    "销售服务有限公司", "汽车贸易有限公司", "有限公司", "集团",
]


def _has_pandas() -> bool:
    try:
        import pandas  # noqa: F401

        return True
    except ImportError:
        return False


def load_table(src: str | Path) -> tuple[Any, list[str]]:
    """返回 (dataframe 或 rows, columns)。"""
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"文件不存在: {src_path}")
    ext = src_path.suffix.lower()
    if _has_pandas():
        import pandas as pd

        if ext in {".xlsx", ".xls"}:
            df = pd.read_excel(src_path)
        else:
            df = pd.read_csv(src_path)
        return df, [str(c) for c in df.columns]

    if ext in {".xlsx", ".xls"}:
        raise RuntimeError("未安装 pandas，无法读取 Excel；请改用 CSV，或安装 pandas。")
    rows: list[list[str]] = []
    with src_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(list(row))
    if not rows:
        return [], []
    header = rows[0]
    return rows[1:], header


def list_columns(src: str | Path) -> list[str]:
    _, cols = load_table(src)
    return cols


def extract_dealer_abbreviation(dealer_name: str, brands: list[str] | None = None) -> str:
    brand_keywords = brands or DEFAULT_BRANDS
    dealer_name = str(dealer_name).strip()
    if not dealer_name:
        return ""
    for brand in brand_keywords:
        if brand in dealer_name:
            return brand
    cleaned = dealer_name
    for company_type in COMPANY_TYPES:
        cleaned = cleaned.replace(company_type, "")
    chinese_chars = re.findall(r"[\u4e00-\u9fa5]+", cleaned)
    if chinese_chars:
        return chinese_chars[0][: min(4, len(chinese_chars[0]))]
    return dealer_name[: min(4, len(dealer_name))]


def convert_selected_columns(src: str | Path, selected_columns: list[str]) -> Any:
    """按 TOA2 规则：选中列 → 每原始行变成新列。返回 DataFrame。"""
    if not selected_columns:
        raise ValueError("请至少选择一列")
    if not _has_pandas():
        raise RuntimeError("列选择行转列需要 pandas")

    import pandas as pd

    df, columns = load_table(src)
    for col in selected_columns:
        if col not in columns:
            raise ValueError(f"列不存在: {col}")

    result_dict: dict[str, list] = {}
    dealer_abbreviations: list[str] = []
    has_dealer_column = False
    dealer_col_index = -1
    for idx, col_name in enumerate(selected_columns):
        if "经销商名称" in col_name or "dealer" in col_name.lower():
            has_dealer_column = True
            dealer_col_index = idx
            break

    for col_idx, col_name in enumerate(selected_columns):
        column_values = df[col_name].fillna("").astype(str).tolist()
        for row_idx, value in enumerate(column_values):
            new_col_name = f"行{row_idx + 1}"
            if new_col_name not in result_dict:
                result_dict[new_col_name] = [None] * len(selected_columns)
            result_dict[new_col_name][col_idx] = value
            if has_dealer_column and col_idx == dealer_col_index:
                while len(dealer_abbreviations) <= row_idx:
                    dealer_abbreviations.append("")
                dealer_abbreviations[row_idx] = extract_dealer_abbreviation(value)

    result = pd.DataFrame(result_dict)
    result.insert(0, "原始列名", selected_columns)

    if has_dealer_column and dealer_abbreviations:
        full = dealer_abbreviations + [""] * max(0, len(result) - len(dealer_abbreviations))
        result.insert(1, "经销商简称", full[: len(result)])
        checks = []
        dealer_name_col = next(
            (c for c in selected_columns if "经销商名称" in c or "dealer" in c.lower()),
            None,
        )
        for idx in range(len(result)):
            if dealer_name_col and idx < len(df):
                dealer_name = str(df.iloc[idx][dealer_name_col])
                if not dealer_name or dealer_name == "nan" or not dealer_name.strip():
                    checks.append("名称为空")
                elif extract_dealer_abbreviation(dealer_name) == dealer_name:
                    checks.append("可能为简称")
                else:
                    checks.append("名称完整")
            else:
                checks.append("")
        result.insert(2, "经销商检查", checks[: len(result)])
    return result


def transpose_file(src: str | Path, dest: str | Path | None = None) -> Path:
    """整表转置（兼容旧入口）。"""
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"文件不存在: {src_path}")

    if dest is None:
        dest = src_path.with_name(f"{src_path.stem}_transposed{src_path.suffix or '.csv'}")
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    ext = src_path.suffix.lower()
    if _has_pandas():
        import pandas as pd

        if ext in {".xlsx", ".xls"}:
            df = pd.read_excel(src_path, header=None)
        else:
            df = pd.read_csv(src_path, header=None)
        out = df.T
        if dest_path.suffix.lower() in {".xlsx", ".xls"}:
            from services.excel_export import dataframe_to_xlsx

            dataframe_to_xlsx(out, dest_path, header=False)
        else:
            if dest_path.suffix.lower() != ".csv":
                dest_path = dest_path.with_suffix(".csv")
            out.to_csv(dest_path, index=False, header=False)
        return dest_path

    if ext in {".xlsx", ".xls"}:
        raise RuntimeError("未安装 pandas，无法读取 Excel；请改用 CSV，或安装 pandas。")

    rows: list[list[str]] = []
    with src_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(list(row))
    if not rows:
        dest_path.write_text("", encoding="utf-8")
        return dest_path

    width = max(len(r) for r in rows)
    for r in rows:
        while len(r) < width:
            r.append("")
    transposed = list(zip(*rows))
    out_path = dest_path if dest_path.suffix.lower() == ".csv" else dest_path.with_suffix(".csv")
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        for row in transposed:
            writer.writerow(row)
    return out_path


def save_converted(
    result,
    dest: str | Path,
) -> Path:
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        from services.excel_export import dataframe_to_xlsx

        dataframe_to_xlsx(result, path)
    else:
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        result.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def preview_result(result, max_rows: int = 5, max_cols: int = 5) -> str:
    preview = result.iloc[: min(max_rows, len(result)), : min(max_cols, len(result.columns))]
    lines = [" | ".join(str(c) for c in preview.columns), "-" * 40]
    for _, row in preview.iterrows():
        lines.append(" | ".join(str(v) if v not in (None, "") else "空" for v in row))
    if len(result) > max_rows:
        lines.append("... 还有更多行 ...")
    if len(result.columns) > max_cols:
        lines.append(f"... 还有 {len(result.columns) - max_cols} 列 ...")
    return "\n".join(lines)
