# -*- coding: utf-8 -*-
"""日志初始化（读取 log_config）。"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _parse_level(name: str) -> int:
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return mapping.get(str(name or "").upper(), logging.INFO)


def setup_logging(level: int | None = None) -> Path:
    from services.config_service import get_log_config, resolve_path

    log_cfg = get_log_config()
    if level is None:
        level = _parse_level(str(log_cfg.get("log_level") or "INFO"))

    log_dir = resolve_path("log_dir")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "toa3.log"

    fmt_text = str(
        log_cfg.get("log_format") or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    fmt = logging.Formatter(fmt_text, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    backup = int(log_cfg.get("max_log_files") or 5)
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=backup, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if log_cfg.get("enable_console_log", True):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    logging.getLogger("TOA3").info("日志目录: %s level=%s", log_dir, logging.getLevelName(level))
    # 壳 / WebEngine / 引擎导航诊断：一律跟全局 DEBUG
    for name in (
        "TOA3",
        "TOA3.shared_webengine",
        "TOA3.webengine_prewarm",
        "TOA3.local_web_engine",
        "app.shell",
        "app.module_loader",
        "core.error_handler",
    ):
        logging.getLogger(name).setLevel(level)
    logging.getLogger("TOA3.audit").setLevel(logging.INFO)
    return log_file
