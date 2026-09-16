# -*- coding: utf-8 -*-
"""助教招聘稿：解析班级名并套公司固定模板。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DEFAULT_DAILY_RATE = 150

# 固定话术（职责/着装等不可散装改写）
_FIXED_BODY = (
    "工作内容：新能源汽车培训助教\n"
    "1、  教室布置\n"
    "2、  学员签到\n"
    "3、  协助讲师进行课堂互动\n"
    "4、  拍摄课堂照片和视频素材\n"
    "5、  管理培训车辆\n"
    "6、  管理文具及教学物料\n"
    "要求：吃苦耐劳，积极主动，服从安排，及时回复消息，有责任心，"
    "需着商务装，女生长发扎马尾辫，化淡装"
)

_CLASS_RE = re.compile(
    r"^(?P<head>.+)-(?P<city>[^-]+)-(?P<start>\d{8})-(?P<end>\d{8})\s*$"
)

SAMPLE_CLASS_NAME = "销售主管岗位L1-成都-20260915-20260917"
SAMPLE_ADDRESS = "成都市高新区新园南一路2号成都三和阿维塔"


@dataclass(frozen=True)
class ParseResult:
    ok: bool
    class_name: str = ""
    course: str = ""
    city: str = ""
    start: date | None = None
    end: date | None = None
    days: int = 0
    message: str = ""


@dataclass(frozen=True)
class RecruitFields:
    city: str
    start_text: str
    end_text: str
    address: str
    days: int
    daily_rate: int
    fee: int


def _parse_yyyymmdd(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def format_cn_date(d: date) -> str:
    return f"{d.year}年{d.month}月{d.day}日"


def parse_class_name(class_name: str) -> ParseResult:
    text = (class_name or "").strip()
    if not text:
        return ParseResult(ok=False, message="请填写班级名称。")
    m = _CLASS_RE.match(text)
    if not m:
        return ParseResult(
            ok=False,
            class_name=text,
            message="班级名需符合「课程-城市-开始YYYYMMDD-结束YYYYMMDD」，可手工补字段后生成。",
        )
    start = _parse_yyyymmdd(m.group("start"))
    end = _parse_yyyymmdd(m.group("end"))
    if start is None or end is None:
        return ParseResult(
            ok=False,
            class_name=text,
            course=m.group("head").strip(),
            city=m.group("city").strip(),
            message="开始/结束日期无效，请检查 YYYYMMDD。",
        )
    if end < start:
        return ParseResult(
            ok=False,
            class_name=text,
            course=m.group("head").strip(),
            city=m.group("city").strip(),
            start=start,
            end=end,
            message="结束日期不能早于开始日期。",
        )
    days = (end - start).days + 1
    return ParseResult(
        ok=True,
        class_name=text,
        course=m.group("head").strip(),
        city=m.group("city").strip(),
        start=start,
        end=end,
        days=days,
    )


def compute_fee(days: int, daily_rate: int = DEFAULT_DAILY_RATE) -> int:
    d = max(0, int(days))
    rate = max(0, int(daily_rate))
    return d * rate


def render_recruit_post(fields: RecruitFields) -> str:
    city = (fields.city or "").strip()
    start_text = (fields.start_text or "").strip()
    end_text = (fields.end_text or "").strip()
    address = (fields.address or "").strip()
    days = max(0, int(fields.days))
    rate = max(0, int(fields.daily_rate))
    fee = max(0, int(fields.fee))
    if not city:
        raise ValueError("请填写城市。")
    if not start_text or not end_text:
        raise ValueError("请填写培训起止日期。")
    if not address:
        raise ValueError("请填写工作地址。")
    if days <= 0:
        raise ValueError("培训天数须大于 0。")

    lines = [
        f"【{city}】诚聘兼职助教",
        f"培训时间：{start_text}-{end_text}   8:00-18:30",
        f"地点：{address}",
        "工资：（不含餐）",
        "1、  布场50（培训前一天下午大约3个小时）",
        f"2、  培训{days}天执行费用{fee}（{rate}一天）",
        _FIXED_BODY,
    ]
    return "\n".join(lines)


def fixed_body_text() -> str:
    """供 UI 展示不可改写的固定段。"""
    return _FIXED_BODY


def save_recruit_txt(
    text: str,
    *,
    out_dir: Path,
    city: str = "",
    start_text: str = "",
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    city_part = re.sub(r'[\\/:*?"<>|]+', "_", (city or "招聘").strip()) or "招聘"
    date_part = re.sub(r"\D+", "", start_text or "")[:8] or datetime.now().strftime("%Y%m%d")
    path = out_dir / f"助教招聘稿_{city_part}_{date_part}.txt"
    path.write_text(text, encoding="utf-8")
    return path
