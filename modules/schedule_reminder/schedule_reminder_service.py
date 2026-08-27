# -*- coding: utf-8 -*-
"""班级日程五场景：从课表 Excel 筛选布置场地 / 签到 / 物流 / 本周 / 下周。"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir, module_output_dir

logger = logging.getLogger("TOA3.schedule_reminder")

SCENE_DEFS = [
    ("venue", "布置场地", "明天开始的课程"),
    ("checkin", "课程签到", "今天进行中的课程"),
    ("logistics", "物流订单", "今天结束的课程"),
    ("this_week", "本周课程", "本周开始的课程"),
    ("next_week", "下周课程", "下周开始的课程"),
]

KEY_COLUMNS = [
    "城市",
    "班级名称",
    "开始时间",
    "结束时间",
    "大运营",
    "助教联系方式",
    "收货人及地址",
]

DATA_FILENAME = "real_data.xlsx"


@dataclass
class SceneResult:
    scene_id: str
    title: str
    columns: list[str]
    rows: list[list[Any]]
    message: str = ""

    @property
    def empty(self) -> bool:
        return not self.rows


def data_file_path() -> Path:
    return module_data_dir("schedule_reminder", create=True) / DATA_FILENAME


def load_schedule_source(src: str | Path) -> Path:
    """复制用户选择的课表到模块数据目录。"""
    path = Path(src)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    dest = data_file_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def _safe_read_excel(path: Path):
    import pandas as pd

    try:
        return pd.read_excel(path)
    except Exception:
        try:
            return pd.read_excel(path, engine="calamine")
        except Exception:
            pass
        try:
            import openpyxl

            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.values)
            if not rows:
                return pd.DataFrame()
            header = [str(h) if h is not None else f"列{i+1}" for i, h in enumerate(rows[0])]
            return pd.DataFrame(rows[1:], columns=header)
        except Exception as exc:
            logger.exception("读取课表失败")
            raise ValueError(f"无法读取 Excel：{exc}") from exc


def _apply_column_aliases(df):
    aliases = {
        "开始时间": ["开课时间", "开始日期", "开始", "课程开始时间", "上课开始时间"],
        "结束时间": ["结课时间", "结束日期", "结束", "课程结束时间", "上课结束时间"],
        "课程状态": ["状态", "课程状态(在读/结束)"],
    }
    for std, cands in aliases.items():
        if std not in df.columns:
            for a in cands:
                if a in df.columns:
                    df.rename(columns={a: std}, inplace=True)
                    break


def _excel_serial_to_ts(x, pd):
    try:
        val = float(x)
    except Exception:
        return pd.NaT
    if 30000 <= val <= 60000:
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=val)
    return pd.NaT


def _coerce_datetime_columns(df, cols):
    import pandas as pd

    for col in cols:
        if col not in df.columns:
            continue
        s = df[col]
        dt = pd.to_datetime(s, errors="coerce")
        mask = dt.isna()
        if mask.any():
            dt2 = s.apply(lambda x: _excel_serial_to_ts(x, pd))
            dt = dt.where(~mask, dt2)
        df[col] = dt


def _exclude_cancelled(df, filtered):
    if "课程状态" in df.columns:
        return filtered[filtered["课程状态"] != "取消"]
    return filtered


def _format_cell(col: str, val: Any) -> str:
    if val is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(val):
            return ""
        if isinstance(val, (pd.Timestamp, datetime)):
            return val.strftime("%Y-%m-%d")
    except Exception:
        pass
    s = str(val).strip()
    if col == "收货人及地址" and "地址" in s:
        parts = s.split("地址", 1)
        return (parts[0].rstrip("：:") + "\n地址" + parts[1]).strip()
    return s


def _to_scene_rows(filtered) -> tuple[list[str], list[list[Any]]]:
    existing = [c for c in KEY_COLUMNS if c in filtered.columns]
    columns = ["序号"] + existing
    rows: list[list[Any]] = []
    for i, (_, row) in enumerate(filtered.iterrows(), 1):
        values = [i] + [_format_cell(c, row[c]) for c in existing]
        rows.append(values)
    return columns, rows


def _load_prepared_df(path: Path | None = None):
    import pandas as pd

    src = path or data_file_path()
    if not src.is_file():
        return None, "数据文件不存在，请先加载课表 Excel。"
    df = _safe_read_excel(src)
    if df is None or df.empty:
        return None, "Excel 为空或无法读取。"
    df.columns = df.columns.astype(str).str.strip()
    _apply_column_aliases(df)
    _coerce_datetime_columns(df, ["开始时间", "结束时间"])
    return df, ""


def query_scene(scene_id: str, path: Path | None = None) -> SceneResult:
    import pandas as pd

    meta = {s[0]: s for s in SCENE_DEFS}
    if scene_id not in meta:
        raise ValueError(f"未知场景: {scene_id}")
    _, title, empty_msg = meta[scene_id]

    df, err = _load_prepared_df(path)
    if df is None:
        return SceneResult(scene_id, title, ["提示"], [[err]], message=err)

    today = pd.Timestamp.now().normalize()

    if scene_id == "venue":
        if "开始时间" not in df.columns:
            return SceneResult(scene_id, title, ["提示"], [["缺少「开始时间」列"]], message="缺少开始时间")
        tomorrow = today + pd.Timedelta(days=1)
        filtered = df[df["开始时间"].dt.normalize() == tomorrow]
        filtered = _exclude_cancelled(df, filtered).sort_values(by="开始时间")
        empty_hint = "没有找到明天开始的课程"
    elif scene_id == "checkin":
        if "开始时间" not in df.columns or "结束时间" not in df.columns:
            return SceneResult(
                scene_id, title, ["提示"], [["缺少「开始时间」或「结束时间」列"]], message="缺列"
            )
        filtered = df[
            (df["开始时间"].dt.normalize() <= today) & (df["结束时间"].dt.normalize() >= today)
        ]
        filtered = _exclude_cancelled(df, filtered).sort_values(by="开始时间")
        empty_hint = "今天没有进行中的课程"
    elif scene_id == "logistics":
        if "结束时间" not in df.columns:
            return SceneResult(scene_id, title, ["提示"], [["缺少「结束时间」列"]], message="缺列")
        filtered = df[df["结束时间"].dt.normalize() == today]
        filtered = _exclude_cancelled(df, filtered)
        if "开始时间" in filtered.columns:
            filtered = filtered.sort_values(by="开始时间")
        empty_hint = "今天没有结束的课程"
    elif scene_id == "this_week":
        if "开始时间" not in df.columns:
            return SceneResult(scene_id, title, ["提示"], [["缺少「开始时间」列"]], message="缺列")
        start = today - pd.Timedelta(days=int(today.dayofweek))
        end = start + pd.Timedelta(days=6)
        filtered = df[
            (df["开始时间"].dt.normalize() >= start) & (df["开始时间"].dt.normalize() <= end)
        ]
        filtered = _exclude_cancelled(df, filtered).sort_values(by="开始时间")
        empty_hint = "本周没有开始的课程"
    else:  # next_week
        if "开始时间" not in df.columns:
            return SceneResult(scene_id, title, ["提示"], [["缺少「开始时间」列"]], message="缺列")
        start_week = today - pd.Timedelta(days=int(today.dayofweek))
        start = start_week + pd.Timedelta(days=7)
        end = start + pd.Timedelta(days=6)
        filtered = df[
            (df["开始时间"].dt.normalize() >= start) & (df["开始时间"].dt.normalize() <= end)
        ]
        filtered = _exclude_cancelled(df, filtered).sort_values(by="开始时间")
        empty_hint = "下周没有开始的课程"

    if filtered.empty:
        return SceneResult(scene_id, title, ["提示"], [[empty_hint]], message=empty_hint)

    columns, rows = _to_scene_rows(filtered)
    return SceneResult(scene_id, title, columns, rows)


def query_all_scenes(path: Path | None = None) -> dict[str, SceneResult]:
    return {sid: query_scene(sid, path) for sid, _, _ in SCENE_DEFS}


def export_scene_xlsx(result: SceneResult, out_dir: str | Path | None = None) -> Path:
    import pandas as pd

    from services.excel_export import dataframe_to_xlsx

    if not result.rows or (len(result.columns) == 1 and result.columns[0] == "提示"):
        raise ValueError("无数据可导出")
    root = Path(out_dir) if out_dir else module_output_dir("schedule_reminder", create=True)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = root / f"场景_{result.title}_{stamp}.xlsx"
    df = pd.DataFrame(result.rows, columns=result.columns)
    return dataframe_to_xlsx(df, dest, sheet_name="结果")


def export_all_scenes_xlsx(
    results: dict[str, SceneResult] | None = None,
    out_dir: str | Path | None = None,
) -> Path:
    import pandas as pd

    from services.excel_export import finalize_excel_writer

    results = results or query_all_scenes()
    root = Path(out_dir) if out_dir else module_output_dir("schedule_reminder", create=True)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = root / f"五场景课表_{stamp}.xlsx"
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        wrote = 0
        for sid, _, _ in SCENE_DEFS:
            r = results.get(sid) or query_scene(sid)
            if not r.rows or (len(r.columns) == 1 and r.columns[0] == "提示"):
                continue
            sheet = r.title[:31]
            pd.DataFrame(r.rows, columns=r.columns).to_excel(writer, index=False, sheet_name=sheet)
            wrote += 1
        if wrote == 0:
            pd.DataFrame([["无数据"]]).to_excel(writer, index=False, header=False, sheet_name="空")
        finalize_excel_writer(writer)
    return dest
