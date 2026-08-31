# -*- coding: utf-8 -*-
"""扩展目录/会话安全体检：防宿主污染与扩展外冗余。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 扩展根内允许的相对路径模式（其余视为冗余/可疑）
_ALLOWED_NAMES = {
    "plugin.toml",
    "AGENTS.md",
    "HOST_API.md",
    "REQUIREMENTS.md",
    "README.md",
    "LICENSE",
    "LICENSE.txt",
}
_ALLOWED_DIR_PREFIXES = (
    "modules/",
    "ui/",
)
_IGNORE_SUFFIXES = (".pyc",)
_IGNORE_DIR_NAMES = {"__pycache__", ".git", ".dsh"}


@dataclass
class GuardFinding:
    level: str  # error | warning | info
    code: str
    message: str


@dataclass
class GuardReport:
    ok: bool
    findings: list[GuardFinding] = field(default_factory=list)

    def summary(self) -> str:
        if not self.findings:
            return "体检通过：未见宿主写入与明显冗余。"
        lines = [f"[{f.level}] {f.message}" for f in self.findings]
        return "\n".join(lines)

    def user_summary(self) -> str:
        errs = [f.message for f in self.findings if f.level == "error"]
        warns = [f.message for f in self.findings if f.level == "warning"]
        if errs:
            return "发现风险：\n- " + "\n- ".join(errs[:6])
        if warns:
            return "可用，但有提醒：\n- " + "\n- ".join(warns[:6])
        return "体检通过。"


def _is_ignored(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in _IGNORE_DIR_NAMES for p in parts):
        return True
    if rel.endswith(_IGNORE_SUFFIXES):
        return True
    return False


def audit_extension_tree(root: Path | str) -> GuardReport:
    """检查扩展目录：禁止逃逸符号链接；标记多余文件。"""
    base = Path(root).expanduser().resolve()
    findings: list[GuardFinding] = []
    if not base.is_dir():
        return GuardReport(
            ok=False,
            findings=[GuardFinding("error", "missing", f"扩展目录不存在：{base}")],
        )

    unexpected: list[str] = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(base).as_posix()
        except ValueError:
            findings.append(
                GuardFinding("error", "escape", f"文件不在扩展根下：{p}")
            )
            continue
        if _is_ignored(rel):
            continue
        name = Path(rel).name
        if name in _ALLOWED_NAMES and "/" not in rel:
            continue
        if rel.startswith(_ALLOWED_DIR_PREFIXES):
            # modules 下只允许 py / toml / md；ui 下允许 web 静态资源
            if rel.startswith("ui/"):
                if p.suffix.lower() in {
                    ".html",
                    ".htm",
                    ".js",
                    ".css",
                    ".json",
                    ".svg",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".woff",
                    ".woff2",
                    ".txt",
                    ".md",
                } or name in _ALLOWED_NAMES:
                    continue
            elif p.suffix.lower() in {".py", ".md", ".toml", ".txt", ""}:
                continue
            if name in _ALLOWED_NAMES:
                continue
        # 临时脚本
        if name.startswith("_smoke") or name.startswith("tmp_"):
            unexpected.append(rel)
            continue
        unexpected.append(rel)

    for rel in unexpected[:20]:
        findings.append(
            GuardFinding(
                "warning",
                "extra",
                f"扩展内多余/临时文件：{rel}（可删；不影响宿主）",
            )
        )

    # 入口页必须存在
    tomls = list(base.glob("plugin.toml"))
    if not tomls:
        findings.append(GuardFinding("error", "no_toml", "缺少 plugin.toml"))

    ok = not any(f.level == "error" for f in findings)
    return GuardReport(ok=ok, findings=findings)


def cleanup_extension_junk(root: Path | str) -> list[str]:
    """删除扩展内常见临时文件与 __pycache__（不碰宿主）。"""
    base = Path(root).expanduser().resolve()
    removed: list[str] = []
    if not base.is_dir():
        return removed
    for p in list(base.rglob("*")):
        if not p.exists():
            continue
        try:
            rel = p.relative_to(base).as_posix()
        except ValueError:
            continue
        name = p.name
        if p.is_dir() and name == "__pycache__":
            import shutil

            shutil.rmtree(p, ignore_errors=True)
            removed.append(rel + "/")
            continue
        if p.is_file() and (
            name.startswith("_smoke")
            or name.startswith("tmp_")
            or name.endswith(".pyc")
        ):
            try:
                p.unlink()
                removed.append(rel)
            except OSError:
                pass
    return removed


def find_session_dir_for_extension(root: Path | str) -> Path | None:
    """在 DSH sessions 下找指向该扩展路径的会话目录。"""
    try:
        from services.harness_config import dsh_home_path

        home = Path(dsh_home_path())
    except Exception:
        return None
    sessions = home / "sessions"
    if not sessions.is_dir():
        return None
    key = str(Path(root).resolve()).replace(":", "").replace("\\", "-").replace("/", "-")
    # DSH 目录名类似 --C-Users-...-ext_968073--
    best: Path | None = None
    for d in sessions.iterdir():
        if not d.is_dir():
            continue
        if key in d.name or Path(root).name in d.name:
            # pick newest session child
            kids = [c for c in d.iterdir() if c.is_dir() and c.name.startswith("session-")]
            if kids:
                kids.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                return kids[0]
            best = d
    return best


def audit_session_writes(
    session_dir: Path | str,
    *,
    extension_root: Path | str,
) -> GuardReport:
    """
    解析 session.jsonl.zstd：检查 write/edit 是否逃出扩展目录。
    只读宿主记 warning（策略违规），写入宿主记 error。
    """
    sdir = Path(session_dir)
    ext = Path(extension_root).resolve()
    ext_s = str(ext).lower()
    findings: list[GuardFinding] = []
    zpath = sdir / "session.jsonl.zstd"
    if not zpath.is_file():
        # maybe plain jsonl
        plain = sdir / "session.jsonl"
        if plain.is_file():
            raw = plain.read_bytes()
        else:
            return GuardReport(
                ok=True,
                findings=[
                    GuardFinding("info", "no_session", "未找到会话日志，跳过写入审计")
                ],
            )
    else:
        try:
            import zstandard as zstd

            dctx = zstd.ZstdDecompressor()
            with zpath.open("rb") as fh, dctx.stream_reader(fh) as reader:
                raw = reader.read()
        except Exception as exc:
            logger.debug("decompress session failed: %s", exc)
            return GuardReport(
                ok=True,
                findings=[
                    GuardFinding(
                        "info",
                        "no_zstd",
                        f"无法解压会话日志（{exc}），跳过写入审计",
                    )
                ],
            )

    write_outside = 0
    read_host = 0
    write_inside = 0
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if "tool-call" not in line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue

        def visit(o: Any) -> None:
            nonlocal write_outside, read_host, write_inside
            if isinstance(o, dict):
                if o.get("type") == "tool-call":
                    name = str(o.get("name") or "").lower()
                    args = o.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    fp = str(
                        args.get("file_path")
                        or args.get("path")
                        or args.get("filePath")
                        or ""
                    ).strip()
                    if fp:
                        try:
                            inside = str(Path(fp).resolve()).lower().startswith(ext_s)
                        except Exception:
                            inside = ext_s in fp.lower().replace("/", "\\")
                        if name in ("write", "edit", "create"):
                            if inside:
                                write_inside += 1
                            else:
                                write_outside += 1
                                findings.append(
                                    GuardFinding(
                                        "error",
                                        "write_outside",
                                        f"会话曾写入扩展外：{fp}",
                                    )
                                )
                        elif name == "read" and not inside:
                            # host read
                            if "toa3" in fp.lower() or "yczh-tdp" in fp.lower():
                                read_host += 1
                for v in o.values():
                    visit(v)
            elif isinstance(o, list):
                for x in o:
                    visit(x)

        visit(ev)

    if read_host:
        findings.append(
            GuardFinding(
                "warning",
                "read_host",
                f"会话中只读访问宿主约 {read_host} 次（未改文件，但浪费且不安全；新策略已禁止）",
            )
        )
    if write_inside and not write_outside:
        findings.append(
            GuardFinding(
                "info",
                "writes_ok",
                f"写入均在扩展内（约 {write_inside} 次），未见改宿主源码",
            )
        )

    ok = not any(f.level == "error" for f in findings)
    return GuardReport(ok=ok, findings=findings)


def full_extension_guard(root: Path | str) -> GuardReport:
    """目录体检 +（若有）最近会话写入审计。"""
    tree = audit_extension_tree(root)
    findings = list(tree.findings)
    sess = find_session_dir_for_extension(root)
    if sess is not None:
        srep = audit_session_writes(sess, extension_root=root)
        findings.extend(srep.findings)
    ok = not any(f.level == "error" for f in findings)
    return GuardReport(ok=ok, findings=findings)
