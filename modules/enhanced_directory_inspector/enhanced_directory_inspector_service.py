# -*- coding: utf-8 -*-
"""交付材料：班级目录骨架 + 清单 + 完整 PPT（利刃/破晓）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_FOLDERS = [
    "01-开班资料",
    "02-教学过程",
    "03-学员作品",
    "04-考核与反馈",
    "05-结业与交付",
]

DEFAULT_CHECKLIST = [
    "开班通知 / 课表确认",
    "学员花名册",
    "授课记录与照片",
    "考核成绩表",
    "结业证书清单",
    "交付材料归档确认",
]


@dataclass
class DeliverableResult:
    class_root: Path
    created_dirs: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    engine_log: str = ""

    @property
    def summary(self) -> str:
        lines = [f"班级根目录: {self.class_root}", f"新建文件夹: {len(self.created_dirs)}"]
        lines.extend(f"  + {d}" for d in self.created_dirs)
        lines.append(f"生成文件: {len(self.files)}")
        lines.extend(f"  * {f}" for f in self.files)
        if self.engine_log.strip():
            lines.append("")
            lines.append("—— PPT 引擎日志 ——")
            lines.append(self.engine_log.strip())
        return "\n".join(lines)


def ensure_folder_structure(class_root: str | Path, folders: list[str] | None = None) -> list[str]:
    root = Path(class_root)
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for name in folders or DEFAULT_FOLDERS:
        target = root / name
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(name)
    return created


def write_checklist(class_root: str | Path, class_name: str = "") -> Path:
    root = Path(class_root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = class_name.strip() or root.name
    lines = [
        f"# 交付材料清单 · {title}",
        f"生成时间: {stamp}",
        "",
        "## 目录结构",
    ]
    for folder in DEFAULT_FOLDERS:
        lines.append(f"- [ ] {folder}/")
    lines.append("")
    lines.append("## 交付检查项")
    for item in DEFAULT_CHECKLIST:
        lines.append(f"- [ ] {item}")
    path = root / "交付材料清单.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_pptx_deliverable(
    class_root: str | Path,
    class_name: str = "",
    *,
    project_type: str = "lixiao",
) -> tuple[Path | None, str]:
    """优先完整引擎；失败回退 deliverable_ppt_service 模板填充 / stub。"""
    root = Path(class_root)
    log = ""
    try:
        from modules.enhanced_directory_inspector.toa2_ppt_engine import (
            EnhancedDirectoryInspectorPPT,
        )

        engine = EnhancedDirectoryInspectorPPT(project_type=project_type)
        if engine.set_directory(str(root)):
            out = engine.export_to_ppt()
            log = engine.log_content
            if out:
                return Path(out), log
    except Exception as exc:
        log = f"引擎异常: {exc}\n"

    try:
        from modules.enhanced_directory_inspector.deliverable_ppt_service import (
            _export_via_template_fill,
            _normalize_project_type,
        )

        path = _export_via_template_fill(
            root,
            class_name=class_name,
            project_type=_normalize_project_type(project_type),
            out_dir=None,
        )
        return path, log + "已回退到模板填充。\n"
    except Exception:
        stub = write_pptx_stub(root, class_name=class_name)
        return stub, log


def write_pptx_stub(class_root: str | Path, class_name: str = "") -> Path | None:
    """若 python-pptx 可用则写极简占位；否则返回 None。"""
    try:
        from pptx import Presentation  # type: ignore
        from pptx.util import Inches, Pt  # type: ignore
    except ImportError:
        return None

    root = Path(class_root)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    title = class_name.strip() or root.name
    box = slide.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(8.5), Inches(1.5))
    tf = box.text_frame
    tf.text = f"{title} · 交付材料"
    p = tf.paragraphs[0]
    p.font.size = Pt(28)
    out = root / "交付材料封面_stub.pptx"
    prs.save(str(out))
    return out


def generate_deliverables(
    class_root: str | Path,
    *,
    class_name: str = "",
    with_pptx: bool = True,
    project_type: str = "lixiao",
) -> DeliverableResult:
    root = Path(class_root)
    result = DeliverableResult(class_root=root)
    result.created_dirs = ensure_folder_structure(root)
    checklist = write_checklist(root, class_name=class_name)
    result.files.append(checklist.name)
    if with_pptx:
        pptx, log = write_pptx_deliverable(
            root,
            class_name=class_name,
            project_type=project_type,
        )
        result.engine_log = log or ""
        if pptx is not None:
            result.files.append(str(pptx))
        else:
            note = root / "交付材料封面_README.txt"
            note.write_text(
                "未安装 python-pptx 或模板缺失，已跳过 PPTX。清单与目录结构已生成。\n",
                encoding="utf-8",
            )
            result.files.append(note.name)
    return result
