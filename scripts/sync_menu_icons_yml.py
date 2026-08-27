# -*- coding: utf-8 -*-
"""把 app.yml 菜单 icon 改为模块 id（与 icon_registry 别名一一对应）。"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP_YML = ROOT / "config" / "app.yml"

OVERRIDE = {
    "screenshot_tool": "camera",
    "watermark_photo_generator": "watermark_photo",
}


def _find_id_near(lines: list[str], icon_idx: int) -> str | None:
    start = max(0, icon_idx - 20)
    end = min(len(lines), icon_idx + 20)
    # 同一 list item：遇到下一个「- class_name」或「- id」块边界停止
    # 先向下
    for j in range(icon_idx + 1, end):
        s = lines[j].lstrip()
        if s.startswith("- class_name:") or s.startswith("- class_name "):
            break
        if s.startswith("id:"):
            return s.split(":", 1)[1].strip()
    # 再向上
    for j in range(icon_idx - 1, start - 1, -1):
        s = lines[j].lstrip()
        if s.startswith("- class_name:") or s.startswith("- class_name "):
            break
        if s.startswith("id:"):
            return s.split(":", 1)[1].strip()
    return None


def main() -> None:
    text = APP_YML.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("icon:"):
            mid = _find_id_near(lines, i)
            if mid:
                icon = OVERRIDE.get(mid, mid)
                indent = line[: len(line) - len(stripped)]
                out.append(f"{indent}icon: {icon}\n")
                continue
        out.append(line)
    APP_YML.write_text("".join(out), encoding="utf-8")
    data = yaml.safe_load(APP_YML.read_text(encoding="utf-8"))
    for it in data["menu"]["menu_items"]:
        print(f"{it['id']:40s} -> {it.get('icon')}")


if __name__ == "__main__":
    main()
