# -*- coding: utf-8 -*-
"""从菜单导出功能与场景说明 Excel（用户故事 / 推广材料）。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from services.menu_registry import GROUP_LABELS, GROUP_ORDER, all_menu_items
from services.migration_manifest import get_module_status, status_label
from services.module_hotkeys import get_module_shortcut

# 模块级场景补充（菜单 desc 不够时）
SCENARIOS: dict[str, dict[str, str]] = {
    "clipboard_history": {
        "scene": "复制粘贴高频：截图/OCR/表格/话术来回切换",
        "input": "系统剪贴板文本或图片；可手动捕获",
        "output": "一键粘贴到原窗口；历史可搜索/置顶",
        "invoke": "Alt+Shift+C 速贴面板；侧栏完整页",
    },
    "directory_inspector": {
        "scene": "交付前检查目录是否缺文件、有空文件夹、命名不规范",
        "input": "本地根目录",
        "output": "路径清单 + 类型占比饼图 + 检查报告（TXT/Word/Excel）",
        "invoke": "目录 → 目录透视",
    },
    "directory_generator": {
        "scene": "新班级/新项目一次性建好标准文件夹",
        "input": "父目录 + 模板或粘贴名单",
        "output": "批量文件夹（已存在跳过）",
        "invoke": "目录 → 批量文件夹生成",
    },
    "enhanced_directory_inspector": {
        "scene": "按培训规范生成交付材料目录与 PPT 清单",
        "input": "班级目录 + 模板",
        "output": "规范化子目录与交付 PPT",
        "invoke": "业务 → 交付材料生成",
    },
    "screenshot_tool": {
        "scene": "截屏标注、翻译、OCR 链式办公",
        "input": "屏幕区域/窗口",
        "output": "图片入剪贴板/文件；可送 OCR",
        "invoke": "Alt+A 截图；办公 → 截图工具",
    },
    "quick_notepad": {
        "scene": "会议随手记、富文本草稿、模板范文",
        "input": "键盘输入；可接收剪贴板/截图",
        "output": "本地笔记文件",
        "invoke": "Alt+N；办公 → 快速记事",
    },
    "resume_extractor": {
        "scene": "批量从 PDF/PPT/Word 提取姓名手机",
        "input": "简历文件夹",
        "output": "表格 + JSON 汇总",
        "invoke": "业务 → 简历信息提取",
    },
    "notifications": {
        "scene": "任务结果、授权提醒、系统状态统一触达",
        "input": "各模块 notify_bus 事件",
        "output": "状态栏/对话框/托盘/邮件",
        "invoke": "顶栏铃铛；系统 → 通知",
    },
}


def _group_label(group_id: str) -> str:
    return GROUP_LABELS.get(group_id, group_id)


def _scenario_row(module_id: str, item: dict) -> dict[str, str]:
    extra = SCENARIOS.get(module_id, {})
    desc = str(item.get("desc") or "")
    return {
        "scene": extra.get("scene") or desc,
        "input": extra.get("input") or "见模块主界面",
        "output": extra.get("output") or "见模块主界面",
        "invoke": extra.get("invoke") or f"{_group_label(str(item.get('group') or ''))} → {item.get('name')}",
    }


def export_workbook(out_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "功能与场景"

    headers = [
        "序号",
        "子模块",
        "功能ID",
        "功能名称",
        "菜单描述",
        "用户场景",
        "典型输入",
        "典型输出",
        "唤起方式",
        "热键",
        "需授权",
        "开发状态",
        "可见",
    ]
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="2563EB")
    header_font = Font(bold=True, color="FFFFFF")
    for col, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    items = sorted(
        all_menu_items(),
        key=lambda x: (
            GROUP_ORDER.index(x.get("group"))
            if x.get("group") in GROUP_ORDER
            else 99,
            int(x.get("order") or 0),
        ),
    )

    row_idx = 2
    for n, item in enumerate(items, 1):
        mid = str(item.get("id") or "")
        if mid in ("home",):
            continue
        scen = _scenario_row(mid, item)
        status = get_module_status(mid)
        hk = get_module_shortcut(mid)
        ws.append(
            [
                n,
                _group_label(str(item.get("group") or "")),
                mid,
                str(item.get("name") or mid),
                str(item.get("desc") or ""),
                scen["scene"],
                scen["input"],
                scen["output"],
                scen["invoke"],
                hk or "—",
                "是" if item.get("requires_license") else "否",
                status_label(status),
                "是" if item.get("show", True) else "否",
            ]
        )
        row_idx += 1

    widths = [6, 10, 22, 16, 28, 32, 22, 22, 24, 12, 8, 10, 6]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for r in range(2, row_idx):
        for c in range(1, len(headers) + 1):
            ws.cell(row=r, column=c).alignment = Alignment(vertical="top", wrap_text=True)

    ws.freeze_panes = "A2"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d")
    out = ROOT / "output" / "docs" / f"TOA3-功能与场景说明-{ts}.xlsx"
    path = export_workbook(out)
    print(f"已导出: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
