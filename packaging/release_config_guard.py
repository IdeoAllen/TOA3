# -*- coding: utf-8 -*-
"""发版门禁：禁止把本机测试密钥、data/user 与个人路径打进安装包。"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 正式版打包时用 shipped_config 覆盖（勿带开发者本机 integrations/harness/模型清单）
RELEASE_CONFIG_OVERRIDES: frozenset[str] = frozenset(
    {
        "harness.yml",
        "integrations.yml",
        "model_catalog.yml",
        "local_image_bundle.yml",
    }
)

# 发版 assets 下不打包的路径（相对 assets/）
RELEASE_ASSET_SKIP_PREFIXES: tuple[str, ...] = (
    "samples/comfyui",
    "samples/license_acceptance",
)

# 发版 assets 下不打包的文件名（任意层级；含开发机绝对路径的 Agent 说明）
RELEASE_ASSET_SKIP_NAMES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
    }
)

# 永不进入发布目录的文件名（任意层级）
FORBIDDEN_RELEASE_NAMES: frozenset[str] = frozenset(
    {
        "integrations_secrets.json",
        "admin_bootstrap_code.txt",
        "app.dev.yml",
        "license.json",
        # 验收/本机备份授权，含手机号·机器码·授权码，严禁进安装包
        "license.json.bak.acceptance",
    }
)

# 文件名匹配即剔除（顶层 config 复制）
FORBIDDEN_RELEASE_NAME_PREFIXES: tuple[str, ...] = (
    "license.json.bak",
    "integrations_secrets",
)

# 扫描文本时的敏感模式
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9_-]{16,}"),
    re.compile(r"TOA2-eyJ[A-Za-z0-9_\-=]+"),  # 本机授权 JWT 码
    re.compile(r"api_key\s*[:=]\s*['\"]?sk-", re.IGNORECASE),
    re.compile(r"Bearer\s+sk-", re.IGNORECASE),
    re.compile(r"integrations_secrets\.json", re.IGNORECASE),
    re.compile(r'"license_key"\s*:\s*"(?!")[^"]{8,}"'),  # 非空授权码
    re.compile(r'"bound_machine_id"\s*:\s*"[a-f0-9]{16,}"', re.IGNORECASE),
    re.compile(r'"phone"\s*:\s*"\d{6,}"'),
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


def release_asset_rel_should_skip(rel_posix: str) -> bool:
    """rel_posix 相对 assets/ 根，如 samples/comfyui/foo.json。"""
    rel = rel_posix.replace("\\", "/").strip().lstrip("/")
    name = Path(rel).name
    if name in RELEASE_ASSET_SKIP_NAMES:
        return True
    for prefix in RELEASE_ASSET_SKIP_PREFIXES:
        p = prefix.strip("/")
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def release_assets_ignore(_dir: str, names: list[str]) -> set[str]:
    """shutil.copytree ignore：跳过发版不含的 samples 子目录。"""
    ignored: set[str] = set()
    base = Path(_dir)
    try:
        rel_base = base.relative_to(base.anchor)
    except ValueError:
        rel_base = Path(_dir)
    for name in names:
        child = Path(_dir) / name
        if child.is_dir():
            try:
                # 相对 PROJECT/assets 的路径在 copytree 回调里用 name 拼接
                rel = str(Path(name))
                if release_asset_rel_should_skip(rel):
                    ignored.add(name)
                    continue
            except Exception:
                pass
        rel_name = name.replace("\\", "/")
        if release_asset_rel_should_skip(rel_name):
            ignored.add(name)
    return ignored


def make_release_assets_ignore(src_assets: Path):
    """返回 copytree ignore 回调，rel 相对 src_assets。"""

    def _ignore(dir_path: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        dir_p = Path(dir_path)
        try:
            rel_dir = dir_p.relative_to(src_assets).as_posix()
        except ValueError:
            rel_dir = ""
        for name in names:
            rel = f"{rel_dir}/{name}".strip("/") if rel_dir else name.replace("\\", "/")
            if release_asset_rel_should_skip(rel):
                ignored.add(name)
        return ignored

    return _ignore


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


def _should_text_scan_release_path(root: Path, path: Path) -> bool:
    """
    文本密钥/个人路径扫描只覆盖我们自有内容。
    PyInstaller _internal 下第三方包（如 botocore examples 的假 sk-）一律跳过，
    仅保留 _internal/config（发版模板覆盖后的干净配置）。
    """
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True
    if not rel_parts:
        return True
    top = rel_parts[0].lower()
    if top == "_internal":
        return len(rel_parts) >= 2 and rel_parts[1].lower() == "config"
    if top in {"config", "assets", "avatars", "ui", "vendor"}:
        return True
    # 发布根 README.txt 等
    return len(rel_parts) == 1


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
        if any(name.startswith(p) for p in FORBIDDEN_RELEASE_NAME_PREFIXES):
            errors.append(f"禁止文件: {path.as_posix()}")
            continue
        if name.startswith("license.json.") and name != "license.json.example":
            errors.append(f"禁止打包授权备份: {path.as_posix()}")
            continue
        parts_lower = {p.lower() for p in path.parts}
        if "vendor" in parts_lower and path.suffix.lower() in (".md", ".txt"):
            continue
        if "data" in parts_lower and "user" in parts_lower:
            errors.append(f"禁止打包 data/user: {path.as_posix()}")
            continue
        if path.suffix.lower() not in _TEXT_SCAN_SUFFIXES:
            continue
        if not _should_text_scan_release_path(root, path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"无法读取 {path.as_posix()}: {exc}")
            continue
        if name == "model_catalog.yml":
            # 空模板允许 profiles: {}；有 api_base / 具体模型 id 一律拦
            if re.search(r"api_base\s*:", text) or "huggingface.co" in text:
                errors.append(
                    f"发版禁止预置模型 catalog（请用 shipped_config/model_catalog.yml）: {path.as_posix()}"
                )
        if name == "local_image_bundle.yml" and "huggingface.co" in text:
            errors.append(
                f"发版禁止打包本机模型下载清单: {path.as_posix()}"
            )
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
