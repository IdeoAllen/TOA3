# -*- coding: utf-8 -*-
"""扩展生命周期：创建记录→目录→规则→工作区→新会话→投喂→完成/卸载。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.notify_bus import request_nav_rebuild
from services.plugin_loader import audit_plugin_root
from services.plugin_pack import PluginManifest
from services.plugin_registry import (
    list_managed_extensions,
    load_plugin_records,
    register_plugin,
    remove_plugin,
    save_plugin_records,
    set_plugin_show,
)
from services.plugin_sandbox import ensure_extensions_home
from services.plugin_scaffold import create_plugin_scaffold, suggest_plugin_id

logger = logging.getLogger(__name__)

# 生命周期状态（写入 plugins.yml status 旁的 lifecycle 字段）
LIFE_SCAFFOLD = "scaffold"  # 刚创建
LIFE_DEVELOPING = "developing"  # 已交给智能体
LIFE_READY = "ready"  # 用户确认可用


@dataclass
class ExtensionCreateResult:
    plugin_id: str
    name: str
    root: Path
    manifest: PluginManifest
    workspace_id: str = ""


def lifecycle_label(row: dict[str, Any]) -> str:
    """列表状态列白话。"""
    if not row.get("registered"):
        return "未登记"
    life = str(row.get("lifecycle") or "").strip()
    if life == LIFE_DEVELOPING:
        return "开发中 · 未上业务"
    if life == LIFE_SCAFFOLD:
        return "已创建 · 待开发"
    if life == LIFE_READY:
        if row.get("show"):
            return "可用 · 业务侧栏"
        return "可用 · 已隐藏"
    if not row.get("show"):
        return "已隐藏"
    if row.get("show"):
        return "业务侧栏"
    return "已登记"


def set_lifecycle(plugin_id: str, lifecycle: str) -> None:
    pid = str(plugin_id or "").strip()
    records = load_plugin_records(force=True)
    for row in records:
        if str(row.get("id") or "").strip() == pid:
            row["lifecycle"] = str(lifecycle or "").strip()
            save_plugin_records(records)
            return
    raise ValueError(f"未登记扩展：{pid}")


def get_lifecycle(plugin_id: str) -> str:
    pid = str(plugin_id or "").strip()
    for row in load_plugin_records(force=True):
        if str(row.get("id") or "").strip() == pid:
            return str(row.get("lifecycle") or "").strip()
    return ""


def create_extension(
    *,
    name: str,
    description: str = "",
    group: str = "business",
    surface: str = "qt",
) -> ExtensionCreateResult:
    """① 记录 ② 目录 ③ AGENTS/脚手架 ④ 审计登记。"""
    from services.plugin_scaffold import write_requirements_md

    ensure_extensions_home()
    display = str(name or "").strip()
    desc = str(description or "").strip()
    if not display:
        raise ValueError("请填写扩展名称")
    if len(desc) < 8:
        raise ValueError("请填写需求描述（场景、痛点、作用等）")
    pid = suggest_plugin_id(display)
    short = desc.splitlines()[0].strip()[:120]
    root = create_plugin_scaffold(
        None,
        plugin_id=pid,
        name=display,
        group=group or "business",
        description=short or display,
        surface=surface,
    )
    write_requirements_md(root, name=display, description=desc)
    man, report = audit_plugin_root(root)
    if not report.ok or man is None:
        msg = report.user_summary() if hasattr(report, "user_summary") else report.summary()
        raise ValueError(msg)
    register_plugin(man.root, show=False, status="mvp", gaps=[])
    set_lifecycle(man.plugin_id, LIFE_SCAFFOLD)
    request_nav_rebuild()
    return ExtensionCreateResult(
        plugin_id=man.plugin_id,
        name=man.name,
        root=Path(man.root),
        manifest=man,
    )


def build_dev_task_prompt(
    *,
    root: Path,
    name: str,
    description: str = "",
) -> str:
    """投喂 Harness 的任务书：对齐 skill toa3-sop-user-extension，锁目录、只做业务。"""
    from services.plugin_scaffold import read_requirements_md

    path_s = str(root.resolve())
    display = (name or root.name).strip() or root.name
    desc = (description or "").strip() or read_requirements_md(root)
    pid = root.name
    surface = "qt"
    toml = root / "plugin.toml"
    if toml.is_file():
        try:
            from services.plugin_pack import parse_plugin_root

            surface = parse_plugin_root(root).entry_surface
        except Exception:
            surface = "qt"
    req_block = desc if desc else "（需求正文见本目录 REQUIREMENTS.md）"
    web_extra = ""
    if surface == "webview":
        web_extra = (
            f"\n## 表面类型：WebView（HTML/JS）\n"
            f"- 只改 `ui/`（index.html / app.js / style.css）\n"
            f"- 用 `TOA.ready` + `toa.reportStatus` / `toa.showSaved`（见 HOST_API.md）\n"
            f"- 禁止写 Python Qt 布局\n"
        )
    return (
        f"【TOA 用户扩展 · skill=toa3-sop-user-extension】\n"
        f"你只做业务实现，不做宿主调研。省时间，保安全。\n\n"
        f"## 用户需求（必须按此实现，勿改题）\n"
        f"功能名：{display}\n"
        f"{req_block}\n"
        f"{web_extra}\n"
        f"## 工作区\n"
        f"唯一可读写目录：\n{path_s}\n"
        f"侧栏工作区必须是「{display}」。\n\n"
        f"开干前只读本目录：REQUIREMENTS.md、AGENTS.md、HOST_API.md、plugin.toml、入口页。"
        f"控件与 show_saved / module_data_dir 已在 HOST_API.md——"
        f"**禁止**再 Read/Grep TOA 源码。\n"
        f"读完需求后直接改入口页，做出可用主路径。\n\n"
        f"硬禁止：\n"
        f"1. 禁止 Read/Grep/Shell 任何扩展外路径：TOA 的 app/、services/、widgets/、core/、"
        f"官方 modules/、config/、安装目录、Program Files、AppData、其它扩展。\n"
        f"2. 禁止研究「插件怎么加载」；入口单文件实现，禁止 from modules.{pid}... 。\n"
        f"3. 禁止写宿主、改智能体、动系统与其它软件。\n"
        f"4. 命令只许在本扩展目录内。\n"
        f"5. 控件按 HOST_API.md；BasePage；禁止 setStyleSheet / 裸 QMessageBox。\n"
        f"6. 界面：ScrollPage + PageHeader + FormSection；"
        f"DateEdit；Primary+Secondary；短字段限宽。\n\n"
        f"任务：按上方需求实现「{display}」最小可用主路径"
        f"（能打开、能完成一次核心操作，且布局合格）。\n"
        f"需求已写清时不要再长篇追问；缺关键信息最多问一句。\n"
        f"\n完成后一句话回复："
        f"回 TOA → 顶栏「系统」→「扩展」→「开发完成」→「打开」→ 顶栏「业务」；不要了点「移除」。"
    )


def start_development(
    shell,
    *,
    plugin_id: str = "",
    root: Path | str,
    name: str = "",
    description: str = "",
    resume: bool = False,
) -> str:
    """交给智能体开发。resume=True 时回到已有会话（不新建、不重复投喂）。"""
    from services.agent_runtime import get_agent_runtime
    from services.plugin_registry import set_plugin_show
    from services.plugin_scaffold import refresh_extension_guard_docs

    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"扩展目录不存在：{path}")
    display = (name or path.name).strip() or path.name
    # 每次进开发先刷新沙箱说明书，堵住「去扫宿主 API」
    try:
        refresh_extension_guard_docs(path, plugin_id=plugin_id or path.name, name=display)
    except Exception:
        pass
    if plugin_id:
        try:
            set_lifecycle(plugin_id, LIFE_DEVELOPING)
        except ValueError:
            pass
        # 开发中不上业务侧栏
        try:
            set_plugin_show(plugin_id, False)
        except Exception:
            pass
        request_nav_rebuild()

    runtime = get_agent_runtime()
    if resume:
        return runtime.resume_dev_session(
            shell,
            path,
            name=display,
            plugin_id=plugin_id,
        )

    prompt = build_dev_task_prompt(root=path, name=display, description=description)
    return runtime.open_dev_session(
        shell,
        path,
        name=display,
        description=description,
        plugin_id=plugin_id,
        prompt=prompt,
    )


def create_and_start_development(
    shell,
    *,
    name: str,
    description: str = "",
    surface: str = "qt",
) -> ExtensionCreateResult:
    """创建全套 + 进入开发投喂。"""
    desc = str(description or "").strip()
    if len(desc) < 8:
        raise ValueError("请填写需求描述（场景、痛点、作用等）")
    created = create_extension(name=name, description=desc, surface=surface)
    wid = start_development(
        shell,
        plugin_id=created.plugin_id,
        root=created.root,
        name=created.name,
        description=desc,
    )
    created.workspace_id = wid
    return created


def mark_development_done(plugin_id: str) -> None:
    """⑦ 用户确认开发完成 → 清理临时文件 → 体检 → 可用。"""
    from services.extension_guard import cleanup_extension_junk, full_extension_guard

    set_lifecycle(plugin_id, LIFE_READY)
    set_plugin_show(plugin_id, True)
    # 清扩展内烟测/缓存，不碰宿主
    root = None
    for row in list_managed_extensions():
        if row.get("id") == plugin_id:
            raw = str(row.get("root") or "").strip()
            if raw:
                root = Path(raw)
            break
    if root is not None and root.is_dir():
        cleanup_extension_junk(root)
        report = full_extension_guard(root)
        if not report.ok:
            raise ValueError(report.user_summary())
        # warning 不阻断，由 UI 展示
        if any(f.level == "warning" for f in report.findings):
            logger.info("extension guard warnings: %s", report.summary())
    request_nav_rebuild()


def guard_report_for_plugin(plugin_id: str):
    """供设置页展示体检结果。"""
    from services.extension_guard import GuardFinding, GuardReport, full_extension_guard

    for row in list_managed_extensions():
        if row.get("id") == plugin_id:
            raw = str(row.get("root") or "").strip()
            if raw:
                return full_extension_guard(raw)
    return GuardReport(
        ok=False,
        findings=[
            GuardFinding("error", "missing", f"未找到扩展：{plugin_id}"),
        ],
    )


def uninstall_extension(plugin_id: str, *, root: Path | str | None = None) -> None:
    """卸载：取消登记 + 删目录 + 尝试清工作区条目。"""
    from services.agent_runtime import get_agent_runtime

    pid = str(plugin_id or "").strip()
    resolved = Path(root).expanduser().resolve() if root else None
    if resolved is None:
        for row in list_managed_extensions():
            if row.get("id") == pid:
                raw = str(row.get("root") or "").strip()
                if raw:
                    resolved = Path(raw).resolve()
                break
    remove_plugin(pid, delete_files=True, root=resolved)
    if resolved is not None:
        try:
            get_agent_runtime().unregister_workspace(resolved)
        except Exception:
            logger.debug("prune workspace failed", exc_info=True)
    request_nav_rebuild()


def enrich_managed_rows() -> list[dict[str, Any]]:
    """列表行附带 lifecycle 展示。"""
    life_by_id = {
        str(r.get("id") or ""): str(r.get("lifecycle") or "")
        for r in load_plugin_records(force=True)
    }
    rows = list_managed_extensions()
    for row in rows:
        pid = str(row.get("id") or "")
        row["lifecycle"] = life_by_id.get(pid) or str(row.get("status") or "")
        row["lifecycle_label"] = lifecycle_label(row)
    return rows
