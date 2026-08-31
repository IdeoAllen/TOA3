# -*- coding: utf-8 -*-
"""扩展沙箱路径围栏：判定工具调用是否逃出扩展根。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# 读/搜类工具（DSH 上游不禁读，需 TOA 侧硬闸）
_READISH = frozenset(
    {
        "read",
        "grep",
        "glob",
        "search",
        "rg",
        "list_dir",
        "listdir",
        "ls",
        "stat",
        "bash",
        "pwsh",
        "shell",
        "powershell",
        "run_terminal_cmd",
        "run_command",
    }
)
_WRITEISH = frozenset({"write", "edit", "create", "apply_patch", "delete", "remove"})

_ABS_WIN = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_ABS_POSIX = re.compile(r"(?<![\\w:])/(?:Users|home|opt|var|tmp|mnt)[^\s\"']*")


@dataclass(frozen=True)
class FenceBreach:
    tool: str
    path: str
    kind: str  # read_outside | write_outside | shell_escape


def _norm(p: Path | str) -> str:
    try:
        return str(Path(p).expanduser().resolve()).lower().replace("/", "\\")
    except Exception:
        return str(p or "").lower().replace("/", "\\")


def allowed_roots_for_extension(
    extension_root: Path | str,
    *,
    plugin_id: str = "",
) -> list[Path]:
    """唯一合法路径集合：扩展根 + 该扩展 data/output。"""
    root = Path(extension_root).expanduser().resolve()
    roots = [root]
    pid = str(plugin_id or root.name).strip()
    try:
        from services.storage_paths import module_data_dir, module_output_dir

        roots.append(module_data_dir(pid, create=False).resolve())
        roots.append(module_output_dir(pid, create=False).resolve())
    except Exception:
        pass
    return roots


def path_inside_roots(path: Path | str, roots: Iterable[Path | str]) -> bool:
    raw = str(path or "").strip()
    if not raw:
        return True  # 无路径参数视为相对 cwd（工作区）
    root_list = [Path(r).expanduser().resolve() for r in roots]
    primary = root_list[0] if root_list else None

    # 相对路径：相对扩展根解析后再判（挡住 ../ 逃逸）
    is_abs = bool(
        re.match(r"^[A-Za-z]:[\\/]", raw)
        or raw.startswith("\\\\")
        or raw.startswith("/")
    )
    try:
        if is_abs:
            target = Path(raw).expanduser().resolve()
        elif primary is not None:
            target = (primary / raw).resolve()
        else:
            target = Path(raw).expanduser().resolve()
    except Exception:
        return False

    target_s = _norm(target)
    for r in root_list:
        base = _norm(r)
        if not base:
            continue
        if target_s == base or target_s.startswith(base + "\\"):
            return True
    return False


def _extract_paths(args: dict[str, Any]) -> list[str]:
    keys = (
        "file_path",
        "filePath",
        "path",
        "target_directory",
        "targetDirectory",
        "directory",
        "cwd",
        "working_directory",
        "workingDirectory",
    )
    out: list[str] = []
    for k in keys:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    # Shell 命令正文里抠绝对路径
    for k in ("command", "cmd", "script"):
        v = args.get(k)
        if not isinstance(v, str):
            continue
        out.extend(_ABS_WIN.findall(v))
        out.extend(_ABS_POSIX.findall(v))
    return out


def classify_tool_call(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    roots: list[Path],
) -> list[FenceBreach]:
    name = str(tool_name or "").strip().lower()
    args = arguments if isinstance(arguments, dict) else {}
    paths = _extract_paths(args)
    if not paths:
        return []
    breaches: list[FenceBreach] = []
    for fp in paths:
        if path_inside_roots(fp, roots):
            continue
        if name in _WRITEISH:
            kind = "write_outside"
        elif name in {"bash", "pwsh", "shell", "powershell", "run_terminal_cmd", "run_command"}:
            kind = "shell_escape"
        else:
            kind = "read_outside"
        breaches.append(FenceBreach(tool=name or "tool", path=fp, kind=kind))
    return breaches


def _iter_tool_calls(obj: Any):
    if isinstance(obj, dict):
        if obj.get("type") == "tool-call" or "toolCall" in str(obj.get("type") or ""):
            yield obj
        name = obj.get("name") or obj.get("toolName") or obj.get("tool")
        args = obj.get("arguments") or obj.get("args") or obj.get("input")
        if name and args is not None and (
            obj.get("type") in (None, "tool-call", "tool_use", "function_call")
            or "tool" in str(obj.get("type") or "").lower()
        ):
            # 宽松：带 name+arguments 的节点
            if isinstance(args, (dict, str)):
                yield obj
        for v in obj.values():
            yield from _iter_tool_calls(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _iter_tool_calls(x)


def scan_session_log_bytes(
    raw: bytes,
    *,
    extension_root: Path | str,
    plugin_id: str = "",
    skip_lines: int = 0,
) -> tuple[list[FenceBreach], int]:
    """
    扫描会话日志字节，返回越界列表与已处理行数。
    skip_lines：跳过已看过的行（增量）。
    """
    roots = allowed_roots_for_extension(extension_root, plugin_id=plugin_id)
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    breaches: list[FenceBreach] = []
    seen: set[tuple[str, str, str]] = set()
    for i, line in enumerate(lines):
        if i < skip_lines:
            continue
        if "tool" not in line.lower():
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        for node in _iter_tool_calls(ev):
            name = str(node.get("name") or node.get("toolName") or node.get("tool") or "")
            args = node.get("arguments") or node.get("args") or node.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            for b in classify_tool_call(name, args, roots=roots):
                key = (b.kind, b.tool, _norm(b.path))
                if key in seen:
                    continue
                seen.add(key)
                breaches.append(b)
    return breaches, len(lines)


def load_session_log_bytes(session_dir: Path | str) -> bytes | None:
    sdir = Path(session_dir)
    zpath = sdir / "session.jsonl.zstd"
    plain = sdir / "session.jsonl"
    if zpath.is_file():
        try:
            import zstandard as zstd

            dctx = zstd.ZstdDecompressor()
            with zpath.open("rb") as fh, dctx.stream_reader(fh) as reader:
                return reader.read()
        except Exception as exc:
            logger.debug("zstd read failed: %s", exc)
            return None
    if plain.is_file():
        try:
            return plain.read_bytes()
        except OSError:
            return None
    return None


def find_session_dir_by_id(session_id: str) -> Path | None:
    sid = str(session_id or "").strip()
    if not sid:
        return None
    try:
        from services.harness_config import dsh_home_path

        home = Path(dsh_home_path())
    except Exception:
        return None
    sessions = home / "sessions"
    if not sessions.is_dir():
        return None
    for d in sessions.rglob(sid):
        if d.is_dir() and (
            (d / "session.jsonl.zstd").is_file() or (d / "session.jsonl").is_file()
        ):
            return d
    # 直接子层
    for ws in sessions.iterdir():
        if not ws.is_dir():
            continue
        cand = ws / sid
        if cand.is_dir() and (
            (cand / "session.jsonl.zstd").is_file() or (cand / "session.jsonl").is_file()
        ):
            return cand
    return None
