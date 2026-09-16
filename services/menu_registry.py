# -*- coding: utf-8 -*-
"""菜单注册表（与 TOA2 menu_registry 同源字段）。"""
from __future__ import annotations

import re
from typing import Any

from services.config_service import get_all_menu_items, get_menu_item_by_id, get_menu_items

# 按办公室实际场景：日常随手 → 图片 → 文件交付 → 开源引擎 → 培训业务 → 系统
GROUP_ORDER = ("home", "office", "image", "files", "engines", "business", "system")
# 旧 group_id → 新（本机 menu.yml / 云端目录兼容）
GROUP_ID_ALIASES = {
    "ai": "engines",
    "directory": "files",
    "file": "files",
}
GROUP_LABELS = {
    "home": "首页与桌面",
    "office": "日常办公",
    "image": "图片处理",
    "files": "文件与目录",
    "engines": "开源引擎",
    "business": "培训业务",
    "system": "系统",
    # 兼容旧标签查询
    "ai": "开源引擎",
    "directory": "文件与目录",
    "file": "文件与目录",
}
# GROUP_LABELS = 子模块（子系统）完整名；DOMAIN_TAB_LABELS = 顶栏短名

# 顶栏子模块 Tab 短标签（一级工具栏 · 每个 Tab = 一个子系统）
DOMAIN_TAB_LABELS = {
    "home": "首页",
    "office": "办公",
    "image": "图片",
    "files": "文件",
    "engines": "引擎",
    "business": "业务",
    "system": "系统",
    "other": "其它",
    # 兼容旧 id
    "ai": "引擎",
    "directory": "文件",
    "file": "文件",
}


def normalize_menu_group_id(group_id: str | None) -> str:
    """统一菜单 group（含历史 ai/directory/file 别名）。"""
    gid = str(group_id or "").strip().lower() or "other"
    return GROUP_ID_ALIASES.get(gid, gid)


_GROUP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def is_custom_group_id(group_id: str | None) -> bool:
    """用户提升为顶栏子模块时，group 可等于模块 id（不在出厂 GROUP_ORDER）。"""
    gid = normalize_menu_group_id(group_id)
    return bool(gid) and gid not in GROUP_ORDER and gid != "other" and bool(_GROUP_ID_RE.match(gid))


def extra_group_ids_from_items(items: list[dict] | None = None) -> set[str]:
    """从菜单项收集自定义顶栏子模块 id。"""
    if items is None:
        items = get_all_menu_items()
    out: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        gid = normalize_menu_group_id(item.get("group"))
        if is_custom_group_id(gid):
            out.add(gid)
    return out


def normalize_group_order(raw: Any, *, extra_allowed: Any = None) -> list[str]:
    """校验并补齐子模块顺序：覆盖出厂 GROUP_ORDER，并保留合法自定义子模块 id。"""
    base = list(GROUP_ORDER)
    base_set = set(base)
    extras: set[str] = set()
    if extra_allowed:
        for item in extra_allowed:
            gid = normalize_menu_group_id(item)
            if is_custom_group_id(gid):
                extras.add(gid)
    if isinstance(raw, (list, tuple)):
        for item in raw:
            gid = normalize_menu_group_id(item)
            if is_custom_group_id(gid):
                extras.add(gid)
    allowed_set = base_set | extras
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(raw, (list, tuple)):
        for item in raw:
            gid = normalize_menu_group_id(item)
            if gid in allowed_set and gid not in seen:
                out.append(gid)
                seen.add(gid)
    for gid in base:
        if gid not in seen:
            out.append(gid)
            seen.add(gid)
    for gid in sorted(extras):
        if gid not in seen:
            out.append(gid)
            seen.add(gid)
    return out


def get_group_order() -> list[str]:
    """当前生效的顶栏子模块顺序（可被 menu.yml 覆盖）。"""
    try:
        from services.config_service import get_group_order as _cfg_order

        return _cfg_order()
    except Exception:
        return list(GROUP_ORDER)

