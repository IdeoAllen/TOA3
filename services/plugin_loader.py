# -*- coding: utf-8 -*-
"""业务插件：审计 + 运行时加载 BasePage（按文件路径，避免与内置 modules 包冲突）。"""
from __future__ import annotations

import ast
import importlib.util
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from core.base_page import BasePage
from core.exceptions import ModuleLoadError
from services.plugin_pack import PluginManifest, parse_plugin_root
from services.plugin_registry import resolve_manifest

logger = logging.getLogger(__name__)

_FORBIDDEN_STYLESHEET = re.compile(r"setStyleSheet\s*\(")
_FORBIDDEN_QMESSAGE = re.compile(r"\bQMessageBox\b")
_FORBIDDEN_SUBPROCESS = re.compile(r"\b(subprocess|os\.system|os\.popen)\b")
_FORBIDDEN_URLLIB = re.compile(r"\b(urllib\.request|requests\.|httpx\.)\b")
_FORBIDDEN_EVAL = re.compile(r"\b(eval|exec|__import__)\s*\(")
_FORBIDDEN_PATH_ESCAPE = re.compile(
    r"""(?:Path\s*\(\s*["']\.\./|open\s*\(\s*["']\.\./|["']\.\./\.\./)"""
)

_LOADED_MODULES: dict[str, ModuleType] = {}


@dataclass
class AuditIssue:
    level: str  # error | warning
    code: str
    message: str


