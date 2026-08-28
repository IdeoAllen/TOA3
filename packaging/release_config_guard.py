# -*- coding: utf-8 -*-
"""发版门禁：禁止把本机测试密钥、data/user 与个人路径打进安装包。"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 正式版打包时用 shipped_config 覆盖（勿带开发者本机 integrations/harness 脏改）
RELEASE_CONFIG_OVERRIDES: frozenset[str] = frozenset(
    {
        "harness.yml",
        "integrations.yml",
    }
)

# 永不进入发布目录的文件名（任意层级）
FORBIDDEN_RELEASE_NAMES: frozenset[str] = frozenset(
    {
        "integrations_secrets.json",
        "admin_bootstrap_code.txt",
        "app.dev.yml",
        "license.json",
    }
)

# 扫描文本时的敏感模式
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9_-]{16,}"),
    re.compile(r"api_key\s*[:=]\s*['\"]?sk-", re.IGNORECASE),
    re.compile(r"Bearer\s+sk-", re.IGNORECASE),
    re.compile(r"integrations_secrets\.json", re.IGNORECASE),
)

# 发版包内不应出现的个人本机路径（Harness / 开发机）
_PERSONAL_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"C:/Users/[A-Za-z0-9._-]+/", re.IGNORECASE),
    re.compile(r"C:\\Users\\[A-Za-z0-9._-]+\\", re.IGNORECASE),
    re.compile(r"/Users/[A-Za-z0-9._-]+/", re.IGNORECASE),
    re.compile(r"\.workbuddy/", re.IGNORECASE),
    re.compile(r"WorkBuddy/", re.IGNORECASE),
)

_TEXT_SCAN_SUFFIXES: frozenset[str] = frozenset(
    {".yml", ".yaml", ".json", ".txt", ".md", ".env", ".ini", ".cfg", ".log"}
)


def shipped_config_dir(packaging_dir: Path) -> Path:
    return packaging_dir / "shipped_config"


def shipped_override_path(packaging_dir: Path, filename: str) -> Path | None:
    path = shipped_config_dir(packaging_dir) / filename
    return path if path.is_file() else None


def _scan_text(path: Path, text: str) -> list[str]:
    rel = path.as_posix()
    hits: list[str] = []
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            hits.append(f"{rel}: 疑似密钥或 secrets 引用 ({pat.pattern})")
    for pat in _PERSONAL_PATH_PATTERNS:
        if pat.search(text):
            hits.append(f"{rel}: 含个人本机路径 ({pat.pattern})")
    return hits


def scan_release_tree(root: Path) -> list[str]:
    """扫描发布目录；返回全部违规说明。"""
    if not root.is_dir():
        return [f"发布目录不存在: {root}"]

    errors: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if name == "license.json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not (
                    isinstance(payload, dict)
                    and not str(payload.get("license_key") or "").strip()
                ):
                    errors.append(f"禁止文件（含授权内容）: {path.as_posix()}")
            except json.JSONDecodeError:
                errors.append(f"禁止文件: {path.as_posix()}")
            continue
        if name in FORBIDDEN_RELEASE_NAMES or name == "integrations_secrets.json":
            errors.append(f"禁止文件: {path.as_posix()}")
            continue
        parts_lower = {p.lower() for p in path.parts}
        if "vendor" in parts_lower and path.suffix.lower() in (".md", ".txt"):
            continue
        if "data" in parts_lower and "user" in parts_lower:
            errors.append(f"禁止打包 data/user: {path.as_posix()}")
            continue
        if path.suffix.lower() not in _TEXT_SCAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"无法读取 {path.as_posix()}: {exc}")
            continue
        errors.extend(_scan_text(path, text))
    return errors


def assert_release_tree_safe(root: Path) -> None:
    errors = scan_release_tree(root)
    if errors:
        detail = "\n".join(f"  - {e}" for e in errors[:30])
        extra = ""
        if len(errors) > 30:
            extra = f"\n  … 另有 {len(errors) - 30} 条"
        raise RuntimeError(
            "发版门禁：发布目录含测试密钥、data/user 或个人路径，禁止分发。\n"
            f"{detail}{extra}"
        )


def scan_project_config_before_release(project_dir: Path, packaging_dir: Path) -> list[str]:
    """打包前确认发版模板齐全（不扫描源码 config 内 dev 文件）。"""
    errors: list[str] = []
    for name in RELEASE_CONFIG_OVERRIDES:
        override = shipped_override_path(packaging_dir, name)
        if override is None:
            errors.append(f"缺少发版模板 packaging/shipped_config/{name}")
    return errors
