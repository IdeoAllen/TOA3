# -*- coding: utf-8 -*-
"""助教简历：表单 → txt/md。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


FIELDS = [
    ("name", "姓名"),
    ("title", "岗位/职称"),
    ("phone", "电话"),
    ("email", "邮箱"),
    ("education", "学历"),
    ("experience", "工作经历"),
    ("skills", "擅长领域"),
    ("summary", "简介"),
]


def render_resume_md(data: dict[str, str]) -> str:
    name = (data.get("name") or "未命名").strip()
    lines = [
        f"# {name}",
        "",
        f"- 岗位：{(data.get('title') or '').strip() or '—'}",
        f"- 电话：{(data.get('phone') or '').strip() or '—'}",
        f"- 邮箱：{(data.get('email') or '').strip() or '—'}",
        f"- 学历：{(data.get('education') or '').strip() or '—'}",
        "",
        "## 简介",
        (data.get("summary") or "").strip() or "（无）",
        "",
        "## 工作经历",
        (data.get("experience") or "").strip() or "（无）",
        "",
        "## 擅长领域",
        (data.get("skills") or "").strip() or "（无）",
        "",
        f"_生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]
    return "\n".join(lines)


def render_resume_txt(data: dict[str, str]) -> str:
    # 纯文本弱化为 markdown 去标题符
    md = render_resume_md(data)
    return (
        md.replace("# ", "")
        .replace("## ", "")
        .replace("_生成时间：", "生成时间：")
        .replace("_", "")
    )


def write_resume(data: dict[str, str], out_dir: str | Path) -> list[Path]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    safe = (data.get("name") or "resume").strip() or "resume"
    for ch in '<>:"/\\|?*':
        safe = safe.replace(ch, "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{safe}_{stamp}"
    md_path = root / f"{base}.md"
    txt_path = root / f"{base}.txt"
    md_path.write_text(render_resume_md(data), encoding="utf-8")
    txt_path.write_text(render_resume_txt(data), encoding="utf-8")
    return [md_path, txt_path]
