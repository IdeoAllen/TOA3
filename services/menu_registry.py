# -*- coding: utf-8 -*-
"""菜单注册表（与 TOA2 menu_registry 同源字段）。"""
from __future__ import annotations

from typing import Any

from services.config_service import get_all_menu_items, get_menu_item_by_id, get_menu_items

GROUP_ORDER = ("home", "office", "ai", "image", "directory", "file", "business", "system")
GROUP_LABELS = {
    "home": "首页",
    "office": "办公增效",
    "ai": "AI 智能体",
    "image": "图片处理",
    "directory": "文件/目录操作",
    "file": "文件操作",
    "business": "业务相关",
    "system": "系统",
}
# GROUP_LABELS = 子模块（子系统）完整名；DOMAIN_TAB_LABELS = 顶栏短名

# 顶栏子模块 Tab 短标签（一级工具栏 · 每个 Tab = 一个子系统）
DOMAIN_TAB_LABELS = {
    "home": "首页",
    "office": "办公",
    "ai": "AI",
    "image": "图片",
    "directory": "目录",
    "file": "文件",
    "business": "业务",
    "system": "系统",
    "other": "其它",
}

# TOA3 已实现的模块页
MIGRATED_MODULES: dict[str, str] = {
    "home": "modules.home.home_page.HomePage",
    "theme_preview": "modules.gallery.control_library_page.ControlLibraryPage",
    "system_settings": "modules.system_settings.settings_page.SettingsPage",
    "job_scheduler": "modules.job_scheduler.job_scheduler_page.JobSchedulerPage",
    "notifications": "modules.notifications.notifications_page.NotificationsPage",
    "deduction_note_formatter": "modules.deduction_note_formatter.deduction_note_page.DeductionNotePage",
    "quick_notepad": "modules.quick_notepad.quick_notepad_page.QuickNotepadPage",
    "web_workspace": "modules.web_workspace.web_workspace_page.WebWorkspacePage",
    "quadrant_tasks": "modules.quadrant_tasks.quadrant_tasks_page.QuadrantTasksPage",
    "pomodoro": "modules.pomodoro.pomodoro_page.PomodoroPage",
    "screenshot_tool": "modules.screenshot_tool.screenshot_tool_page.ScreenshotToolPage",
    "clipboard_history": "modules.clipboard_history.clipboard_history_page.ClipboardHistoryPage",
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
    "harness_agent": "modules.harness_agent.harness_agent_page.HarnessAgentPage",
    "directory_generator": "modules.directory_generator.directory_generator_page.DirectoryGeneratorPage",
    "directory_inspector": "modules.directory_inspector.directory_inspector_page.DirectoryInspectorPage",
    "column_preview": "modules.column_preview.column_preview_page.ColumnPreviewPage",
    "enhanced_directory_inspector": "modules.enhanced_directory_inspector.enhanced_directory_inspector_page.EnhancedDirectoryInspectorPage",
    "excel_row_to_column": "modules.excel_row_to_column.excel_row_to_column_page.ExcelRowToColumnPage",
    "document_composer": "modules.document_composer.document_composer_page.DocumentComposerPage",
    "schedule_format_converter": "modules.schedule_format_converter.schedule_format_converter_page.ScheduleFormatConverterPage",
    "generic_generator_simple": "modules.generic_generator_simple.generic_generator_simple_page.GenericGeneratorSimplePage",
    "table_card_generator": "modules.table_card_generator.table_card_generator_page.TableCardGeneratorPage",
    "teaching_assistant_resume": "modules.teaching_assistant_resume.teaching_assistant_resume_generator_page.TeachingAssistantResumeGeneratorPage",
    "resume_extractor": "modules.resume_extractor.resume_extractor_page.ResumeExtractorPage",
    "schedule_reminder": "modules.schedule_reminder.schedule_reminder_page.ScheduleReminderPage",
    "__about__": "modules.about.about_page.AboutPage",
}

# 系统菜单（不在模块网格重复展示时可从 toolbar 进）
SYSTEM_ACTIONS = ("system_settings", "theme_preview")


def group_label(group_id: str | None) -> str:
    gid = str(group_id or "business").strip().lower()
    return GROUP_LABELS.get(gid, "其它")


def visible_menu_items() -> list[dict[str, Any]]:
    """侧栏/首页可见菜单（按授权过滤）。"""
    from services.access_control import filter_menu_items

    try:
        from services.license_manager import global_license_manager

        if global_license_manager.is_admin_user():
            return filter_menu_items(all_menu_items())
    except Exception:
        pass
    return filter_menu_items(get_menu_items())


def all_menu_items() -> list[dict[str, Any]]:
    """未过滤的完整菜单（设置页功能清单 / 审计用，含 show:false）。"""
    return get_all_menu_items()


def grouped_menu_items(
    *,
    licensed_only: bool = True,
    migrated_only: bool = False,
) -> list[tuple[str, str, list[dict]]]:
    """返回 [(group_id, group_label, items)] 按 GROUP_ORDER 排序。"""
    admin_all = False
    try:
        from services.license_manager import global_license_manager

        admin_all = global_license_manager.is_admin_user()
    except Exception:
        pass
    items = visible_menu_items() if licensed_only else all_menu_items()
    if migrated_only:
        items = [i for i in items if is_migrated(str(i.get("id") or ""))]
    # all_menu_items 含 show:false；管理员默认全部可见
    if not licensed_only and not admin_all:
        items = [
            i
            for i in items
            if i.get("show", True) or str(i.get("id") or "") in SYSTEM_ACTIONS
        ]
    buckets: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    other: list[dict] = []
    for item in items:
        g = str(item.get("group") or "business").lower()
        if g in buckets:
            buckets[g].append(item)
        else:
            other.append(item)
    out: list[tuple[str, str, list[dict]]] = []
    for g in GROUP_ORDER:
        if buckets[g]:
            out.append((g, group_label(g), buckets[g]))
    if other:
        out.append(("other", "其它", other))
    return out


def is_migrated(module_id: str) -> bool:
    if module_id in MIGRATED_MODULES:
        return True
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
