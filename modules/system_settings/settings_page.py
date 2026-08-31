# -*- coding: utf-8 -*-
"""系统设置：按角色展示左侧菜单 + 内容区。

菜单懒加载：首次选中再构建。定时任务 / 通知 / 扩展见系统侧栏对应模块。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.theme_loader import apply_theme, theme_display_name
from core.base_page import BasePage
from core.status_service import StatusLevel
from services.config_service import get_ui_config, resolve_path, save_ui_theme
from services.icon_registry import brand_logo_pixmap
from services.log_view_service import log_file_path, read_log_tail
from services.system_info import get_system_info, log_directory
from services.theme_catalog import theme_description
from services.user_system_info import save_user_overrides
from services.settings_access import (
    TAB_BRAND,
    TAB_DIAGNOSTICS,
    TAB_INTEGRATIONS,
    TAB_LICENSE,
    TAB_MENU,
    TAB_MODELS,
    TAB_OPS_CONSOLE,
    TAB_PREFERENCES,
    TAB_SUBSCRIPTION,
    TAB_SYSTEM,
    capability_settings_tab_key,
    license_settings_tab_key,
    resolve_settings_menu_key,
    settings_header_subtitle,
    subscription_tab_visible,
)
from services.icon_registry import menu_item_icon
from services.settings_menu import (
    SettingsMenuItem,
    settings_menu_groups,
    settings_menu_item,
    settings_nav_icon_size,
)
from core.ui_spec import page_content_margins
from widgets import (
    CheckBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    ThemePicker,
)


def _wrap_scroll(*widgets) -> ScrollPage:
    # 外层 SettingsPage 已有页边距，避免双重左边距
    scroll = ScrollPage(padded=False)
    for w in widgets:
        if isinstance(w, QWidget):
            scroll.add_widget(w)
        else:
            scroll.add_layout(w)
    scroll.add_stretch(1)
    return scroll


class _LazyTabHost(QWidget):
    """占位宿主：首次显示时调用 factory 填充。"""

    def __init__(self, factory: Callable[[], QWidget], parent=None) -> None:
        super().__init__(parent)
        self._factory = factory
        self._built = False
        self._child: QWidget | None = None
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

    def ensure_built(self) -> QWidget | None:
        if self._built:
            return self._child
        child = self._factory()
        self._lay.addWidget(child, 1)
        self._child = child
        self._built = True
        return child


class SettingsPage(BasePage):
    page_id = "system_settings"
    page_title = "系统设置"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._applying = False
        self._logo: QLabel | None = None
        self._info_fields: dict[str, LineEdit] = {}
        self._integrations = None
        self._log_view: ReadOnlyPlainTextEdit | None = None
        self._theme_picker: ThemePicker | None = None
        self._theme_desc: HintLabel | None = None
        self._lazy_hosts: list[_LazyTabHost] = []
        self._menu_keys: dict[str, int] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._current_menu_key = TAB_SYSTEM

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(6)

        self._header = PageHeader("系统设置", settings_header_subtitle())
        outer.addWidget(self._header)

        body = QHBoxLayout()
        body.setSpacing(12)

        self._nav_host = QWidget()
        self._nav_host.setFixedWidth(200)
        self._nav_col = QVBoxLayout(self._nav_host)
        self._nav_col.setSpacing(4)
        self._nav_col.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._build_settings_nav()

        self._nav_col.addStretch(1)
        body.addWidget(self._nav_host)
        body.addWidget(self._stack, 1)
        outer.addLayout(body, 1)

        QTimer.singleShot(0, lambda: self._select_menu(TAB_SYSTEM))

        ui = get_ui_config()
        cur = str(ui.get("theme") or "dms_blue")
        if self._theme_picker is not None:
            self._theme_picker.set_theme(cur)
            self._update_description()

    def _factory_for(self, key: str) -> Callable[[], QWidget]:
        factories: dict[str, Callable[[], QWidget]] = {
            TAB_SYSTEM: self._factory_system,
            TAB_PREFERENCES: self._factory_preferences,
            TAB_MODELS: self._factory_models,
            TAB_BRAND: self._factory_brand,
            TAB_LICENSE: self._factory_license,
            TAB_MENU: self._factory_menu,
            TAB_INTEGRATIONS: self._factory_integrations_admin,
            TAB_DIAGNOSTICS: self._factory_diagnostics,
            TAB_SUBSCRIPTION: self._factory_subscription,
            TAB_OPS_CONSOLE: self._factory_ops_console,
        }
        factory = factories.get(key)
        if factory is None:
            raise KeyError(key)
        return factory

    def _build_settings_nav(self) -> None:
        icon_size = settings_nav_icon_size()
        first_group = True
        for group in settings_menu_groups():
            if not first_group and group.label:
                self._nav_col.addSpacing(6)
            if group.label:
                self._nav_col.addWidget(HintLabel(group.label))
            first_group = False
            for item in group.items:
                self._add_menu_item(item, icon_size)

    def _add_menu_item(self, item: SettingsMenuItem, icon_size: int) -> None:
        key = item.key
        host = _LazyTabHost(self._factory_for(key), self)
        self._lazy_hosts.append(host)
        idx = self._stack.addWidget(host)
        self._menu_keys[key] = idx

        btn = QPushButton(item.title)
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setProperty("navItem", "true")
        btn.setIcon(menu_item_icon(item.icon, size=icon_size, parent=self))
        btn.setIconSize(QSize(icon_size, icon_size))
        if item.subtitle:
            btn.setToolTip(item.subtitle)
        btn.clicked.connect(lambda _=False, k=key: self._select_menu(k))
        self._nav_buttons[key] = btn
        self._nav_col.addWidget(btn)

    def _select_menu(self, key: str) -> None:
        idx = self._menu_keys.get(key)
        if idx is None:
            return
        self._current_menu_key = key
        self._stack.setCurrentIndex(idx)
        w = self._stack.widget(idx)
        if isinstance(w, _LazyTabHost):
            w.ensure_built()
        for mk, btn in self._nav_buttons.items():
            btn.setChecked(mk == key)
        self._sync_theme_selection()
        meta = settings_menu_item(key)
        title = meta.title if meta else key
        if meta and meta.subtitle:
            self._header.set_hint(meta.subtitle)
        self.report_status(f"系统设置 · {title}")

    def open_tab(self, key: str) -> bool:
        menu_key = resolve_settings_menu_key(key)
        if menu_key not in self._menu_keys:
            menu_key = TAB_SYSTEM if TAB_SYSTEM in self._menu_keys else next(iter(self._menu_keys), "")
        if not menu_key:
            return False
        self._select_menu(menu_key)
        return True

    def _factory_preferences(self) -> QWidget:
        parts: list = [
            self._build_theme_box(),
            self._build_nav_pref_box(),
        ]
        from modules.system_settings.hotkeys_section import HotkeysSection

        parts.append(HotkeysSection(self))
        return _wrap_scroll(*parts)

    def _factory_models(self) -> QWidget:
        from modules.system_settings.model_registry_section import ModelRegistrySection

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._integrations = ModelRegistrySection(self)
        self._integrations.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(self._integrations, 1)
        return host

    def _factory_system(self) -> QWidget:
        from modules.system_settings.system_section import SystemSection

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(SystemSection(self), 1)
        return host

    def _sync_theme_selection(self) -> None:
        if self._theme_picker is None:
            return
        self._applying = True
        ui = get_ui_config()
        cur = str(ui.get("theme") or "dms_blue")
        self._theme_picker.set_theme(cur)
        self._update_description()
        self._applying = False

    def _factory_brand(self) -> QWidget:
        return _wrap_scroll(self._build_system_info_box())

    def _factory_license(self) -> QWidget:
        from modules.system_settings.license_section import LicenseSection

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        section = LicenseSection(self)
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(section, 1)
        return host

    def _factory_subscription(self) -> QWidget:
        from modules.system_settings.activation_section import ActivationSection
        from modules.system_settings.subscription_section import SubscriptionSection

        return _wrap_scroll(ActivationSection(self), SubscriptionSection(self))

    def _factory_ops_console(self) -> QWidget:
        from modules.system_settings.ops_console_section import OpsConsoleSection

        return _wrap_scroll(OpsConsoleSection(self))

    def _factory_menu(self) -> QWidget:
        from modules.system_settings.menu_section import MenuSection

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        section = MenuSection(self)
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(section, 1)
        return host

    def _factory_hotkeys(self) -> QWidget:
        from modules.system_settings.hotkeys_section import HotkeysSection

        return _wrap_scroll(HotkeysSection(self))

    def _factory_integrations_admin(self) -> QWidget:
        from modules.system_settings.integrations_section import IntegrationsSection

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        section = IntegrationsSection(self, admin=True)
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(section, 1)
        return host

    def _factory_integrations_user(self) -> QWidget:
        return self._factory_models()

    def _factory_app_update(self) -> QWidget:
        return self._factory_system()

    def _factory_app(self) -> QWidget:
        return self._factory_system()

    def _factory_about_app(self) -> QWidget:
        return self._factory_system()

    def _factory_diagnostics(self) -> QWidget:
        # 不用外层 ScrollPage：日志框本身可滚，并吃满页签剩余高度
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self._build_runtime_box())
        lay.addWidget(self._build_diagnostics_box(), 1)
        self._refresh_log_view(report=False)
        return host

    def _build_diagnostics_box(self) -> FormSection:
        box = FormSection("诊断 · 日志")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        box.add_widget(HintLabel(f"日志文件：{log_file_path()}"))
        self._log_view = ReadOnlyPlainTextEdit()
        self._log_view.setMinimumHeight(420)
        self._log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        box.add_widget(self._log_view, 1)

        row = QHBoxLayout()
        btn_refresh = PrimaryButton("刷新日志")
        btn_refresh.clicked.connect(lambda: self._refresh_log_view(report=True))
        row.addWidget(btn_refresh)
        btn_open = SecondaryButton("在系统中打开日志")
        btn_open.clicked.connect(self._open_log_file)
        row.addWidget(btn_open)
        row.addStretch(1)
        box.add_layout(row)
        return box

    def _build_system_info_box(self) -> FormSection:
        box = FormSection("系统信息 · 用户维护")
        box.add_widget(
            HintLabel(
                "保存后写入 data/user/system_info.json，覆盖 app.yml 默认值；"
                "关于页与顶栏品牌将同步更新。"
            )
        )

        form = QFormLayout()
        info = get_system_info()

        row = QHBoxLayout()
        self._logo = QLabel()
        self._logo.setFixedSize(72, 72)
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_logo_preview()
        row.addWidget(self._logo)
        row.addWidget(
            HintLabel(
                f"产品 {info['app_name']}（版本号由发布包决定，见关于与状态栏）"
            )
        )
        row.addStretch(1)
        form.addRow("概览", row)

        field_defs = (
            ("brand_name", "品牌名称", info.get("brand_name")),
            ("brand_alias", "品牌别名", info.get("brand_alias")),
            ("brand_abbreviation", "品牌缩写", info.get("brand_abbreviation")),
            ("brand_name_en", "英文名称", info.get("brand_name_en")),
            ("author", "作者", info.get("author")),
            ("author_email", "联系邮箱", info.get("author_email")),
            ("slogan", "标语", info.get("slogan")),
            ("slogan_subtitle", "副标语", info.get("slogan_subtitle")),
            ("app_logo_path", "Logo 路径", info.get("app_logo_path") or "avatars/logo.png"),
        )
        for key, label, value in field_defs:
            edit = LineEdit(str(value or ""))
            self._info_fields[key] = edit
            form.addRow(label, edit)

        actions = QHBoxLayout()
        btn_save = PrimaryButton("保存系统信息")
        btn_save.clicked.connect(self._save_system_info)
        actions.addWidget(btn_save)
        btn_reload = SecondaryButton("重新加载")
        btn_reload.clicked.connect(self._reload_system_info_fields)
        actions.addWidget(btn_reload)
        btn_preview = SecondaryButton("刷新 Logo 预览")
        btn_preview.clicked.connect(self._refresh_logo_preview)
        actions.addWidget(btn_preview)
        actions.addStretch(1)
        form.addRow("", actions)

        box.add_layout(form)
        return box

    def _reload_system_info_fields(self) -> None:
        info = get_system_info()
        mapping = {
            "brand_name": info.get("brand_name"),
            "brand_alias": info.get("brand_alias"),
            "brand_abbreviation": info.get("brand_abbreviation"),
            "brand_name_en": info.get("brand_name_en"),
            "author": info.get("author"),
            "author_email": info.get("author_email"),
            "slogan": info.get("slogan"),
            "slogan_subtitle": info.get("slogan_subtitle"),
            "app_logo_path": info.get("app_logo_path") or "avatars/logo.png",
        }
        for key, edit in self._info_fields.items():
            edit.setText(str(mapping.get(key) or ""))
        self._refresh_logo_preview()
        self.report_status("已重新加载系统信息")

    def _refresh_logo_preview(self) -> None:
        if self._logo is None:
            return
        pix = brand_logo_pixmap(64, 64, parent=self)
        if pix.isNull():
            self._logo.setText("无 Logo")
        else:
            self._logo.setPixmap(pix)

    def _save_system_info(self) -> None:
        data = {key: edit.text().strip() for key, edit in self._info_fields.items()}
        if not data.get("brand_name"):
            from core.user_messages import show_warning

            show_warning(self, "品牌名称不能为空。")
            return

        def _do_save() -> None:
            save_user_overrides(data)
            self._refresh_logo_preview()
            shell = self.window()
            if shell is not None and hasattr(shell, "refresh_brand_chrome"):
                shell.refresh_brand_chrome()

        self.run_safe(_do_save, success_status="系统信息已保存")

    def _build_theme_box(self) -> FormSection:
        box = FormSection("主题与外观")
        box.add_widget(
            HintLabel("点击下方主题按钮即时切换；当前主题说明见下方。")
        )
        self._theme_picker = ThemePicker()
        self._theme_picker.theme_selected.connect(self._on_theme_picked)
        box.add_widget(self._theme_picker)
        self._theme_desc = HintLabel("")
        self._theme_desc.setWordWrap(True)
        box.add_widget(self._theme_desc)
        ui = get_ui_config()
        cur = str(ui.get("theme") or "dms_blue")
        self._theme_picker.set_theme(cur)
        self._update_description()
        return box

    def _build_nav_pref_box(self) -> FormSection:
        from services.config_service import nav_default_collapsed

        box = FormSection("二级菜单")
        box.add_widget(
            HintLabel(
                "控制左侧功能侧栏（二级菜单）启动时的默认状态；"
                "运行中仍可用侧栏折叠按钮随时切换。"
            )
        )
        self._nav_default_collapsed = CheckBox("默认折叠（关着）")
        self._nav_default_collapsed.setToolTip(
            "勾选：启动时收起二级菜单，内容区更大；取消：启动时展开二级菜单。"
        )
        self._nav_default_collapsed.setChecked(nav_default_collapsed())
        self._nav_default_collapsed.toggled.connect(self._on_nav_default_collapsed)
        box.add_widget(self._nav_default_collapsed)
        return box

    def _on_nav_default_collapsed(self, checked: bool) -> None:
        from services.config_service import save_ui_values

        save_ui_values(nav_default_collapsed=bool(checked))
        shell = self.window()
        if shell is not None and hasattr(shell, "set_nav_collapsed"):
            shell.set_nav_collapsed(bool(checked), show_rail=True)
        self.report_status(
            "二级菜单默认折叠已开启" if checked else "二级菜单默认展开已开启",
            level=StatusLevel.SUCCESS,
        )

    def _on_theme_picked(self, tid: str) -> None:
        if self._applying or not tid:
            return
        self._update_description()
        shell = self.window()
        if shell is not None and hasattr(shell, "apply_user_theme"):
            shell.apply_user_theme(str(tid))
            return
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, str(tid))
            save_ui_theme(str(tid))
            self.report_status(
                f"已切换主题：{theme_display_name(str(tid))}",
                level=StatusLevel.SUCCESS,
            )

    def _update_description(self) -> None:
        if self._theme_desc is None:
            return
        tid = (
            (self._theme_picker.current_theme() if self._theme_picker else None)
            or get_ui_config().get("theme")
            or "dms_blue"
        )
        self._theme_desc.setText(theme_description(str(tid)))

    def _build_runtime_box(self) -> FormSection:
        from services.config_service import project_root

        box = FormSection("运行环境")
        root = project_root()
        info = get_system_info()
        lines = [
            f"项目根：{root}",
            f"数据目录：{resolve_path('data_dir')}",
            f"输出目录：{resolve_path('output_dir')}",
            f"日志目录：{log_directory()}",
            f"Python：{sys.executable}",
        ]
        box.add_widget(HintLabel("\n".join(lines)))

        row = QHBoxLayout()
        btn_folder = SecondaryButton("打开日志目录")
        btn_folder.clicked.connect(self._open_log_dir)
        row.addWidget(btn_folder)
        btn_data = SecondaryButton("打开数据目录")
        btn_data.clicked.connect(lambda: self._open_path(resolve_path("data_dir")))
        row.addWidget(btn_data)
        row.addStretch(1)
        box.add_layout(row)
        return box

    def _open_path(self, path) -> None:
        p = Path(path)
        if not p.exists():
            from core.user_messages import show_warning

            show_warning(self, f"路径不存在：{p}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(p))  # noqa: S606
            else:
                subprocess.run(["xdg-open", str(p)], check=False)
        except Exception as e:
            from core.user_messages import show_error

            show_error(self, f"无法打开：{e}")

    def _open_log_dir(self) -> None:
        self._open_path(log_directory())

    def _open_log_file(self) -> None:
        self._open_path(log_file_path())

    def _refresh_log_view(self, *, report: bool = True) -> None:
        if self._log_view is None:
            return
        self._log_view.setPlainText(read_log_tail())
        if report:
            self.report_status("已刷新日志预览")

    def open_model_hub_tab(self) -> None:
        """外部跳转到模型管理。"""
        self.open_models_tab()

    def open_capability_tab(self, *, image: bool = False) -> None:
        """外部跳转到模型管理。"""
        self.open_models_tab()
        if image and self._integrations is not None and hasattr(
            self._integrations, "set_capability_filter"
        ):
            self._integrations.set_capability_filter("image_gen")

    def open_license_or_subscription(self) -> None:
        from services.settings_access import subscription_tab_visible

        if subscription_tab_visible():
            self.open_subscription_tab()
        else:
            self.open_license_tab()

    def open_license_tab(self) -> None:
        """外部跳转到授权（管理员）或订阅（终端用户）。"""
        self.open_tab(license_settings_tab_key())

    def open_subscription_tab(self) -> None:
        from services.settings_access import subscription_tab_visible

        if subscription_tab_visible():
            self.open_tab(TAB_SUBSCRIPTION)
        else:
            self.open_app_update_tab()

    def open_app_update_tab(self) -> None:
        self.open_tab(TAB_SYSTEM)

    def open_system_tab(self) -> None:
        self.open_tab(TAB_SYSTEM)

    def open_extensions_tab(self) -> None:
        """兼容旧入口：跳到系统侧栏「扩展」模块。"""
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            try:
                shell.navigate("user_extensions")
                return
            except Exception:
                pass
        from core.user_messages import show_warning

        show_warning(self, "请到顶栏「系统」→ 侧栏「扩展」。")

    def open_models_tab(self) -> None:
        self.open_tab(TAB_MODELS)

    def open_about_tab(self) -> None:
        shell = self.window()
        if shell is not None and hasattr(shell, "_show_about"):
            shell._show_about()
            return
        self.open_tab(TAB_SYSTEM)

    def on_enter(self) -> None:
        self._select_menu(self._current_menu_key or TAB_SYSTEM)
        self.report_status("系统设置")

    def open_preferences_tab(self) -> None:
        self.open_tab(TAB_PREFERENCES)