# TOA3 已实现的模块页
MIGRATED_MODULES: dict[str, str] = {
    "home": "modules.home.home_page.HomePage",
    "theme_preview": "modules.gallery.control_library_page.ControlLibraryPage",
    "system_settings": "modules.system_settings.settings_page.SettingsPage",
    "user_extensions": "modules.user_extensions.user_extensions_page.UserExtensionsPage",
    "job_scheduler": "modules.job_scheduler.job_scheduler_page.JobSchedulerPage",
    "notifications": "modules.notifications.notifications_page.NotificationsPage",
    "deduction_note_formatter": "modules.deduction_note_formatter.deduction_note_page.DeductionNotePage",
    "quick_notepad": "modules.quick_notepad.quick_notepad_page.QuickNotepadPage",
    "web_workspace": "modules.web_workspace.web_workspace_page.WebWorkspacePage",
    "quadrant_tasks": "modules.quadrant_tasks.quadrant_tasks_page.QuadrantTasksPage",
    "pomodoro": "modules.pomodoro.pomodoro_page.PomodoroPage",
    "screenshot_tool": "modules.screenshot_tool.screenshot_tool_page.ScreenshotToolPage",
    "clipboard_history": "modules.clipboard_history.clipboard_history_page.ClipboardHistoryPage",
    "email_client": "modules.email_client.email_client_page.EmailClientPage",
    "batch_rename": "modules.batch_rename.batch_rename_page.BatchRenamePage",
    "image_creator": "modules.image_creator.image_creator_page.ImageCreatorPage",
    "image_adjust": "modules.image_adjust.image_adjust_page.ImageAdjustPage",
    "image_watermark": "modules.image_watermark.image_watermark_page.ImageWatermarkPage",
    "image_format_convert": "modules.image_format_convert.image_format_convert_page.ImageFormatConvertPage",
    "image_to_scan": "modules.image_to_scan.image_to_scan_page.ImageToScanPage",
    "watermark_photo_generator": "modules.watermark_photo_generator.watermark_photo_generator_page.WatermarkPhotoGeneratorPage",
    "photo_extractor": "modules.photo_extractor.photo_extractor_page.PhotoExtractorPage",
    "watermark_remover": "modules.watermark_remover.watermark_remover_page.WatermarkRemoverPage",
    "ocr_tool": "modules.ocr_tool.ocr_tool_page.OcrToolPage",
    "llm_assistant": "modules.llm_assistant.llm_assistant_page.LlmAssistantPage",
    "media_studio": "modules.media_studio.media_studio_page.MediaStudioPage",
    "engine_host_hub": "modules.engine_host_hub.engine_host_hub_page.EngineHostHubPage",
    "harness_agent": "modules.harness_agent.harness_agent_page.HarnessAgentPage",
    "open_pencil": "modules.open_pencil.open_pencil_page.OpenPencilPage",
    "drawio_web": "modules.drawio_web.drawio_web_page.DrawioWebPage",
    "comfyui_web": "modules.comfyui_web.comfyui_web_page.ComfyUiWebPage",
    "directory_generator": "modules.directory_generator.directory_generator_page.DirectoryGeneratorPage",
    "directory_inspector": "modules.directory_inspector.directory_inspector_page.DirectoryInspectorPage",
    "column_preview": "modules.column_preview.column_preview_page.ColumnPreviewPage",
    "enhanced_directory_inspector": "modules.enhanced_directory_inspector.enhanced_directory_inspector_page.EnhancedDirectoryInspectorPage",
    "deliverable_directory_check": "modules.deliverable_directory_check.deliverable_directory_check_page.DeliverableDirectoryCheckPage",
    "excel_row_to_column": "modules.excel_row_to_column.excel_row_to_column_page.ExcelRowToColumnPage",
    "document_composer": "modules.document_composer.document_composer_page.DocumentComposerPage",
    "pdf_toolkit": "modules.pdf_toolkit.pdf_toolkit_page.PdfToolkitPage",
    "file_packager": "modules.file_packager.file_packager_page.FilePackagerPage",
    "schedule_format_converter": "modules.schedule_format_converter.schedule_format_converter_page.ScheduleFormatConverterPage",
    "generic_generator_simple": "modules.generic_generator_simple.generic_generator_simple_page.GenericGeneratorSimplePage",
    "table_card_generator": "modules.table_card_generator.table_card_generator_page.TableCardGeneratorPage",
    "teaching_assistant_resume": "modules.teaching_assistant_resume.teaching_assistant_resume_generator_page.TeachingAssistantResumeGeneratorPage",
    "assistant_recruit_post": "modules.assistant_recruit_post.assistant_recruit_post_page.AssistantRecruitPostPage",
    "assistant_outfit_swap": "modules.assistant_outfit_swap.assistant_outfit_swap_page.AssistantOutfitSwapPage",
    "resume_extractor": "modules.resume_extractor.resume_extractor_page.ResumeExtractorPage",
    "schedule_reminder": "modules.schedule_reminder.schedule_reminder_page.ScheduleReminderPage",
    "training_delivery_board": "modules.training_delivery_board.training_delivery_board_page.TrainingDeliveryBoardPage",
    "__about__": "modules.about.about_page.AboutPage",
}

