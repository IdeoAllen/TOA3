# -*- coding: utf-8 -*-
"""系统设置：分类页签（外观 / 授权 / 热键 / 能力接入 / 运行诊断）。

页签内容懒加载：首次打开只建「外观与品牌」，切换到其它页签再构建，
避免授权名单 / 菜单编辑 / 能力总览 / 日志读取拖慢进入速度。

定时任务与通知已拆到系统侧栏独立模块：job_scheduler / notifications。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.theme_loader import apply_theme, theme_display_name
from core.base_page import BasePage
from core.status_service import StatusLevel
from services.config_service import get_ui_config, resolve_path, save_ui_theme
from services.icon_registry import brand_logo_pixmap
from services.log_view_service import log_file_path, read_log_tail
from services.system_info import get_system_info, log_directory
from services.theme_catalog import selectable_themes, theme_description
from services.user_system_info import save_user_overrides
from core.ui_spec import page_content_margins
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    TabWidget,
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
        self._theme_combo: ComboBox | None = None
        self._theme_desc: HintLabel | None = None
        self._lazy_hosts: list[_LazyTabHost] = []

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(10)

        header = PageHeader(
            "系统设置",
            "按分类管理：外观 · 授权 · 菜单 · 快捷键 · 能力接入 · 运行诊断。"
            "定时任务与通知见系统侧栏「任务」「通知」。",
        )
        outer.addWidget(header)

        self._tabs = TabWidget()
        outer.addWidget(self._tabs, 1)

        # 首屏只建外观；其余懒加载
        appearance = _wrap_scroll(self._build_system_info_box(), self._build_theme_box())
        self._tabs.addTab(appearance, "外观与品牌")

        self._add_lazy_tab("授权", self._factory_license)
        self._add_lazy_tab("订阅购买", self._factory_subscription)
        self._add_lazy_tab("菜单", self._factory_menu)
        self._add_lazy_tab("快捷键", self._factory_hotkeys)
        self._add_lazy_tab("能力接入", self._factory_integrations)
        self._add_lazy_tab("运行诊断", self._factory_diagnostics)

        self._tabs.currentChanged.connect(self._on_tab_changed)

        ui = get_ui_config()
        cur = str(ui.get("theme") or "dms_blue")
        if self._theme_combo is not None:
            idx = self._theme_combo.findData(cur)
            if idx >= 0:
                self._theme_combo.setCurrentIndex(idx)
            else:
                self._update_description()

    def _add_lazy_tab(self, title: str, factory: Callable[[], QWidget]) -> None:
        host = _LazyTabHost(factory, self)
        self._lazy_hosts.append(host)
        self._tabs.addTab(host, title)

    def _on_tab_changed(self, index: int) -> None:
        w = self._tabs.widget(index)
        if isinstance(w, _LazyTabHost):
            w.ensure_built()

    def _factory_license(self) -> QWidget:
        from modules.system_settings.license_section import LicenseSection

        return _wrap_scroll(LicenseSection(self))

    def _factory_subscription(self) -> QWidget:
        from modules.system_settings.subscription_section import SubscriptionSection

        return _wrap_scroll(SubscriptionSection(self))

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

    def _factory_integrations(self) -> QWidget:
        from modules.system_settings.integrations_section import IntegrationsSection

        self._integrations = IntegrationsSection(self)
        return self._integrations

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
                f"产品 {info['app_name']} · 版本 {info['app_version']}（版本号由发布包决定）"
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
            HintLabel(
                "也可在顶栏右上角切换：用户图标右侧、齿轮「设置」左侧，"
                "带「主题」二字与调色板图标的按钮，点一下即可选主题。"
            )
        )
        self._theme_desc = HintLabel("")
        box.add_widget(self._theme_desc)

        form = QFormLayout()
        self._theme_combo = ComboBox()
        for tid, label in selectable_themes():
            self._theme_combo.addItem(theme_display_name(tid) or label, tid)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        form.addRow("主题", self._theme_combo)
        box.add_layout(form)
        return box

    def _on_theme_changed(self, _idx: int) -> None:
        if self._applying:
            return
        tid = self._theme_combo.currentData() if self._theme_combo else None
        if not tid:
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
            (self._theme_combo.currentData() if self._theme_combo else None)
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
            f"版本：{info['app_version']}",
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

    def open_capability_tab(self) -> None:
        """外部跳转到「能力接入」。"""
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == "能力接入":
                self._tabs.setCurrentIndex(i)
                w = self._tabs.widget(i)
                if isinstance(w, _LazyTabHost):
                    w.ensure_built()
                break

    def open_license_tab(self) -> None:
        """外部跳转到「授权」。"""
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == "授权":
                self._tabs.setCurrentIndex(i)
                w = self._tabs.widget(i)
                if isinstance(w, _LazyTabHost):
                    w.ensure_built()
                break

    def on_enter(self) -> None:
        # 仅同步主题选择，不读日志、不联网探测
        if self._theme_combo is None:
            self.report_status("系统设置")
            return
        self._applying = True
        ui = get_ui_config()
        cur = str(ui.get("theme") or "dms_blue")
        idx = self._theme_combo.findData(cur)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._update_description()
        self._applying = False
        self.report_status("系统设置")
