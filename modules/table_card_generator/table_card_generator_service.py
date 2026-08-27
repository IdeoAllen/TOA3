# -*- coding: utf-8 -*-
"""桌卡：名单 / Excel → 文本卡或 PPTX（对标 TOA2 桌卡生成）。"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from services.storage_paths import list_module_templates

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

PLACEHOLDER_KEYWORDS = (
    "姓名",
    "{姓名}",
    "{name}",
    "name",
    "名字",
    "学员姓名",
    "人员姓名",
    "员工姓名",
)


def parse_names(raw: str) -> list[str]:
    return filter_valid_names((raw or "").splitlines())


def filter_valid_names(names: Iterable[str]) -> list[str]:
    valid: list[str] = []
    for n in names or []:
        s = str(n).strip()
        if not s or s.lower() == "nan" or s == "姓名":
            continue
        if HAS_PANDAS:
            try:
                if pd.isna(n):
                    continue
            except Exception:
                pass
        valid.append(s)
    return valid


@dataclass
class CardResult:
    out_dir: Path
    files: list[str] = field(default_factory=list)
    mode: str = "text"

    @property
    def summary(self) -> str:
        return (
            f"模式: {self.mode}\n输出目录: {self.out_dir}\n文件数: {len(self.files)}\n"
            + "\n".join(f"  - {f}" for f in self.files)
        )


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "card"
    return cleaned[:60]


def resolve_template(template: Path | None = None) -> Path | None:
    if template is not None and template.is_file():
        return template
    templates = list_module_templates("table_card_generator")
    return templates[0] if templates else None


def replace_name_in_slide(slide, name: str) -> bool:
    replaced = False
    for shape in slide.shapes:
        if not hasattr(shape, "text_frame") or not shape.text_frame:
            continue
        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                for kw in PLACEHOLDER_KEYWORDS:
                    if kw in run.text:
                        run.text = run.text.replace(kw, name)
                        replaced = True
    if not replaced:
        for shape in slide.shapes:
            if hasattr(shape, "text_frame") and shape.text_frame:
                text_val = (getattr(shape, "text", "") or "").strip()
                if text_val == "" or text_val in PLACEHOLDER_KEYWORDS:
                    shape.text = name
                    return True
    if not replaced:
        for shape in slide.shapes:
            if hasattr(shape, "text_frame") and shape.text_frame:
                shape.text = name
                return True
    return replaced


def generate_text_cards(names: list[str], out_dir: str | Path) -> CardResult:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    result = CardResult(out_dir=root, mode="text")
    for i, name in enumerate(names, 1):
        path = root / f"{i:02d}_{_safe_filename(name)}.txt"
        path.write_text(f"桌卡\n----\n{name}\n", encoding="utf-8")
        result.files.append(path.name)
    index = root / "index.txt"
    index.write_text("\n".join(f"{i}. {n}" for i, n in enumerate(names, 1)) + "\n", encoding="utf-8")
    result.files.append(index.name)
    return result


def generate_single_pptx(
    name: str,
    out_dir: str | Path,
    *,
    template: Path | None = None,
) -> Path:
    try:
        from pptx import Presentation  # type: ignore
    except ImportError as exc:
        raise ImportError("未安装 python-pptx，请执行 pip install python-pptx") from exc

    tpl = resolve_template(template)
    if tpl is None:
        raise FileNotFoundError("未找到桌卡 PPTX 模板，请检查 config/storage.yml")

    prs = Presentation(str(tpl))
    for slide in prs.slides:
        replace_name_in_slide(slide, name)

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = root / f"桌卡_{_safe_filename(name)}_{stamp}.pptx"
    prs.save(str(out))
    return out


def generate_cards_separate(
    names: list[str],
    out_dir: str | Path,
    *,
    template: Path | None = None,
) -> CardResult:
    valid = filter_valid_names(names)
    if not valid:
        raise ValueError("未找到有效姓名")
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    tpl = resolve_template(template)
    files: list[str] = []
    mode = "pptx" if tpl else "text"
    if tpl:
        try:
            for name in valid:
                path = generate_single_pptx(name, root, template=tpl)
                files.append(path.name)
        except ImportError:
            mode = "text"
    if mode == "text":
        tr = generate_text_cards(valid, root)
        return tr
    return CardResult(out_dir=root, files=files, mode=mode)


def generate_cards_merged(
    names: list[str],
    out_dir: str | Path,
    *,
    template: Path | None = None,
) -> CardResult:
    valid = filter_valid_names(names)
    if not valid:
        raise ValueError("未找到有效姓名")
    tpl = resolve_template(template)
    if tpl is None:
        return generate_text_cards(valid, out_dir)

    try:
        from pptx import Presentation  # type: ignore
    except ImportError:
        return generate_text_cards(valid, out_dir)

    final_prs = Presentation(str(tpl))
    source_prs = Presentation(str(tpl))
    if not final_prs.slides or not source_prs.slides:
        raise RuntimeError("模板中没有幻灯片")
    template_slide = final_prs.slides[0]
    template_layout = template_slide.slide_layout
    source_template_slide = source_prs.slides[0]

    replace_name_in_slide(template_slide, valid[0])
    for name_str in valid[1:]:
        new_slide = final_prs.slides.add_slide(template_layout)
        for shape in list(new_slide.shapes):
            sp = shape._element
            sp.getparent().remove(sp)
        for shape in source_template_slide.shapes:
            new_slide.shapes._spTree.append(deepcopy(shape._element))
        replace_name_in_slide(new_slide, name_str)

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = root / f"桌卡_批量合并_{stamp}.pptx"
    final_prs.save(str(out))
    return CardResult(out_dir=root, files=[out.name], mode="pptx")


def find_name_column(df) -> int | None:
    name_keywords = ["姓名", "名字", "name", "姓", "名", "学员姓名", "人员姓名", "员工姓名"]
    for i, column in enumerate(df.columns):
        if str(column).strip() == "姓名":
            return i
    for i, column in enumerate(df.columns):
        column_name = str(column).lower()
        for keyword in name_keywords:
            if keyword.lower() in column_name:
                return i
    for col_idx in range(min(5, len(df.columns))):
        sample_data = df.iloc[:10, col_idx].dropna()
        name_like = 0
        for data in sample_data:
            data_str = str(data)
            if 2 <= len(data_str) <= 4 and any("\u4e00" <= c <= "\u9fff" for c in data_str):
                name_like += 1
        if sample_data.size and name_like >= len(sample_data) * 0.6:
            return col_idx
    return 0 if len(df.columns) > 0 else None


def list_excel_columns(excel_path: str | Path) -> list[str]:
    if not HAS_PANDAS:
        raise ImportError("未安装 pandas/openpyxl，请执行 pip install pandas openpyxl")
    path = Path(excel_path)
    if not path.is_file():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")
    df = pd.read_excel(path, nrows=0)
    return [str(c) for c in df.columns]


def read_names_from_excel(
    excel_path: str | Path,
    *,
    name_column: str | int | None = None,
) -> list[str]:
    if not HAS_PANDAS:
        raise ImportError("未安装 pandas/openpyxl，请执行 pip install pandas openpyxl")
    path = Path(excel_path)
    if not path.is_file():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")
    df = pd.read_excel(path)
    if name_column is not None and str(name_column).strip() != "":
        col_name = str(name_column).strip()
        if col_name in df.columns:
            return filter_valid_names(df[col_name].tolist())
        try:
            idx = int(col_name)
            if 0 <= idx < len(df.columns):
                return filter_valid_names(df.iloc[:, idx].tolist())
        except ValueError:
            pass
        raise ValueError(f"找不到姓名列：{col_name}")
    col = find_name_column(df)
    if col is None:
        raise ValueError("无法在 Excel 中找到姓名列")
    return filter_valid_names(df.iloc[:, col].tolist())


def generate_cards(
    names: list[str],
    out_dir: str | Path,
    *,
    prefer_pptx: bool = True,
    merged: bool = True,
    template: Path | None = None,
) -> CardResult:
    if not names:
        raise ValueError("名单为空")
    if prefer_pptx and resolve_template(template):
        if merged:
            return generate_cards_merged(names, out_dir, template=template)
        return generate_cards_separate(names, out_dir, template=template)
    return generate_text_cards(filter_valid_names(names), out_dir)
