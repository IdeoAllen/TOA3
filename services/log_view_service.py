# -*- coding: utf-8 -*-
"""日志读取（设置页诊断区）。"""
from __future__ import annotations

from pathlib import Path

from services.system_info import log_directory


def log_file_path() -> Path:
    return log_directory() / "toa3.log"


def read_log_tail(max_lines: int = 400, max_bytes: int = 256_000) -> str:
    """读取日志文件末尾若干行（用于设置页预览）。"""
    path = log_file_path()
    if not path.is_file():
        return "（暂无日志文件）"

    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, 2)
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = ["…（仅显示末尾）…"] + lines[-max_lines:]
        return "\n".join(lines)
    except OSError as e:
        return f"无法读取日志：{e}"
