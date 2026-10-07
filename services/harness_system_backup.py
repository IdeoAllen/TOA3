# -*- coding: utf-8 -*-
"""Harness 系统备份：升级前整树快照，升坏了可回滚。

与 profile_snapshots（仅 web 配置）互补：本模块备份安装根 + 会话家目录关键态。
默认保留最近 KEEP_GENERATIONS 代；大目录会跳过可重建的 profile node_modules。
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("TOA3.harness_system_backup")

KEEP_GENERATIONS = 3

# 相对安装根的忽略名（任意层级命中则跳过）
_SKIP_DIR_NAMES = frozenset(
    {
        ".cache",
        "Cache",
        "__pycache__",
        ".pnpm-store",
    }
)

# 安装根下可从 CDN 重建的大目录：升级前备份不必整树复制（否则数百 MB 像卡死）
_SKIP_AT_INSTALL_ROOT = frozenset(
    {
        "node_modules",
        "node",
    }
)


def _backups_root() -> Path:
    from services.storage_paths import module_data_dir

    d = module_data_dir("harness_agent", create=True) / "system_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_backup_dir() -> Path:
    return _backups_root()


def _install_root() -> Path:
    from services.harness_setup import default_install_root

    return default_install_root()


def read_installed_dsh_core_version(install_root: Path | None = None) -> str:
    """读本机 node_modules 里真实 dsh 内核版本（可与 MANIFEST / 钉扎漂移）。"""
    root = Path(install_root) if install_root is not None else _install_root()
    pkg = root / "node_modules" / "@deepseek-ai" / "dsh" / "package.json"
    if not pkg.is_file():
        return ""
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        return str(data.get("version") or "").strip()
    except (OSError, json.JSONDecodeError):
        return ""


def version_info(install_root: Path | None = None) -> dict[str, Any]:
    """页内展示用：本机程序包 / 内核 / 配置钉扎 / 是否漂移。"""
    from services.harness_prefab import FLAVOR_LABELS, normalize_flavor, read_installed_manifest
    from services.harness_setup import DSH_PINNED_VERSION
    from services.harness_config import load_harness_config

    root = Path(install_root) if install_root is not None else _install_root()
    manifest = read_installed_manifest(root) if root.is_dir() else {}
    flavor = normalize_flavor(str(manifest.get("flavor") or "prefab"))
    cfg = load_harness_config()
    pin_key = "prefab_bundle_version" if flavor == "prefab" else "official_bundle_version"
    pinned_bundle = str(cfg.get(pin_key) or "").strip()
    installed_bundle = str(manifest.get("version") or "").strip()
    core = read_installed_dsh_core_version(root)
    # 代码钉扎为真相源（MANIFEST.dsh_pinned 仅记录上次升核结果，不得拖住升级提示）
    pinned_core = DSH_PINNED_VERSION
    core_drift = bool(core and pinned_core and core != pinned_core)
    bundle_drift = bool(
        installed_bundle and pinned_bundle and installed_bundle != pinned_bundle
    )
    return {
        "install_root": str(root),
        "installed": root.is_dir(),
        "flavor": flavor,
        "flavor_label": FLAVOR_LABELS.get(flavor, flavor),
        "installed_bundle": installed_bundle or "(未装)",
        "pinned_bundle": pinned_bundle or "(未配置)",
        "dsh_core": core or "(未知)",
        "dsh_pinned": pinned_core,
        "core_drift": core_drift,
        "bundle_drift": bundle_drift,
        "needs_repin": core_drift or bundle_drift,
    }


def _copytree_filtered(src: Path, dst: Path, progress: Callable[[str], None] | None) -> None:
    src_root = src.resolve()

    def _ignore(directory: str, names: list[str]) -> set[str]:
        skip: set[str] = set()
        p = Path(directory)
        try:
            at_root = p.resolve() == src_root
        except OSError:
            at_root = False
        for name in names:
            if name in _SKIP_DIR_NAMES:
                skip.add(name)
                continue
            # 任意层级 node_modules：可重建，且常含断裂 junction（WinError 3）
            if name == "node_modules":
                skip.add(name)
                continue
            # 安装根便携 Node：升级会整包覆盖
            if at_root and name in _SKIP_AT_INSTALL_ROOT:
                skip.add(name)
                continue
        return skip

    if progress:
        progress(f"复制 {src.name} …")
    shutil.copytree(
        src,
        dst,
        ignore=_ignore,
        dirs_exist_ok=False,
        ignore_dangling_symlinks=True,
    )


def _dir_size_mb(path: Path) -> float:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        return 0.0
    return round(total / (1024 * 1024), 1)


def prune_old_backups(*, keep: int = KEEP_GENERATIONS) -> None:
    root = _backups_root()
    try:
        dirs = sorted(
            [p for p in root.iterdir() if p.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return
    for old in dirs[max(0, int(keep)) :]:
        try:
            shutil.rmtree(old, ignore_errors=True)
        except OSError:
            logger.warning("prune backup failed: %s", old)


def list_system_backups() -> list[dict[str, Any]]:
    root = _backups_root()
    out: list[dict[str, Any]] = []
    try:
        dirs = sorted(
            [p for p in root.iterdir() if p.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return []
    for d in dirs[:20]:
        meta: dict[str, Any] = {"id": d.name, "path": str(d)}
        mp = d / "meta.json"
        if mp.is_file():
            try:
                meta.update(json.loads(mp.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
        out.append(meta)
    return out


def backup_system(
    *,
    reason: str = "manual",
    progress: Callable[[str], None] | None = None,
    stop_service: bool = False,
) -> tuple[bool, str, Path | None]:
    """备份当前 Harness 安装树。成功返回 (True, 人话, 目录)。"""
    root = _install_root()
    if not root.is_dir():
        return False, f"尚未安装运行环境：{root}", None

    if stop_service:
        try:
            from services import harness_sidecar

            if progress:
                progress("正在停止服务…")
            harness_sidecar.stop(force=True)
        except Exception as exc:
            logger.warning("stop before backup: %s", exc)

    info = version_info(root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _backups_root() / stamp
    try:
        dest.mkdir(parents=True, exist_ok=False)
        payload_dir = dest / "runtime"
        _copytree_filtered(root, payload_dir, progress)
        size_mb = _dir_size_mb(payload_dir)
        meta = {
            "id": stamp,
            "reason": reason,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "size_mb": size_mb,
            "flavor": info.get("flavor"),
            "installed_bundle": info.get("installed_bundle"),
            "dsh_core": info.get("dsh_core"),
            "dsh_pinned": info.get("dsh_pinned"),
            "source": str(root),
        }
        (dest / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        prune_old_backups()
        return (
            True,
            f"系统已备份（{info.get('flavor_label')} · 程序包 {info.get('installed_bundle')} · "
            f"内核 {info.get('dsh_core')} · 约 {size_mb} MB）",
            dest,
        )
    except Exception as exc:
        logger.exception("system backup failed")
        shutil.rmtree(dest, ignore_errors=True)
        return False, f"备份失败：{exc}", None


def restore_system(
    backup_id: str,
    *,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """用某次系统备份覆盖当前安装树（先再打一份 pre_restore）。"""
    sid = str(backup_id or "").strip()
    src = _backups_root() / sid / "runtime"
    if not src.is_dir():
        return False, f"找不到备份：{sid}"

    # 回滚前再留一份，防止误点
    ok_pre, msg_pre, _ = backup_system(reason="pre_restore", progress=progress, stop_service=True)
    if not ok_pre:
        logger.warning("pre_restore backup soft-fail: %s", msg_pre)

    root = _install_root()
    try:
        from services import harness_sidecar

        if progress:
            progress("正在停止服务…")
        harness_sidecar.stop(force=True)
    except Exception as exc:
        logger.warning("stop before restore: %s", exc)

    aside = root.parent / f"{root.name}_aside_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        if root.exists():
            if progress:
                progress("挪开当前安装树…")
            root.rename(aside)
        if progress:
            progress("写入备份内容…")
        shutil.copytree(src, root)
        # 回滚后清 aside（成功才删；失败可手捞）
        shutil.rmtree(aside, ignore_errors=True)
        return True, f"已从备份 {sid} 恢复运行环境"
    except Exception as exc:
        logger.exception("system restore failed")
        # 尽力还原 aside
        try:
            if aside.exists() and not root.exists():
                aside.rename(root)
        except OSError:
            pass
        return False, f"恢复失败：{exc}（若目录被挪开，请到 {aside} 手动找回）"


def restore_latest_system() -> tuple[bool, str]:
    snaps = list_system_backups()
    if not snaps:
        return False, "尚无系统备份。请先点「备份系统」。"
    return restore_system(str(snaps[0].get("id") or ""))
