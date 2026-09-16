# -*- coding: utf-8 -*-
"""引擎管家生命周期：日志 / 卸载 / 备份 / 修复（本地 Web；Harness 委托现有服务）。"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("TOA3.engine_host.lifecycle")


def log_path_for(engine_id: str) -> Path | None:
    eid = str(engine_id or "").strip()
    if not eid:
        return None
    if eid == "harness_agent":
        try:
            from services.harness_sidecar import sidecar_log_path

            return sidecar_log_path()
        except Exception:
            try:
                from services.storage_paths import module_output_dir

                return module_output_dir("harness_agent")
            except Exception:
                return None
    try:
        from services.storage_paths import module_data_dir

        p = module_data_dir("local_web_engine", create=True) / "logs" / f"{eid}.log"
        return p
    except Exception:
        return None


def open_log(engine_id: str) -> tuple[bool, str, Path | None]:
    path = log_path_for(engine_id)
    if path is None:
        return False, "无日志路径", None
    if path.is_file():
        return True, "已定位日志文件", path
    if path.is_dir():
        return True, "已定位日志目录", path
    # 文件尚未生成：仍返回父目录
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    return True, "日志尚未生成，已打开目录", parent


def backup_dir() -> Path:
    from services.storage_paths import module_data_dir

    d = module_data_dir("engine_host_hub", create=True) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup_engine(engine_id: str) -> tuple[bool, str, Path | None]:
    """快照安装根目录（大目录可能较慢；后台调用方应在线程中跑）。"""
    eid = str(engine_id or "").strip()
    if eid == "harness_agent":
        try:
            from services.harness_setup import default_install_root, discover_runtime

            rt = discover_runtime()
            root = Path(rt["home"]) if rt.get("home") else default_install_root()
        except Exception as exc:
            return False, f"无法定位 Harness 目录：{exc}", None
    else:
        from services.local_web_engine import discover_root

        root = discover_root(eid)
        if root is None:
            return False, "未安装，无法备份", None
    if not root.exists():
        return False, f"目录不存在：{root}", None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir() / eid / stamp
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root, dest, dirs_exist_ok=False)
        return True, f"已备份到 {dest}", dest
    except Exception as exc:
        logger.exception("backup failed %s", eid)
        return False, f"备份失败：{exc}", None


def repair_engine(engine_id: str) -> tuple[bool, str]:
    eid = str(engine_id or "").strip()
    if eid == "harness_agent":
        from services.harness_setup import repair_harness_runtime

        return repair_harness_runtime()
    from services.local_web_engine import stop_engine
    from services.local_web_engine.install import can_one_click_install, install_engine

    stop_engine(eid)
    if can_one_click_install(eid):
        ok, msg = install_engine(eid)
        return ok, msg if ok else f"修复安装失败：{msg}"
    return (
        False,
        "该引擎无自动修复脚本。请「打开日志」查看端口占用，或「指定目录」后重启。",
    )


def uninstall_engine(engine_id: str, *, delete_files: bool = False) -> tuple[bool, str]:
    """停进程 + 清除用户登记根；可选删除安装目录。"""
    eid = str(engine_id or "").strip()
    if eid == "harness_agent":
        try:
            from services import harness_sidecar

            harness_sidecar.stop(force=True)
        except Exception as exc:
            logger.warning("stop harness: %s", exc)
        if delete_files:
            try:
                from services.harness_setup import default_install_root, discover_runtime

                rt = discover_runtime()
                root = Path(rt["home"]) if rt.get("home") else default_install_root()
                if root.exists():
                    shutil.rmtree(root, ignore_errors=True)
            except Exception as exc:
                return False, f"已停止服务，但删除目录失败：{exc}"
        return True, "已卸载 Harness 运行登记（服务已停）"

    from services import local_web_engine as lwe

    lwe.stop_engine(eid)
    root = lwe.discover_root(eid)
    try:
        import yaml

        path = lwe._user_cfg_path()  # noqa: SLF001 — Hub 清除用户根登记
        data: dict = {}
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        roots = dict(data.get("roots") or {})
        roots.pop(eid, None)
        data["roots"] = roots
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        lwe._USER_ROOTS.pop(eid, None)  # noqa: SLF001
        lwe.load_specs(force=True)
    except Exception as exc:
        logger.warning("clear user root %s: %s", eid, exc)

    if delete_files and root is not None and root.exists():
        try:
            shutil.rmtree(root, ignore_errors=False)
        except Exception as exc:
            return False, f"已停止并清除登记，但删除文件失败：{exc}"
        return True, "已卸载并删除安装目录"
    return True, "已停止并清除本机登记（安装文件保留）"
