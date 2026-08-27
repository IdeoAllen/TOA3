# -*- coding: utf-8 -*-
"""排程格式转换服务：TOA2 引擎门面 + 开班信息确认表适配 + CSV 轻量回退。"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules.schedule_format_converter.toa2_engine import ScheduleFormatConverter
from services.storage_paths import module_output_dir

MODULE_ID = "schedule_format_converter"

# 「开班信息确认表」表头别名
_OPEN_HEADERS = {
    "课程名称": ("课程名称", "课程名", "原课程名"),
    "开始日期": ("开始日期", "开始", "开班日期"),
    "结束日期": ("结束日期", "结束", "结课日期"),
    "班级名称": ("班级名称", "班级"),
    "授课老师": ("授课老师", "老师", "讲师"),
    "培训场地": ("培训场地", "场地", "门店"),
    "城市": ("城市（拆分）", "城市", "城市拆分"),
    "课程拆分": ("课程（拆分）", "课程拆分"),
    "期数": ("期数（拆分）", "期数"),
}


@dataclass
class ConvertResult:
    ok: bool
    message: str
    output_path: Path | None = None
    schedule_data: list[dict[str, Any]] = field(default_factory=list)
    summary_data: list[dict[str, Any]] = field(default_factory=list)
    course_stats: dict[str, Any] = field(default_factory=dict)


def _normalize_cell(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if text.lower() == "nan":
        return ""
    return text


def sheet_to_csv(src: str | Path, dest: str | Path | None = None) -> Path:
    """读取 Excel/CSV 首表，规范化单元格后写出 CSV（轻量回退）。"""
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"文件不存在: {src_path}")

    if dest is None:
        dest = src_path.with_name(f"{src_path.stem}_normalized.csv")
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    rows = _load_rows(src_path)
    normalized = [[_normalize_cell(c) for c in row] for row in rows]
    normalized = [r for r in normalized if any(c for c in r)]

    with dest_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(normalized)
    return dest_path


def _load_rows(path: Path) -> list[list[object]]:
    ext = path.suffix.lower()
    if ext == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [list(row) for row in csv.reader(f)]

    try:
        import pandas as pd

        df = pd.read_excel(path, header=None, dtype=object)
        return df.fillna("").values.tolist()
    except ImportError:
        pass
    except Exception:
        pass

    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = [list(row) for row in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    except ImportError as e:
        raise RuntimeError("需要 pandas 或 openpyxl 才能读取 Excel；也可改用 CSV。") from e


def _header_map(headers: list[str]) -> dict[str, int]:
    cleaned = [_normalize_cell(h) for h in headers]
    found: dict[str, int] = {}
    for key, aliases in _OPEN_HEADERS.items():
        for i, h in enumerate(cleaned):
            if h in aliases:
                found[key] = i
                break
    return found


def _looks_like_open_confirm_headers(headers: list[object]) -> bool:
    m = _header_map([_normalize_cell(h) for h in headers])
    return "课程名称" in m and "开始日期" in m and "结束日期" in m


def detect_open_class_confirm_sheet(path: Path) -> str | None:
    """若为开班信息确认表，返回应用的工作表名。"""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            preferred = ["开班信息", "开班信息确认", "开班确认"]
            for name in preferred:
                if name in wb.sheetnames:
                    ws = wb[name]
                    row1 = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
                    if row1 and _looks_like_open_confirm_headers(list(row1)):
                        return name
            for name in wb.sheetnames:
                ws = wb[name]
                row1 = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
                if row1 and _looks_like_open_confirm_headers(list(row1)):
                    return name
        finally:
            wb.close()
    except Exception:
        return None
    return None


def _parse_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _normalize_cell(value).replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    try:
        import pandas as pd

        ts = pd.to_datetime(value, errors="coerce")
        if ts is not None and not pd.isna(ts):
            return ts.date()
    except Exception:
        pass
    return None


def _project_belonging(course_text: str) -> str:
    t = course_text or ""
    if "低绩效" in t or "认证" in t:
        return "破晓突击"
    return "利刃出鞘"


def _city_from_row(city_cell: object, class_name: str) -> str:
    city = _normalize_cell(city_cell)
    if city:
        return city
    cn = class_name or ""
    if "-" in cn:
        return cn.split("-", 1)[0].strip()
    return ""


def parse_open_class_confirm(
    path: Path,
    year: int,
    month: int,
    *,
    sheet_name: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """开班信息确认表 → schedule_data + course_stats。"""
    import pandas as pd

    sheet = sheet_name or detect_open_class_confirm_sheet(path)
    if not sheet:
        raise ValueError("未识别到开班信息确认表")

    df = pd.read_excel(path, sheet_name=sheet, dtype=object)
    headers = [str(c) for c in df.columns.tolist()]
    colmap = _header_map(headers)
    if "课程名称" not in colmap or "开始日期" not in colmap or "结束日期" not in colmap:
        raise ValueError(f"工作表「{sheet}」缺少必要列（课程名称/开始日期/结束日期）")

    def cell(row, key: str) -> object:
        idx = colmap.get(key)
        if idx is None:
            return ""
        name = headers[idx]
        return row.get(name)

    schedule: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "total": 0,
        "破晓突击课程": 0,
        "利刃出鞘课程": 0,
        "销售顾问课程": 0,
        "source": f"开班信息确认表/{sheet}",
    }

    for _, row in df.iterrows():
        original = _normalize_cell(cell(row, "课程名称"))
        if not original or original == "课程名称":
            continue
        start_d = _parse_date(cell(row, "开始日期"))
        end_d = _parse_date(cell(row, "结束日期"))
        if start_d is None or end_d is None:
            continue
        if start_d.year != int(year) or start_d.month != int(month):
            continue

        class_name = _normalize_cell(cell(row, "班级名称"))
        course_name = _normalize_cell(cell(row, "课程拆分")) or original
        theater = _normalize_cell(cell(row, "培训场地")) or "—"
        city = _city_from_row(cell(row, "城市"), class_name)
        if not city:
            continue

        days = max(1, (end_d - start_d).days + 1)
        belonging = _project_belonging(original)
        schedule.append(
            {
                "course_name": course_name,
                "city": city,
                "theater": theater,
                "start_date": start_d.strftime("%Y/%m/%d"),
                "end_date": end_d.strftime("%Y/%m/%d"),
                "project_belonging": belonging,
                "course_days": days,
                "original_course_name": original,
                "class_name": class_name,
                "teacher": _normalize_cell(cell(row, "授课老师")),
            }
        )
        stats["total"] += 1
        if belonging == "破晓突击":
            stats["破晓突击课程"] += 1
        else:
            stats["利刃出鞘课程"] += 1
        if "销售顾问" in original or "销售顾问" in course_name:
            stats["销售顾问课程"] += 1

    schedule.sort(key=lambda x: (x["start_date"], x["city"], x["course_name"]))
    return schedule, stats


def convert_open_class_confirm_to_teaching_plan(
    src: str | Path,
    year: int,
    month: int,
    *,
    dest: str | Path | None = None,
) -> ConvertResult:
    src_path = Path(src)
    try:
        sheet = detect_open_class_confirm_sheet(src_path)
        if not sheet:
            return ConvertResult(ok=False, message="不是开班信息确认表格式")
        schedule, stats = parse_open_class_confirm(src_path, year, month, sheet_name=sheet)
    except Exception as exc:
        return ConvertResult(ok=False, message=f"解析开班信息确认表失败: {exc}")

    if not schedule:
        return ConvertResult(
            ok=False,
            message=f"在 {year}年{month:02d}月 未解析到课程（请核对年份/月份与表内开始日期）",
            course_stats=stats,
        )

    tool = ScheduleFormatConverter()
    tool.set_year_month(int(year), int(month))
    tool.schedule_data = schedule
    tool.course_stats = stats
    tool._generate_summary_data()

    out_dir = module_output_dir(MODULE_ID, create=True)
    out_path = (
        Path(dest) if dest else out_dir / f"{src_path.stem}_教学计划_{year}{month:02d}.xlsx"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ok_export, export_msg = tool.export_to_excel(str(out_path))
    if not ok_export:
        return ConvertResult(
            ok=False,
            message=export_msg,
            schedule_data=schedule,
            summary_data=list(tool.get_summary_data() or []),
            course_stats=stats,
        )
    return ConvertResult(
        ok=True,
        message=(
            f"已按「开班信息确认表 / {sheet}」解析 {len(schedule)} 条课程"
            f"（{year}-{month:02d}）\n已导出: {out_path}"
        ),
        output_path=out_path,
        schedule_data=schedule,
        summary_data=list(tool.get_summary_data() or []),
        course_stats=stats,
    )


def convert_schedule_to_teaching_plan(
    src: str | Path,
    year: int,
    month: int,
    *,
    dest: str | Path | None = None,
) -> ConvertResult:
    """排期 → 教学计划 xlsx（自动识别：开班信息确认表 / 合并单元格排期）。"""
    src_path = Path(src)
    if not src_path.is_file():
        return ConvertResult(ok=False, message=f"文件不存在: {src_path}")

    if detect_open_class_confirm_sheet(src_path):
        return convert_open_class_confirm_to_teaching_plan(src_path, year, month, dest=dest)

    tool = ScheduleFormatConverter()
    ok, message = tool.convert_schedule(str(src_path), int(year), int(month))
    if not ok:
        return ConvertResult(ok=False, message=message)

    out_dir = module_output_dir(MODULE_ID, create=True)
    out_path = (
        Path(dest) if dest else out_dir / f"{src_path.stem}_教学计划_{year}{month:02d}.xlsx"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ok_export, export_msg = tool.export_to_excel(str(out_path))
    if not ok_export:
        return ConvertResult(
            ok=False,
            message=export_msg,
            schedule_data=list(tool.get_schedule_data() or []),
            summary_data=list(tool.get_summary_data() or []),
            course_stats=dict(tool.get_course_stats() or {}),
        )
    return ConvertResult(
        ok=True,
        message=f"{message}\n已导出: {out_path}",
        output_path=out_path,
        schedule_data=list(tool.get_schedule_data() or []),
        summary_data=list(tool.get_summary_data() or []),
        course_stats=dict(tool.get_course_stats() or {}),
    )


def generate_schedule_from_teaching_plan(
    teaching_plan: str | Path,
    *,
    dest: str | Path | None = None,
) -> ConvertResult:
    """教学计划 → 排期 xlsx。"""
    src_path = Path(teaching_plan)
    if not src_path.is_file():
        return ConvertResult(ok=False, message=f"文件不存在: {src_path}")

    out_dir = module_output_dir(MODULE_ID, create=True)
    out_path = Path(dest) if dest else out_dir / f"{src_path.stem}_排期.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tool = ScheduleFormatConverter()
    ok, message, validation = tool.generate_schedule_from_teaching_plan(
        str(src_path),
        str(out_path),
    )
    extra = ""
    if isinstance(validation, dict) and validation.get("message"):
        extra = f"\n验证: {validation.get('message')}"
    return ConvertResult(
        ok=bool(ok),
        message=f"{message}{extra}",
        output_path=out_path if ok else None,
    )
