# -*- coding: utf-8 -*-
"""按菜单项创建业务页实例。"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from core.base_page import BasePage
from core.exceptions import ModuleLoadError
from modules.stub.stub_page import StubPage
from services.menu_registry import MIGRATED_MODULES

logger = logging.getLogger(__name__)


def _import_page_class(dotted: str) -> type:
    if "." not in dotted:
        raise ModuleLoadError(dotted, f"无效模块路径: {dotted}")
    module_name, class_name = dotted.rsplit(".", 1)
    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
    except Exception as e:
        raise ModuleLoadError(dotted, f"无法加载 {dotted}: {e}") from e
    if not issubclass(cls, BasePage):
        raise ModuleLoadError(dotted, f"{dotted} 不是 BasePage 子类")
    return cls


def create_page(module_id: str, menu_item: dict[str, Any] | None = None) -> BasePage:
    """为菜单 id 创建页面；stub 清单项返回迁移占位页。"""
    item = menu_item or {}
    name = str(item.get("name") or module_id)
    desc = str(item.get("desc") or "")

    from services.migration_manifest import get_module_meta, is_stub

    if is_stub(module_id):
        from modules.stub.migration_placeholder_page import MigrationPlaceholderPage

        page = MigrationPlaceholderPage(module_id, name, desc, get_module_meta(module_id))
        logger.info("加载迁移占位页: %s", module_id)
        return page

    dotted = MIGRATED_MODULES.get(module_id)
    if dotted:
        try:
            cls = _import_page_class(dotted)
            page = cls()
            logger.info("加载模块页: %s (%s)", module_id, dotted)
            return page
        except ModuleLoadError as e:
            logger.warning("迁移模块加载失败，使用占位页: %s (%s)", module_id, e)
            return StubPage(
                module_id,
                name,
                desc,
                load_error=str(e),
            )
        except Exception as e:
            logger.exception("模块实例化失败 %s: %s", module_id, e)
            return StubPage(
                module_id,
                name,
                desc,
                load_error=f"{type(e).__name__}: {e}",
            )

    # 用户业务插件包（data/user/plugins.yml）
    try:
        from services.plugin_registry import get_plugin_record

        if get_plugin_record(module_id) or str(item.get("source") or "") == "user_plugin":
            from services.plugin_loader import create_plugin_page

            page = create_plugin_page(module_id, item)
            logger.info("加载用户插件页: %s", module_id)
            return page
    except ModuleLoadError as e:
        logger.warning("用户插件加载失败: %s (%s)", module_id, e)
        return StubPage(module_id, name, desc, load_error=str(e))
    except Exception as e:
        logger.exception("用户插件实例化失败 %s: %s", module_id, e)
        return StubPage(
            module_id,
            name,
            desc,
            load_error=f"{type(e).__name__}: {e}",
        )

    return StubPage(module_id, name, desc)