# 系统菜单（顶栏/热键可达；部分项不进侧栏，见 show_in_sidebar）
SYSTEM_ACTIONS = ("system_settings", "theme_preview")


def show_in_sidebar(item: dict | None) -> bool:
    """侧栏是否展示该菜单项（默认 True；system_settings 等可设 sidebar: false）。"""
    if not isinstance(item, dict):
        return False
    if item.get("sidebar") is False:
        return False
    return bool(item.get("show", True))


def group_label(group_id: str | None) -> str:
    """用户可见的子模块名（顶栏 Tab；可被 menu.yml group_labels 覆盖）。"""
    try:
        from services.config_service import get_group_labels

        labels = get_group_labels()
    except Exception:
        labels = DOMAIN_TAB_LABELS
    gid = str(group_id or "business").strip().lower()
    return labels.get(gid) or GROUP_LABELS.get(gid, "其它")


def visible_menu_items() -> list[dict[str, Any]]:
    """侧栏/首页可见菜单（尊重 show:false，再按授权过滤）。"""
    from services.access_control import filter_menu_items

    return filter_menu_items(get_menu_items())


def all_menu_items() -> list[dict[str, Any]]:
    """未过滤的完整菜单（设置页功能清单 / 审计用，含 show:false）。"""
    return get_all_menu_items()


def grouped_menu_items(
    *,
    licensed_only: bool = True,
    migrated_only: bool = False,
    include_hidden: bool = False,
) -> list[tuple[str, str, list[dict]]]:
    """返回 [(group_id, group_label, items)] 按当前 group_order 排序。"""
    order = get_group_order()
    if licensed_only:
        items = visible_menu_items()
    elif include_hidden:
        items = list(all_menu_items())
    else:
        items = list(get_menu_items())
    if migrated_only:
        items = [i for i in items if is_migrated(str(i.get("id") or ""))]
    if not include_hidden:
        items = [i for i in items if i.get("show", True)]
    buckets: dict[str, list[dict]] = {g: [] for g in order}
    other: list[dict] = []
    for item in items:
        g = normalize_menu_group_id(item.get("group") or "business")
        if g in buckets:
            buckets[g].append(item)
        elif is_custom_group_id(g):
            buckets[g] = [item]
        else:
            other.append(item)
    out: list[tuple[str, str, list[dict]]] = []
    seen_groups: set[str] = set()
    for g in order:
        if buckets.get(g):
            buckets[g].sort(key=lambda x: int(x.get("order") or 0))
            out.append((g, group_label(g), buckets[g]))
            seen_groups.add(g)
    for g in sorted(buckets):
        if g in seen_groups or not buckets[g]:
            continue
        buckets[g].sort(key=lambda x: int(x.get("order") or 0))
        out.append((g, group_label(g), buckets[g]))
    if other:
        out.append(("other", "其它", other))
    return out


def is_migrated(module_id: str) -> bool:
    if module_id in MIGRATED_MODULES:
        return True
    try:
        from services.plugin_registry import is_registered_plugin

        if is_registered_plugin(module_id):
            return True
    except Exception:
        pass
    from services.migration_manifest import get_module_meta

    return bool(get_module_meta(module_id))


def get_menu_catalog() -> list[dict[str, Any]]:
    """授权菜单清单（与侧栏可见菜单同源）。"""
    return visible_menu_items()


def get_menu_item_by_name(name: str) -> dict[str, Any] | None:
    q = str(name or "").strip()
    if not q:
        return None
    for item in visible_menu_items():
        if str(item.get("name") or "").strip() == q:
            return item
    return None
