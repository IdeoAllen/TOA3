# -*- coding: utf-8 -*-
"""从 TOA2 同步随包模板与示例到 assets/（可选，首次搭建）。"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOA2 = ROOT.parent / "TOA"
DEST_TEMPLATES = ROOT / "assets" / "templates"
DEST_SAMPLES = ROOT / "assets" / "samples"

# TOA2 路径 → assets 内相对路径
TEMPLATE_MAP = {
    "templates/简历模版.pptx": "business/resume.pptx",
    "templates/台卡模板.pptx": "business/table_card.pptx",
    "templates/利刃交付材料模版.pptx": "deliverables/lixiao.pptx",
    "templates/破晓交付材料模版.pptx": "deliverables/poxiao.pptx",
    "templates/通用生成工具模版/demo3.txt": "generators/demo3.txt",
}

SAMPLE_MAP = {
    "data/generator_tasks/demo_task_json.json": "modules/generic_generator_simple/demo_task.json",
    "data/generator_tasks/demo_task_txt.json": "modules/generic_generator_simple/demo_task_txt.json",
    "data/deduction_note_history.json": "modules/deduction_note_formatter/history.example.json",
}


def main() -> None:
    if not TOA2.is_dir():
        print(f"TOA2 不存在: {TOA2}")
        return
    DEST_TEMPLATES.mkdir(parents=True, exist_ok=True)
    DEST_SAMPLES.mkdir(parents=True, exist_ok=True)
    n = 0
    for src_rel, dst_rel in TEMPLATE_MAP.items():
        src = TOA2 / src_rel.replace("/", "\\")
        dst = DEST_TEMPLATES / dst_rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print("template", dst_rel)
            n += 1
    for src_rel, dst_rel in SAMPLE_MAP.items():
        src = TOA2 / src_rel.replace("/", "\\")
        dst = DEST_SAMPLES / dst_rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print("sample", dst_rel)
            n += 1
    print(f"done: {n} files")


if __name__ == "__main__":
    main()
