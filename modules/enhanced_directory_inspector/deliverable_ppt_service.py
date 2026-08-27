# -*- coding: utf-8 -*-
"""交付材料 PPTX：优先 TOA2 完整引擎，失败再回退模板填充。"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from services.storage_paths import bundled_templates_dir, list_module_templates, module_output_dir

logger = logging.getLogger(__name__)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _normalize_project_type(project_type: str) -> str:
    p = (project_type or "lixiao").strip().lower()
    if p in ("liren", "利刃"):
        return "lixiao"
    if p in ("破晓",):
        return "poxiao"
    return p if p in ("lixiao", "poxiao") else "lixiao"


def _find_deliverable_template(project_type: str = "lixiao") -> Path | None:
    keys = {
        "lixiao": ["deliverables/lixiao.pptx", "deliverables/利刃交付材料模版.pptx"],
        "liren": ["deliverables/lixiao.pptx", "deliverables/利刃交付材料模版.pptx"],
        "poxiao": ["deliverables/poxiao.pptx", "deliverables/破晓交付材料模版.pptx"],
    }
    names = keys.get(project_type, keys["lixiao"])
    root = bundled_templates_dir()
    for name in names:
        p = root / name
        if p.is_file():
            return p
    for name in names:
        p = root / Path(name).name
        if p.is_file():
            return p
    tpls = list_module_templates("deliverable")
    return tpls[0] if tpls else None


def _first_image_in(*dirs: Path) -> Path | None:
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                return p
    return None


def _replace_class_name(prs, class_name: str) -> None:
    keywords = ("班级名称", "模板班级名称", "{{班级}}", "{{class_name}}")
    for slide in prs.slides:
        for shape in slide.shapes:
            if not hasattr(shape, "text_frame") or not shape.text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    text = run.text
                    for kw in keywords:
                        if kw in text:
                            run.text = text.replace(kw, class_name)


def _add_picture_if_slot(slide, img_path: Path, left_in, top_in, width_in, height_in) -> bool:
    if not img_path or not img_path.is_file():
        return False
    try:
        from pptx.util import Inches  # type: ignore

        slide.shapes.add_picture(
            str(img_path),
            Inches(left_in),
            Inches(top_in),
            width=Inches(width_in),
            height=Inches(height_in),
        )
        return True
    except Exception as e:
        logger.warning("嵌入图片失败 %s: %s", img_path, e)
        return False


def _export_via_engine(
    class_root: Path,
    *,
    project_type: str,
    out_dir: Path | None,
) -> Path | None:
    from modules.enhanced_directory_inspector.toa2_ppt_engine import (
        EnhancedDirectoryInspectorPPT,
    )

    engine = EnhancedDirectoryInspectorPPT(project_type=project_type)
    if not engine.set_directory(str(class_root)):
        return None
    dest: Path | None = None
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = out_dir / f"{class_root.name}_交付材料_{stamp}.pptx"
    result = engine.export_to_ppt(dest)
    return Path(result) if result else None


def _export_via_template_fill(
    class_root: Path,
    *,
    class_name: str,
    project_type: str,
    out_dir: Path | None,
) -> Path:
    from pptx import Presentation  # type: ignore

    title = (class_name or class_root.name).strip()
    template = _find_deliverable_template(project_type)
    if template is None:
        raise FileNotFoundError("未找到交付材料 PPTX 模板（deliverables/lixiao 或 poxiao）")

    prs = Presentation(str(template))
    if len(prs.slides) < 1:
        raise RuntimeError("模板无幻灯片")
    _replace_class_name(prs, title)

    photo_root = class_root / "03-教室布置照片-PPT&钉钉"
    if not photo_root.is_dir():
        photo_root = class_root / "03-教室布置照片"
    img = _first_image_in(
        photo_root / "01-布置完成的全景照片-PPT",
        photo_root / "04-上墙物料-钉钉",
        photo_root,
        class_root,
    )
    if img and prs.slides:
        _add_picture_if_slot(prs.slides[0], img, 7.5, 1.2, 4.5, 3.0)

    dest_dir = Path(out_dir) if out_dir else module_output_dir("enhanced_directory_inspector", create=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = dest_dir / f"{title}_交付材料_{stamp}.pptx"
    prs.save(str(out))
    return out


def export_deliverable_pptx(
    class_root: str | Path,
    *,
    class_name: str = "",
    project_type: str = "lixiao",
    out_dir: str | Path | None = None,
) -> Path:
    """优先完整引擎；引擎失败时回退模板填充。"""
    root = Path(class_root)
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录: {root}")
    ptype = _normalize_project_type(project_type)
    dest_dir = Path(out_dir) if out_dir else None

    try:
        via_engine = _export_via_engine(root, project_type=ptype, out_dir=dest_dir)
        if via_engine is not None and via_engine.is_file():
            return via_engine
        logger.warning("完整 PPT 引擎未产出文件，回退模板填充")
    except Exception as exc:
        logger.warning("完整 PPT 引擎失败，回退模板填充: %s", exc)

    return _export_via_template_fill(
        root,
        class_name=class_name,
        project_type=ptype,
        out_dir=dest_dir,
    )
