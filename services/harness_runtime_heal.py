# -*- coding: utf-8 -*-
"""Harness 运行时启动自愈：Node ≥22.15（zstd）+ 残缺 otlp-transformer。"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# dsh-session-persistence-jsonl@0.1.5-rc.2 依赖 node:zlib.createZstdCompress（Node ≥22.15）
_MIN_NODE = (22, 15, 0)


def _run_node(node: Path, expr: str, *, cwd: Path | None = None, timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(
            [str(node), "-e", expr],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERR:{exc}"
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        return f"ERR:{(err[-1] if err else out) or r.returncode}"
    return out


def parse_node_version(node: Path) -> tuple[int, int, int] | None:
    raw = _run_node(node, "console.log(process.versions.node)")
    if raw.startswith("ERR:") or not raw:
        return None
    parts = raw.lstrip("v").split(".")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2] if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return None


def node_has_zstd(node: Path) -> bool:
    if not node.is_file():
        return False
    out = _run_node(node, "const z=require('node:zlib');console.log(typeof z.createZstdCompress)")
    return out == "function"


def otlp_transformer_ok(install_root: Path) -> bool:
    root = (
        Path(install_root)
        / "node_modules"
        / "@opentelemetry"
        / "otlp-transformer"
        / "build"
        / "src"
        / "logs"
        / "protobuf"
    )
    return (root / "index.js").is_file() or (root.with_suffix(".js")).is_file()


def heal_otlp_transformer(install_root: Path) -> tuple[bool, str]:
    """补齐残缺的 @opentelemetry/otlp-transformer（缺 build/src/logs 时拖死 boot）。"""
    root = Path(install_root)
    dest = root / "node_modules" / "@opentelemetry" / "otlp-transformer"
    if otlp_transformer_ok(root):
        return True, ""
    if not dest.is_dir():
        return True, ""  # 未安装则跳过；由上游依赖决定

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        # 便携 Node 旁的 npm
        cand = root / "node" / ("npm.cmd" if os.name == "nt" else "npm")
        if cand.is_file():
            npm = str(cand)
    if not npm:
        return False, "otlp-transformer 缺 logs 模块，且本机无 npm 可修复"

    try:
        with tempfile.TemporaryDirectory(prefix="toa_otel_") as tmp:
            tdir = Path(tmp)
            r = subprocess.run(
                [npm, "pack", "@opentelemetry/otlp-transformer@0.220.0", "--pack-destination", str(tdir)],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if r.returncode != 0:
                return False, f"npm pack otlp-transformer 失败：{(r.stderr or r.stdout or '')[-200:]}"
            tgzs = list(tdir.glob("opentelemetry-otlp-transformer-*.tgz"))
            if not tgzs:
                return False, "npm pack 未产出 tarball"
            extract = tdir / "pkg"
            extract.mkdir()
            subprocess.run(
                ["tar", "-xf", str(tgzs[0]), "-C", str(extract)],
                check=False,
                capture_output=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            pkg = extract / "package"
            if not (pkg / "build" / "src" / "logs" / "protobuf" / "index.js").is_file():
                return False, "tarball 内仍无 logs/protobuf"
            bak = dest.with_name(dest.name + ".bak_toa")
            if bak.exists():
                shutil.rmtree(bak, ignore_errors=True)
            dest.rename(bak)
            shutil.copytree(pkg, dest)
            shutil.rmtree(bak, ignore_errors=True)
    except Exception as exc:
        logger.warning("heal otlp-transformer failed: %s", exc)
        return False, f"修复 otlp-transformer 失败：{exc}"
    if not otlp_transformer_ok(root):
        return False, "修复后 otlp-transformer 仍缺 logs"
    return True, "已补齐 otlp-transformer"


def ensure_runtime_boot_prereqs(
    install_root: Path | None = None,
    *,
    persist_node_override: bool = True,
) -> tuple[bool, str]:
    """启动/收尾前：保证 Node 含 zstd，且 otlp-transformer 完整。"""
    from services.harness_setup import default_install_root, find_system_node

    root = Path(install_root) if install_root is not None else default_install_root()
    notes: list[str] = []

    from services.harness_config import node_exe_path, save_harness_config, load_harness_config
    from services.harness_prefab import portable_node_exe

    node = node_exe_path()
    if not node.is_file():
        node = portable_node_exe(root)

    if not node_has_zstd(node):
        alt = find_system_node()
        if alt is not None and node_has_zstd(alt):
            notes.append(
                f"便携 Node 过旧（需 ≥{_MIN_NODE[0]}.{_MIN_NODE[1]}，含 createZstdCompress），已改用本机 Node {alt}"
            )
            if persist_node_override:
                try:
                    cfg = load_harness_config()
                    cfg["node_exe"] = str(alt)
                    save_harness_config(cfg)
                except Exception as exc:
                    logger.warning("persist node override failed: %s", exc)
            node = alt
        else:
            ver = parse_node_version(node)
            ver_s = ".".join(map(str, ver)) if ver else "?"
            return (
                False,
                f"便携 Node {ver_s} 过旧：会话持久化需要 Node ≥{_MIN_NODE[0]}.{_MIN_NODE[1]}（createZstdCompress）。"
                "请更新运行环境预制包，或安装较新的本机 Node 后再启动。",
            )

    ok_otel, otel_msg = heal_otlp_transformer(root)
    if otel_msg:
        notes.append(otel_msg)
    if not ok_otel:
        return False, "；".join(notes) if notes else otel_msg

    return True, "；".join(notes) if notes else ""
