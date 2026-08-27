# -*- coding: utf-8 -*-
"""批量文件夹生成 — 内置模板（可扩展）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# key → (显示名, 多行文件夹名)
DIRECTORY_TEMPLATES: dict[str, tuple[str, str]] = {
    "blank": ("空白（自行粘贴）", ""),
    "class": (
        "班级交付",
        "学员材料\n签到表\n课件\n结业证书\n照片归档",
    ),
    "project": (
        "项目归档",
        "01-需求\n02-设计\n03-开发\n04-测试\n05-交付",
    ),
    "archive": (
        "资料归档",
        "合同\n发票\n往来邮件\n会议纪要\n其它",
    ),
    "training_week": (
        "培训周结构",
        "Day1-开班\nDay2-授课\nDay3-演练\nDay4-考核\nDay5-结业\n后勤物资\n学员名单",
    ),
    "photo_deliver": (
        "照片交付",
        "开班合影\n课堂互动\n实操演练\n结业合影\n原始素材",
    ),
    "resume_batch": (
        "招聘简历批次",
        "待筛选\n初面通过\n复试通过\n已录用\n已淘汰",
    ),
    "name_list": (
        "学员名单占位",
        "学员01\n学员02\n学员03\n学员04\n学员05",
    ),
}


@dataclass
class CreateResult:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines = [
            f"创建 {len(self.created)} 个，跳过已存在 {len(self.skipped)} 个，失败 {len(self.errors)} 个。"
        ]
        for name in self.created:
            lines.append(f"  + {name}")
        for name in self.skipped:
            lines.append(f"  = {name}（已存在）")
        for err in self.errors:
            lines.append(f"  ! {err}")
        return "\n".join(lines)


def parse_names(raw: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in (raw or "").splitlines():
        name = line.strip().strip("/\\")
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def create_directories(parent: str | Path, names: list[str]) -> CreateResult:
    root = Path(parent)
    result = CreateResult()
    if not root.is_dir():
        result.errors.append(f"父目录不存在: {root}")
        return result
    for name in names:
        target = root / name
        try:
            if target.exists():
                result.skipped.append(name)
                continue
            target.mkdir(parents=True, exist_ok=False)
            result.created.append(name)
        except OSError as e:
            result.errors.append(f"{name}: {e}")
    return result
