# -*- coding: utf-8 -*-
"""Harness web profile 配置版本：快照 / 恢复上次可用（插件搞挂时可一键回退）。"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("TOA3.harness_profile_versions")

_PROFILE_FILES = ("package.json", "cordis.yml", "cordis.patch.yml", "pnpm-workspace.yaml")


def _snapshots_root() -> Path:
    from services.storage_paths import module_data_dir

    d = module_data_dir("harness_agent", create=True) / "profile_snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pointer_path() -> Path:
    return _snapshots_root() / "last_good.json"


def _web_profile_dir(home: Path | None = None) -> Path:
    from services.harness_plugins import profile_dir_for

    if home is None:
        from services.harness_config import dsh_home_path

        home = dsh_home_path()
    return profile_dir_for(Path(home))


def _dsh_core_version() -> str:
    try:
        from services.harness_config import dsh_bin_path

        dsh = dsh_bin_path()
        pkg = dsh.resolve().parent.parent / "package.json"
        if pkg.is_file():
            data = json.loads(pkg.read_text(encoding="utf-8"))
            return str(data.get("version") or "").strip()
    except Exception:
        pass
    return ""


def list_snapshots() -> list[dict[str, Any]]:
    root = _snapshots_root()
    out: list[dict[str, Any]] = []
    try:
        dirs = sorted(
            [p for p in root.iterdir() if p.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return []
    last_id = ""
    try:
        if _pointer_path().is_file():
            last_id = str(json.loads(_pointer_path().read_text(encoding="utf-8")).get("id") or "")
    except (json.JSONDecodeError, OSError):
        pass
    for d in dirs[:30]:
        meta_path = d / "meta.json"
        meta: dict[str, Any] = {"id": d.name, "path": str(d)}
        if meta_path.is_file():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        meta["is_last_good"] = d.name == last_id
        out.append(meta)
    return out


def snapshot_web_profile(
    *,
    reason: str = "manual",
    mark_good: bool = False,
    home: Path | None = None,
) -> tuple[bool, str, Path | None]:
    """备份当前 web profile 关键文件。"""
    src = _web_profile_dir(home)
    if not src.is_dir():
        return False, f"无 web profile 目录：{src}", None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = _snapshots_root() / stamp
    try:
        dest.mkdir(parents=True, exist_ok=False)
        copied = 0
        for name in _PROFILE_FILES:
            f = src / name
            if f.is_file():
                shutil.copy2(f, dest / name)
                copied += 1
        if copied == 0:
            shutil.rmtree(dest, ignore_errors=True)
            return False, "profile 下无可备份文件", None
        meta = {
            "id": stamp,
            "reason": reason,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "dsh_version": _dsh_core_version(),
            "mark_good": bool(mark_good),
            "files": [n for n in _PROFILE_FILES if (dest / n).is_file()],
        }
        (dest / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if mark_good:
            _pointer_path().write_text(
                json.dumps({"id": stamp, "updated_at": meta["created_at"]}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
        tip = f"已备份配置 {stamp}"
        if mark_good:
            tip += "（标为上次可用）"
        return True, tip, dest
    except OSError as exc:
        logger.exception("snapshot failed")
        return False, f"备份失败：{exc}", None


def mark_snapshot_good(snapshot_id: str) -> tuple[bool, str]:
    sid = str(snapshot_id or "").strip()
    dest = _snapshots_root() / sid
    if not dest.is_dir():
        return False, "快照不存在"
    _pointer_path().write_text(
        json.dumps(
            {"id": sid, "updated_at": datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return True, f"已将 {sid} 标为上次可用"


def restore_snapshot(snapshot_id: str, *, home: Path | None = None) -> tuple[bool, str]:
    """用某次快照覆盖当前 web profile（不碰 node_modules）。"""
    sid = str(snapshot_id or "").strip()
    src = _snapshots_root() / sid
    if not src.is_dir():
        return False, "快照不存在"
    dest = _web_profile_dir(home)
    try:
        dest.mkdir(parents=True, exist_ok=True)
        # 恢复前先再拍一版，便于反悔
        snapshot_web_profile(reason="pre_restore", mark_good=False, home=home)
        n = 0
        for name in _PROFILE_FILES:
            f = src / name
            if f.is_file():
                shutil.copy2(f, dest / name)
                n += 1
        if n == 0:
            return False, "快照内无配置文件"
        return True, f"已恢复配置 {sid}（请重启服务）"
    except OSError as exc:
        return False, f"恢复失败：{exc}"


def restore_last_good(*, home: Path | None = None) -> tuple[bool, str]:
    if not _pointer_path().is_file():
        # 退化：取最近一次快照
        snaps = list_snapshots()
        if not snaps:
            return False, "尚无「上次可用」备份。请先在正常可开时点「备份当前配置」。"
        return restore_snapshot(str(snaps[0].get("id") or ""), home=home)
    try:
        data = json.loads(_pointer_path().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"读取上次可用指针失败：{exc}"
    sid = str(data.get("id") or "").strip()
    if not sid:
        return False, "上次可用指针无效"
    return restore_snapshot(sid, home=home)


def ensure_baseline_snapshot(*, home: Path | None = None) -> None:
    """若还没有任何快照，在修复/启动前尽量留一份当前配置。"""
    if list_snapshots():
        return
    snapshot_web_profile(reason="baseline", mark_good=False, home=home)


def maybe_snapshot_after_healthy(
    *,
    home: Path | None = None,
    min_interval_sec: float = 3600.0,
) -> tuple[bool, str]:
    """HTTP 就绪后节流拍「上次可用」：证明当前配置能开，搞挂可回退。"""
    ptr = _pointer_path()
    if ptr.is_file():
        try:
            data = json.loads(ptr.read_text(encoding="utf-8"))
            updated = str(data.get("updated_at") or "")
            if updated:
                ts = datetime.fromisoformat(updated)
                age = (datetime.now() - ts).total_seconds()
                if age < float(min_interval_sec):
                    return False, "跳过：距上次可用快照过近"
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    ok, msg, _ = snapshot_web_profile(reason="healthy", mark_good=True, home=home)
    return ok, msg
