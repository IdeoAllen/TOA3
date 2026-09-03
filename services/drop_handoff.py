# -*- coding: utf-8 -*-
"""拖入 TOA → MACOS 桌面：启动参数解析与 IPC 载荷。

非独立侧栏模块；见 docs/research/drop_handoff-top3.md。
"""
from __future__ import annotations

import sys
from pathlib import Path


_SKIP_FLAGS_WITH_VALUE = frozenset(
    {
        "--activate-license",
        "--verify-license",
    }
)


def collect_launch_paths(argv: list[str] | None = None) -> list[Path]:
    """从命令行收集存在的本地文件/目录路径（拖到图标时由系统传入）。"""
    raw = list(sys.argv[1:] if argv is None else argv)
    out: list[Path] = []
    i = 0
    while i < len(raw):
        a = str(raw[i] or "").strip()
        if not a:
            i += 1
            continue
        if a in _SKIP_FLAGS_WITH_VALUE:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        try:
            p = Path(a).expanduser()
            if not p.exists():
                i += 1
                continue
            out.append(p.resolve())
        except OSError:
            pass
        i += 1
    return out


def encode_ipc_message(paths: list[str] | None = None) -> bytes:
    """单实例载荷：无路径 = activate；有路径 = open\\0p1\\0p2…（UTF-8）。"""
    cleaned = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not cleaned:
        return b"activate"
    parts = [b"open"] + [p.encode("utf-8", "surrogatepass") for p in cleaned]
    return b"\0".join(parts)


def decode_ipc_message(data: bytes) -> tuple[str, list[str]]:
    """返回 (命令, 路径列表)。命令为 activate | open。"""
    if not data:
        return "activate", []
    # 兼容旧客户端只发 activate
    if data.strip() == b"activate" or data.startswith(b"activate") and b"\0" not in data:
        return "activate", []
    parts = data.split(b"\0")
    if not parts:
        return "activate", []
    cmd = parts[0].decode("utf-8", "replace").strip().lower()
    if cmd == "open":
        paths: list[str] = []
        for chunk in parts[1:]:
            if not chunk:
                continue
            try:
                paths.append(chunk.decode("utf-8", "surrogatepass"))
            except Exception:
                continue
        return "open", paths
    return "activate", []
