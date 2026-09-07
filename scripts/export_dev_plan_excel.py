# -*- coding: utf-8 -*-
"""
导出 TOA3 协作用 Excel（三档路线图：Ready / 眼下 / 未来）。

协作真相源：https://docs.qq.com/sheet/DT05mY3ZXcGpneEpF?tab=000001
落盘：`output/docs/TOA3-开发与功能手册-*.xlsx`（禁止写入 docs/）
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from scripts.export_menu_catalog_excel import export_workbook as _export_catalog_sheet
from services.menu_registry import GROUP_LABELS, all_menu_items
from services.migration_manifest import get_module_status, status_label
from services.module_hotkeys import get_module_shortcut

COLLAB_SHEET_URL = "https://docs.qq.com/sheet/DT05mY3ZXcGpneEpF?tab=000001"

TIER_FILL = {
    "Ready·体验版": "107C10",
    "眼下做": "2563EB",
    "未来做": "6B7280",
    "实验附带": "F0A020",
}

# —— 眼下做：仅系统/架构/发版（体验版阶段不修 MVP 小瑕疵）——
NOW_TASKS: list[dict[str, str]] = [
    {
        "seq": "1",
        "area": "发版",
        "item": "体验版 v3.0.0-beta 定稿",
        "goal": "小范围调研可装、可授权、核心 done 功能可用",
        "next": "VM 干净机试装 Setup；定体验版菜单白名单",
        "owner": "Agent+主理人",
        "acceptance": "TOA3-Setup-v3.0.0.exe；无 skip_login；license 走 DMS",
    },
    {
        "seq": "2",
        "area": "发版",
        "item": "DMS 发布 draft（体验版说明+下载链）",
        "goal": "Portal 可下载体验包；人审后 deploy",
        "next": "主理人审 draft → deploy.ps1",
        "owner": "主理人审+Agent建draft",
        "acceptance": "draft 含版本说明、风险、回滚、安装包路径",
    },
    {
        "seq": "3",
        "area": "架构",
        "item": "体验版菜单/feature_pack 裁剪",
        "goal": "侧栏只主推 Ready；MVP 标实验或不展示",
        "next": "config feature_packs 或 menu 体验版 profile",
        "owner": "Agent",
        "acceptance": "调研用户只见承诺功能；stub 不可见",
    },
    {
        "seq": "4",
        "area": "架构",
        "item": "About 检查更新（预留网络版）",
        "goal": "关于页可查新版本；异步不卡启动",
        "next": "DMS release manifest API + About 按钮",
        "owner": "Agent",
        "acceptance": "有/无新版本均可离线用；一键打开下载页",
    },
    {
        "seq": "5",
        "area": "架构",
        "item": "插件化/feature_packs 文档与登记",
        "goal": "模块可拆可合；新能力走 manifest+menu",
        "next": "补 docs 一页纸 + feature_packs 与菜单映射表",
        "owner": "Agent",
        "acceptance": "新增模块路径：research→manifest→menu→pack",
    },
    {
        "seq": "6",
        "area": "系统",
        "item": "冻结包路径与授权回归",
        "goal": "安装后 data 在 LOCALAPPDATA；release 配置生效",
        "next": "打包机 smoke：安装→激活→重启",
        "owner": "Agent",
        "acceptance": "不加载 app.dev.yml；license.json 干净",
    },
    {
        "seq": "7",
        "area": "协作",
        "item": "体验版调研反馈表",
        "goal": "小范围用户故事+满意度+是否愿卸独立软件",
        "next": "腾讯文档加「调研反馈」Sheet 或问卷链接",
        "owner": "主理人",
        "acceptance": "每条反馈可映射到模块/架构项",
    },
]

# —— 未来做（含 Wave★ 做强、缺失模块、网络/移动）——
FUTURE_TASKS: list[dict[str, str]] = [
    ("Wave★", "screenshot_tool", "截图做强", "Snipaste 级；钉图/放大镜", "mvp gaps 体验版不修"),
    ("Wave★", "clipboard_history", "剪贴板做强", "Ditto 级搜索持久", "mvp gaps 体验版不修"),
    ("Wave★", "quick_notepad", "记事做强", "热键互拷自动保存", "mvp gaps 体验版不修"),
    ("Wave★", "quadrant_tasks", "四象限做强", "拖拽逾期热键", "mvp gaps 体验版不修"),
    ("Wave★", "watermark_remover", "去水印 AI", "LaMa/IOPaint", "mvp gaps 体验版不修"),
    ("Wave★", "directory_generator", "建文件夹做强", "模板 DSL 点验标 done", "mvp gaps 体验版不修"),
    ("Wave★", "screenshot_translate", "截图翻译独立链", "挂工具栏已有一部分", "missing"),
    ("业务", "deliverable_directory_check", "TOA2 生成交付报告迁入", "Word贴图+Excel统计", "Top3 未 approved"),
    ("业务", "schedule_reminder", "日程提醒增强", "钉钉/邮件联动", "mvp"),
    ("业务", "column_preview", "MACOS桌面做强", "三模式点验", "mvp"),
    ("平台", "llm_assistant", "大模型 Wave", "八件套 done 后", "P1"),
    ("平台", "notifications", "通知持久化/未读", "顶栏铃铛增强", "mvp"),
    ("平台", "job_scheduler", "任务调度增强", "Top3 后", "mvp"),
    ("战略", "delivery_board", "培训交付看板", "垂直非 Jira", "评估"),
    ("战略", "mobile_companion", "移动伴侣", "通知/日程/剪贴板接力", "P2"),
    ("战略", "network_edition", "网络版", "配置同步+只读 DMS", "P2"),
    ("可选", "hostSwitch", "hosts 切换", "feature_pack 可选", "评估"),
    ("stub", "generic_generator", "通用生成 Excel 版", "对齐 TOA2 GUI", "stub"),
    ("stub", "pdf_toolkit", "PDF 工具", "合并拆分", "stub"),
    ("stub", "excel_cleaner", "Excel 清洗", "空行重复", "stub"),
]

PLATFORM_READY = [
    ("壳层", "MainShell", "三级导航·顶栏/侧栏/BasePage", "done"),
    ("壳层", "license/DMS", "桌面授权·激活·校验", "done"),
    ("壳层", "tray/hotkey", "托盘·全局热键·单实例", "done"),
    ("壳层", "notify_bus", "通知总线·状态栏/对话框/托盘", "done"),
    ("壳层", "runtime_paths", "冻结包路径·用户数据目录", "done"),
    ("壳层", "feature_packs", "能力包 SKU 配置", "done"),
    ("壳层", "integrations", "三方统一入口 integrations.yml", "done"),
    ("壳层", "packaging", "TOA3-Setup-v3.0.0.exe（待 VM 点验）", "待点验"),
    ("壳层", "command_palette", "Ctrl+K 命令面板", "done"),
]

CHANGELOG = [
    ("2026-08-27", "计划", "路线图三档：Ready / 眼下 / 未来；体验版发版导向"),
    ("2026-08-27", "packaging", "TOA3-Setup-v3.0.0.exe 构建链路"),
    ("2026-08-27", "协作", "腾讯文档协作表上线"),
]


def _load_manifest() -> dict:
    path = ROOT / "config" / "migration_manifest.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("modules") or {}


def _menu_by_id() -> dict[str, dict]:
    return {str(it.get("id") or ""): it for it in all_menu_items() if it.get("id")}


def _style_header(ws, headers: list[str], widths: list[int]) -> None:
    ws.append(headers)
    fill = PatternFill("solid", fgColor="1E3A8A")
    font = Font(bold=True, color="FFFFFF")
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.fill = fill
        c.font = font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _wrap_sheet(ws, max_row: int, max_col: int) -> None:
    for r in range(2, max_row + 1):
        for c in range(1, max_col + 1):
            ws.cell(row=r, column=c).alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"


def _sheet_overview(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "路线图总览"
    headers = ["档位", "含义", "数量/范围", "体验版策略", "本阶段纪律"]
    widths = [12, 22, 28, 36, 40]
    _style_header(ws, headers, widths)

    manifest = _load_manifest()
    done_n = sum(1 for v in manifest.values() if (v or {}).get("status") == "done")
    mvp_n = sum(1 for v in manifest.values() if (v or {}).get("status") == "mvp")
    missing_n = sum(1 for v in manifest.values() if (v or {}).get("status") in ("missing", "stub"))

    rows = [
        (
            "Ready·体验版",
            "manifest=done，可对外承诺",
            f"业务/平台模块 {done_n} 项 + 壳层底座",
            "小范围调研主推；写进体验版说明",
            "只修阻塞性 bug，不修体验 polish",
        ),
        (
            "眼下做",
            "系统·架构·发版",
            f"{len(NOW_TASKS)} 项（见「眼下做」Sheet）",
            "优先 VM 试装 + DMS draft + 菜单裁剪",
            "不做 Wave★ MVP 清 gaps",
        ),
        (
            "未来做",
            "Wave★ 做强 / 新模块 / 网络移动",
            f"约 {mvp_n} 项 mvp + {missing_n} 项缺失/stub",
            "调研反馈驱动排序，不抢先开发",
            "每项 Top3+三独到处后再写码",
        ),
        (
            "实验附带",
            "mvp 可用但未标 done",
            "可选开放给调研员「试用不承诺」",
            "菜单可隐藏或标「实验」",
            "明确不修小瑕疵",
        ),
    ]
    for i, row in enumerate(rows, 2):
        ws.append(list(row))
        tier = row[0]
        color = TIER_FILL.get(tier.split("·")[0] if "·" in tier else tier)
        if not color and "实验" in tier:
            color = TIER_FILL["实验附带"]
        if color:
            ws.cell(row=i, column=1).fill = PatternFill("solid", fgColor=color)
            ws.cell(row=i, column=1).font = Font(bold=True, color="FFFFFF")

    note_row = len(rows) + 3
    ws.cell(row=note_row, column=1).value = (
        f"在线协作：{COLLAB_SHEET_URL}  ·  "
        "主理人下一步：定体验版 Ready 白名单 → VM 试装 → DMS draft 体验版"
    )
    _wrap_sheet(ws, len(rows) + 1, len(headers))


def _sheet_ready(wb: Workbook) -> None:
    ws = wb.create_sheet("Ready体验版")
    headers = [
        "类型",
        "模块ID",
        "名称",
        "子模块",
        "需授权",
        "菜单可见",
        "说明",
        "体验版纳入",
    ]
    widths = [8, 22, 16, 12, 8, 8, 36, 10]
    _style_header(ws, headers, widths)

    manifest = _load_manifest()
    menus = _menu_by_id()
    row = 2

    for layer, mid, name, st in PLATFORM_READY:
        ws.append([layer, mid, name, "系统", "—", "—", st, "是"])
        ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="107C10")
        row += 1

    for mid, info in sorted(manifest.items()):
        if mid.startswith("__"):
            continue
        st = (info or {}).get("status") or ""
        if st != "done":
            continue
        menu = menus.get(mid, {})
        group = GROUP_LABELS.get(str(menu.get("group") or ""), "—")
        name = str(menu.get("name") or mid)
        desc = str((info or {}).get("note") or menu.get("desc") or "")
        lic = "是" if menu.get("requires_license") else "否"
        vis = "是" if menu.get("show", True) else "否"
        include = "是" if vis == "是" else "待定"
        ws.append(["功能", mid, name, group, lic, vis, desc[:120], include])
        ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="107C10")
        row += 1

    _wrap_sheet(ws, row - 1, len(headers))


def _sheet_experimental(wb: Workbook) -> None:
    """mvp 可选附带：体验版不修瑕疵，仅收反馈。"""
    ws = wb.create_sheet("实验附带mvp")
    headers = ["模块ID", "名称", "子模块", "manifest", "gaps摘要", "体验版建议"]
    widths = [22, 16, 12, 10, 48, 24]
    _style_header(ws, headers, widths)

    manifest = _load_manifest()
    menus = _menu_by_id()
    row = 2
    for mid, info in sorted(manifest.items()):
        if mid.startswith("__"):
            continue
        st = (info or {}).get("status") or ""
        if st != "mvp":
            continue
        menu = menus.get(mid, {})
        if not menu.get("show", True):
            continue
        gaps = "；".join(str(g) for g in ((info or {}).get("gaps") or [])[:2]) or "—"
        suggest = "默认隐藏" if mid in ("pomodoro", "image_creator", "web_workspace") else "可选开放·标实验"
        ws.append(
            [
                mid,
                str(menu.get("name") or mid),
                GROUP_LABELS.get(str(menu.get("group") or ""), "—"),
                status_label(st),
                gaps,
                suggest,
            ]
        )
        ws.cell(row=row, column=4).fill = PatternFill("solid", fgColor="F0A020")
        row += 1

    ws.cell(row=row + 1, column=1).value = "纪律：体验版阶段不排期修上表 gaps，仅记录调研意见。"
    _wrap_sheet(ws, row - 1, len(headers))


def _sheet_now(wb: Workbook) -> None:
    ws = wb.create_sheet("眼下做")
    headers = ["序", "领域", "任务", "目标", "下一步", "负责人", "验收"]
    widths = [5, 10, 28, 32, 28, 16, 36]
    _style_header(ws, headers, widths)
    for i, t in enumerate(NOW_TASKS, 2):
        ws.append(
            [
                t["seq"],
                t["area"],
                t["item"],
                t["goal"],
                t["next"],
                t["owner"],
                t["acceptance"],
            ]
        )
        ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor="2563EB")
        ws.cell(row=i, column=2).font = Font(bold=True, color="FFFFFF")
    _wrap_sheet(ws, len(NOW_TASKS) + 1, len(headers))


def _sheet_future(wb: Workbook) -> None:
    ws = wb.create_sheet("未来做")
    headers = ["分类", "模块ID", "任务", "目标", "状态/备注"]
    widths = [10, 22, 22, 32, 36]
    _style_header(ws, headers, widths)
    for i, row in enumerate(FUTURE_TASKS, 2):
        ws.append(list(row))
        ws.cell(row=i, column=1).fill = PatternFill("solid", fgColor="6B7280")
        ws.cell(row=i, column=1).font = Font(bold=True, color="FFFFFF")
    _wrap_sheet(ws, len(FUTURE_TASKS) + 1, len(headers))


def _sheet_changelog(wb: Workbook) -> None:
    ws = wb.create_sheet("更新记录")
    headers = ["日期", "范围", "摘要"]
    widths = [12, 14, 80]
    _style_header(ws, headers, widths)
    for date, scope, summary in CHANGELOG:
        ws.append([date, scope, summary])
    _wrap_sheet(ws, len(CHANGELOG) + 1, 3)


def _sheet_catalog(wb: Workbook) -> None:
    tmp = ROOT / "output" / "docs" / "_catalog_tmp.xlsx"
    _export_catalog_sheet(tmp)
    src = load_workbook(tmp)
    src_ws = src.active
    dst = wb.create_sheet("功能与场景")
    for row in src_ws.iter_rows(values_only=True):
        dst.append(list(row))
    for col, dim in src_ws.column_dimensions.items():
        dst.column_dimensions[col].width = dim.width or 12
    dst.freeze_panes = "A2"
    tmp.unlink(missing_ok=True)


def export_dev_workbook(out_path: Path | None = None) -> Path:
    ts = datetime.now().strftime("%Y%m%d")
    out_path = out_path or (ROOT / "output" / "docs" / f"TOA3-开发与功能手册-{ts}.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    _sheet_overview(wb)
    _sheet_ready(wb)
    _sheet_now(wb)
    _sheet_future(wb)
    _sheet_experimental(wb)
    _sheet_catalog(wb)
    _sheet_changelog(wb)
    wb.save(out_path)
    return out_path


def main() -> int:
    path = export_dev_workbook()
    print(f"已导出: {path}")
    print("（不写入 docs/；官方文档见 docs/README.md）")
    print(f"腾讯文档: {COLLAB_SHEET_URL}")
    print("  Sheet1 路线图总览")
    print("  Sheet2 Ready体验版 — 可发调研")
    print("  Sheet3 眼下做 — 系统/架构/发版（不修 MVP 小瑕疵）")
    print("  Sheet4 未来做 — Wave★/新模块/网络移动")
    print("  Sheet5 实验附带mvp — 可选试用不承诺")
    print("  Sheet6 功能与场景")
    print("  Sheet7 更新记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