@dataclass
class AuditReport:
    ok: bool
    issues: list[AuditIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[AuditIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[AuditIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def summary(self) -> str:
        if self.ok and not self.issues:
            return "审计通过"
        lines = [f"[{i.level}] {i.code}: {i.message}" for i in self.issues]
        return "\n".join(lines) if lines else ("审计通过" if self.ok else "审计失败")

    def user_summary(self) -> str:
        """给终端用户的白话摘要（不含技术 code）。"""
        if self.ok and not self.errors:
            return "安全检查通过"
        if not self.errors:
            return "安全检查基本通过（有提醒，不影响上架）"
        hints = {
            "manifest": "扩展说明文件不完整或格式不对",
            "id_conflict": "这个名字和软件自带功能冲突，请换一个",
            "unsafe_root": "扩展放错位置了，必须放在本机用户扩展区",
            "no_stylesheet": "扩展里不能自己改皮肤颜色",
            "no_qmessagebox": "扩展里弹窗写法不符合规范",
            "no_shell": "扩展未允许运行系统命令",
            "no_network": "扩展未允许联网",
            "no_winreg": "扩展不能改注册表",
            "no_ctypes": "扩展不能使用危险的底层调用",
            "no_os_power": "扩展不能关机或重启电脑",
            "no_eval": "扩展不能动态执行任意代码",
            "no_path_escape": "扩展不能读写本文件夹以外的路径",
            "entry_missing": "缺少功能入口页面",
            "web_entry_missing": "缺少网页入口文件",
            "class_missing": "功能入口类名对不上",
            "syntax": "扩展代码有语法错误",
            "read": "有文件读不出来",
        }
        parts: list[str] = []
        for err in self.errors[:3]:
            parts.append(hints.get(err.code, err.message.split(":")[0] or "有一处不符合安全规则"))
        return "安全检查未过：" + "；".join(parts)


def _py_files(root: Path) -> list[Path]:
    base = root / "modules"
    if not base.is_dir():
        return []
    return [p for p in base.rglob("*.py") if p.is_file()]


def audit_plugin_root(root: Path | str) -> tuple[PluginManifest | None, AuditReport]:
    issues: list[AuditIssue] = []
    try:
        man = parse_plugin_root(root)
    except Exception as exc:
        return None, AuditReport(
            ok=False,
            issues=[AuditIssue("error", "manifest", str(exc))],
        )

    from services.menu_registry import MIGRATED_MODULES

    if man.plugin_id in MIGRATED_MODULES:
        issues.append(
            AuditIssue("error", "id_conflict", f"与内置模块 id 冲突：{man.plugin_id}")
        )

    try:
        from services.plugin_sandbox import assert_registerable_root

        assert_registerable_root(man.root, allow_sample=True)
    except ValueError as exc:
        issues.append(AuditIssue("error", "unsafe_root", str(exc)))

    # 扫描包内全部 .py（不只入口）
    for py in _py_files(man.root):
        try:
            src = py.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(AuditIssue("error", "read", f"{py.name}: {exc}"))
            continue
        rel = py.relative_to(man.root).as_posix()
        if _FORBIDDEN_STYLESHEET.search(src):
            issues.append(
                AuditIssue("error", "no_stylesheet", f"{rel}: 禁止 setStyleSheet")
            )
        if _FORBIDDEN_QMESSAGE.search(src):
            issues.append(
                AuditIssue("error", "no_qmessagebox", f"{rel}: 禁止裸 QMessageBox")
            )
        if not man.allow_shell and _FORBIDDEN_SUBPROCESS.search(src):
            issues.append(
                AuditIssue("error", "no_shell", f"{rel}: 未声明 allow_shell")
            )
        if not man.allow_network and _FORBIDDEN_URLLIB.search(src):
            issues.append(
                AuditIssue("error", "no_network", f"{rel}: 未声明 allow_network")
            )
        if _FORBIDDEN_EVAL.search(src):
            issues.append(
                AuditIssue("error", "no_eval", f"{rel}: 禁止 eval/exec/__import__")
            )
        if _FORBIDDEN_PATH_ESCAPE.search(src):
            issues.append(
                AuditIssue("error", "no_path_escape", f"{rel}: 疑似读写本扩展目录以外路径")
            )
        for pat, code, msg in (
            (r"\bwinreg\b", "no_winreg", "禁止操作注册表"),
            (r"\bctypes\b", "no_ctypes", "禁止 ctypes（易越权）"),
            (r"ShutdownSystem|ExitWindows", "no_os_power", "禁止系统关机类调用"),
        ):
            if re.search(pat, src):
                issues.append(AuditIssue("error", code, f"{rel}: {msg}"))

    page = man.page_file
    if man.is_webview_surface:
        web_entry = man.web_entry_file
        if not web_entry.is_file():
            issues.append(
                AuditIssue(
                    "error",
                    "web_entry_missing",
                    f"缺少网页入口：{man.web_root}",
                )
            )
        elif web_entry.suffix.lower() not in (".html", ".htm"):
            issues.append(
                AuditIssue("warning", "web_entry_ext", "网页入口建议使用 .html")
            )
    elif not page.is_file():
        issues.append(
            AuditIssue("error", "entry_missing", f"缺少入口文件：{page}")
        )
    else:
        try:
            src = page.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(AuditIssue("error", "entry_read", str(exc)))
            src = ""

        if src:
            if "BasePage" not in src:
                issues.append(
                    AuditIssue("warning", "base_page", "入口文件未见 BasePage，请确认继承关系")
                )
            try:
                tree = ast.parse(src)
                has_class = any(
                    isinstance(n, ast.ClassDef) and n.name == man.class_name for n in tree.body
                )
                if not has_class:
                    issues.append(
                        AuditIssue(
                            "error",
                            "class_missing",
                            f"入口文件未定义 class {man.class_name}",
                        )
                    )
            except SyntaxError as exc:
                issues.append(AuditIssue("error", "syntax", f"语法错误：{exc}"))

    if page.is_file() and not man.is_webview_surface:
        pass  # 已在上方处理 qt 入口
    elif page.is_file() and man.is_webview_surface:
        # webview 可选保留 py 占位；若存在则做语法扫描（上方 _py_files 已扫）
        try:
            src = page.read_text(encoding="utf-8")
            if src.strip():
                try:
                    ast.parse(src)
                except SyntaxError as exc:
                    issues.append(AuditIssue("error", "syntax", f"入口 py 语法错误：{exc}"))
        except OSError:
            pass

    # 移除旧的重复 page 检查块 — 下面 agents 检查保留
    agents = man.root / "AGENTS.md"
    if not agents.is_file():
        issues.append(AuditIssue("warning", "agents_md", "建议保留 AGENTS.md 供 Harness 遵守铁律"))

    ok = not any(i.level == "error" for i in issues)
    return man, AuditReport(ok=ok, issues=issues)


def _module_key(manifest: PluginManifest) -> str:
    return f"toa_user_plugin.{manifest.plugin_id}"


def load_plugin_page_class(manifest: PluginManifest, *, reload: bool = False) -> type:
    """从插件目录按文件加载页面类。"""
    page = manifest.page_file
    if not page.is_file():
        raise ModuleLoadError(manifest.plugin_id, f"缺少入口：{page}")

    key = _module_key(manifest)
    if reload and key in _LOADED_MODULES:
        del _LOADED_MODULES[key]
        sys.modules.pop(key, None)

    if key in _LOADED_MODULES and not reload:
        mod = _LOADED_MODULES[key]
    else:
        spec = importlib.util.spec_from_file_location(key, page)
        if spec is None or spec.loader is None:
            raise ModuleLoadError(manifest.plugin_id, f"无法创建加载规格：{page}")
        mod = importlib.util.module_from_spec(spec)
        # 保证同包相对导入可读：先登记父包
        pkg_name = f"toa_user_plugin.{manifest.plugin_id}"
        if pkg_name not in sys.modules:
            pkg = ModuleType(pkg_name)
            pkg.__path__ = [str(page.parent)]  # type: ignore[attr-defined]
            sys.modules[pkg_name] = pkg
        sys.modules[key] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:
            sys.modules.pop(key, None)
            raise ModuleLoadError(manifest.plugin_id, f"执行入口失败：{exc}") from exc
        _LOADED_MODULES[key] = mod

    cls = getattr(mod, manifest.class_name, None)
    if cls is None:
        raise ModuleLoadError(manifest.plugin_id, f"未找到类 {manifest.class_name}")
    if not isinstance(cls, type) or not issubclass(cls, BasePage):
        raise ModuleLoadError(manifest.plugin_id, f"{manifest.class_name} 不是 BasePage 子类")
    return cls


def create_plugin_page(plugin_id: str, menu_item: dict[str, Any] | None = None) -> BasePage:
    man = resolve_manifest(plugin_id)
    if man is None:
        root = str((menu_item or {}).get("plugin_root") or "").strip()
        if root:
            man = parse_plugin_root(root)
        else:
            raise ModuleLoadError(plugin_id, "未登记或无法解析插件")

    _, report = audit_plugin_root(man.root)
    if not report.ok:
        raise ModuleLoadError(plugin_id, f"插件审计未通过：\n{report.summary()}")

    if man.is_webview_surface:
        from core.extension_web_page import create_extension_web_page

        page = create_extension_web_page(man)
        if not getattr(page, "page_id", None):
            page.page_id = man.plugin_id
        if not getattr(page, "page_title", None):
            page.page_title = man.name
        return page

    cls = load_plugin_page_class(man)
    page = cls()
    if not getattr(page, "page_id", None):
        page.page_id = man.plugin_id
    if not getattr(page, "page_title", None):
        page.page_title = man.name
    return page
