# -*- coding: utf-8 -*-
"""助教简历 PPTX 生成（从 TOA2 generator 移植核心逻辑）。"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from services.config_service import resolve_path
from services.storage_paths import list_module_templates, module_output_dir

logger = logging.getLogger(__name__)

FIELD_MAP = {
    "name": "姓名",
    "title": "岗位",
    "phone": "电话",
    "email": "邮箱",
    "education": "学历",
    "experience": "汽车行业培训经验",
    "skills": "擅长领域",
    "summary": "个人简介",
}


def _knowledge_base_path() -> Path:
    try:
        return resolve_path("knowledge_base")
    except Exception:
        return resolve_path("data_dir") / "knowledge_base.json"


def load_knowledge_base() -> dict[str, Any]:
    path = _knowledge_base_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("加载知识库失败: %s", e)
        return {}


def _to_placeholder_data(data: dict[str, str], kb: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, label in FIELD_MAP.items():
        val = str(data.get(key) or "").strip()
        if val:
            out[label] = val
    name = out.get("姓名") or str(data.get("name") or "").strip()
    if name:
        out["姓名"] = name

    def _pick_list(k: str) -> str:
        vals = kb.get(k, [])
        return random.choice(vals) if isinstance(vals, list) and vals else ""

    if not out.get("年龄"):
        age = _pick_list("ages")
        if age:
            out["年龄"] = str(age)
    if not out.get("学历"):
        edu = _pick_list("educations")
        if edu:
            out["学历"] = str(edu)
    if not out.get("汽车行业培训经验"):
        exp = _pick_list("training_experiences") or _pick_list("training_exps")
        if exp:
            out["汽车行业培训经验"] = str(exp)

    brands_map = kb.get("brands") if isinstance(kb.get("brands"), dict) else {}
    if brands_map and not out.get("服务过的品牌"):
        valid = [b for b, projs in brands_map.items() if isinstance(projs, list) and projs]
        if valid:
            chosen = random.sample(valid, k=min(3, len(valid)))
            out["服务过的品牌"] = "、".join(chosen)
            pairs: list[str] = []
            for b in chosen:
                projs = brands_map.get(b) or []
                if projs:
                    pairs.append(f"{b}-{random.choice(projs)}")
            if pairs and not out.get("汽车行业运营项目"):
                out["汽车行业运营项目"] = "、".join(pairs)
    return out


def _replace_placeholders_in_ppt(prs, mapping: dict[str, str]):
    pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping.keys(), key=len, reverse=True)))

    def _replace_text(text: str) -> str:
        def repl(m):
            return mapping.get(m.group(0), m.group(0))

        return pattern.sub(repl, text or "")

    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text_frame") and shape.text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        new = _replace_text(run.text)
                        if new != run.text:
                            run.text = new
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        if cell.text_frame:
                            for para in cell.text_frame.paragraphs:
                                for run in para.runs:
                                    new = _replace_text(run.text)
                                    if new != run.text:
                                        run.text = new


def generate_resume_pptx(
    data: dict[str, str],
    out_dir: str | Path | None = None,
) -> list[Path]:
    """生成 PPTX + 信息 txt；无模板时退回 txt/md。"""
    from modules.teaching_assistant_resume.teaching_assistant_resume_service import (
        render_resume_md,
        write_resume,
    )

    root = Path(out_dir) if out_dir else module_output_dir("teaching_assistant_resume", create=True)
    root.mkdir(parents=True, exist_ok=True)
    templates = list_module_templates("teaching_assistant_resume")
    kb = load_knowledge_base()
    placeholder = _to_placeholder_data(data, kb)
    name = placeholder.get("姓名") or data.get("name") or "resume"
    safe = re.sub(r'[<>:"/\\|?*]', "_", str(name)).strip() or "resume"

    outputs: list[Path] = []
    if templates:
        try:
            from pptx import Presentation  # type: ignore

            template = templates[0]
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = root / f"{safe}简历_{stamp}.pptx"
            shutil.copy2(template, dest)
            prs = Presentation(str(dest))
            _replace_placeholders_in_ppt(prs, placeholder)
            prs.save(str(dest))
            outputs.append(dest)
            info = root / f"{safe}_信息.txt"
            info.write_text(
                "\n".join(f"{k}: {v}" for k, v in placeholder.items()) + "\n",
                encoding="utf-8",
            )
            outputs.append(info)
            return outputs
        except ImportError:
            pass

    outputs.extend(write_resume(data, root))
    md_path = root / f"{safe}.md"
    md_path.write_text(render_resume_md(data), encoding="utf-8")
    if md_path not in outputs:
        outputs.append(md_path)
    return outputs


def generate_resumes_from_excel(excel_path: str | Path, out_dir: str | Path | None = None) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError("批量生成需要 pandas/openpyxl") from exc

    path = Path(excel_path)
    df = pd.read_excel(path)
    if df.empty:
        raise ValueError("Excel 为空")
    root = Path(out_dir) if out_dir else module_output_dir("teaching_assistant_resume", create=True)
    success = 0
    failed = 0
    errors: list[str] = []
    col_map = {str(c).strip(): c for c in df.columns}
    for _, row in df.iterrows():
        data: dict[str, str] = {}
        for key, label in FIELD_MAP.items():
            if label in col_map:
                data[key] = str(row[col_map[label]] or "").strip()
            elif key in col_map:
                data[key] = str(row[col_map[key]] or "").strip()
        if not data.get("name") and "姓名" in col_map:
            data["name"] = str(row[col_map["姓名"]] or "").strip()
        if not data.get("name"):
            failed += 1
            errors.append("跳过空姓名行")
            continue
        try:
            generate_resume_pptx(data, root)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"{data.get('name')}: {e}")
    return {"total": success + failed, "success": success, "failed": failed, "errors": errors}
