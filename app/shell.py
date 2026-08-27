# -*- coding: utf-8 -*-
"""主应用壳：顶栏、快捷条、侧栏导航、模块宿主、状态栏。"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QSize, QEvent
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.app_state import AppState
from app.module_loader import create_page
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import apply_shell_spec, shell_spec
from services.config_service import get_hotkeys_config, get_menu_item_by_id, get_ui_config
from services.icon_registry import brand_logo_pixmap, clear_cache, get_header_icon, get_icon, menu_item_icon
from services.menu_registry import (
    DOMAIN_TAB_LABELS,
    GROUP_ORDER,
    SYSTEM_ACTIONS,
    grouped_menu_items,
)
from services.access_control import can_open
from services.notify_bus import get_bus
from services.job_scheduler import get_scheduler
from services.tray_service import get_tray
from services.hotkey_service import get_hotkey_service
from services.screenshot_service import run_screenshot_hotkey
from core.user_messages import show_warning

logger = logging.getLogger(__name__)

_HEADER_LOGO = 44
_HEADER_ICON = 18
_HEADER_BTN = 30
_NAV_ICON = 22
_QUICK_ICON = 20
_MENU_ICON = 18
_NAV_RAIL_WIDTH = 4


def _lum_hex(hex_c: str) -> float:
    h = str(hex_c or "").lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast_hex(a: str, b: str) -> float:
    la, lb = _lum_hex(a), _lum_hex(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class _ThemeToolButton(QToolButton):
    """顶栏主题按钮：悬停滚轮快速切换。"""

    def __init__(self, on_wheel_step, parent=None) -> None:
        super().__init__(parent)
        self._on_wheel_step = on_wheel_step

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta != 0 and self._on_wheel_step is not None:
            # 滚轮向上 → 上一主题；向下 → 下一主题
            self._on_wheel_step(-1 if delta > 0 else 1)
            event.accept()
            return
        super().wheelEvent(event)


class _ShellNavKeyFilter(QObject):
    """←/→ 切子模块、↑/↓ 切侧栏；列表/浏览器内不抢方向键。"""

    def __init__(self, shell: "MainShell") -> None:
        super().__init__(shell)
        self._shell = shell

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        if key not in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            return False
        if not self._shell._should_handle_nav_keys():
            return False
        if self._shell.handle_shell_arrow_key(key):
            return True
        return False


class MainShell(QMainWindow):
    """TOA3 主窗口壳。"""

    def __init__(self, *, defer_startup: bool = False) -> None:
        super().__init__()
        self._st = AppState.get()
        ui = get_ui_config()
        self._startup_complete = False

        title = str(ui.get("window_title") or self._st.brand_name())
        try:
            from services.edition_profile import window_title_suffix

            suffix = window_title_suffix()
        except Exception:
            suffix = ""
        self.setWindowTitle(f"{title} · TOA3{suffix}")

        apply_shell_spec(self)
        self._shell_spec = shell_spec()

        self._pages: dict[str, BasePage] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_items: dict[str, dict] = {}
        self._nav_group_headers: dict[str, QPushButton] = {}
        self._nav_group_members: dict[str, list[str]] = {}
        self._nav_group_labels: dict[str, str] = {}
        self._nav_group_expanded: dict[str, bool] = {}
        self._module_groups: dict[str, str] = {}
        self._current_domain: str = "home"
        self._domain_buttons: dict[str, QToolButton] = {}
        self._menu_meta: dict[str, dict] = {}  # 懒加载：仅登记元数据
        self._current_id: str = ""
        self._status_user_label: QLabel | None = None
        self._status_ver_label: QLabel | None = None
        self._last_status_level = StatusLevel.READY
        self._header_icon_buttons: list[tuple[QToolButton, str]] = []
        self._quick_buttons: list[tuple[QToolButton, str, str]] = []
        self._outer_layout: QVBoxLayout | None = None
        self._header: QWidget | None = None
        self._quick_bar: QWidget | None = None
        self._focus_exit_bar: QWidget | None = None
        self._chrome_focus = False
        self._hotkey_actions: list[QAction] = []
        self._page_shortcuts: list[QShortcut] = []
        self._brand_label: QLabel | None = None
        self._header_logo_label: QLabel | None = None
        self._user_btn: QToolButton | None = None

        self._build_chrome()
        self._build_quick_bar()
        self._register_hotkeys()
        self._load_modules()
        self.rebuild_nav()
        self._build_status_bar()
        self._install_nav_key_filter()

        # 隐藏系统原生菜单栏，快捷条 + 侧栏承担导航
        mb = self.menuBar()
        mb.setVisible(False)
        mb.setNativeMenuBar(False)

        self._close_to_tray = bool(get_hotkeys_config().get("close_to_background", True))
        if not defer_startup:
            self.complete_startup()

    def complete_startup(self) -> None:
        """托盘/热键/首页：先 show 主窗再调用，避免登录后长时间无界面。"""
        if self._startup_complete:
            return
        self._startup_complete = True
        logger.info("主壳完成启动：接入平台服务")
        self._wire_platform()
        ui = get_ui_config()
        start = str(ui.get("default_start_tab") or "home")
        self.navigate(start)
        if ui.get("default_fullscreen"):
            self.showMaximized()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(600, self._maybe_prompt_renew_on_start)

    def _maybe_prompt_renew_on_start(self) -> None:
        try:
            from services.license_manager import global_license_manager
            from services.subscription_renew import is_renewable_block, renew_profile
            from app.renew_dialog import offer_renew_dialog

            lm = global_license_manager
            if lm.is_licensed():
                return
            text = lm.get_validity_text()
            if not is_renewable_block(text):
                return
            prof = renew_profile()
            if lm.is_standalone_mode() and not prof.get("phone"):
                return
            offer_renew_dialog(self, message=text)
        except Exception:
            pass

    def _wire_platform(self) -> None:
        """权限重建、通知总线、托盘、全局热键、定时任务。"""
        bus = get_bus()
        bus.nav_rebuild_requested.connect(self._on_nav_rebuild)
        bus.license_changed.connect(self._on_license_changed)
        bus.status.connect(self._on_bus_status)

        from services.license_watchdog import start_license_watchdog

        start_license_watchdog(self)

        get_scheduler().start_all()

        # 启动剪贴板自动捕获（托盘隐藏时仍监听）
        from modules.clipboard_history.clipboard_watcher import get_clipboard_watcher

        get_clipboard_watcher()

        tray = get_tray()
        tray.start(
            tip=f"{self._st.brand_name()} TOA3",
            on_show=self._show_from_tray,
            on_notepad=lambda: self._summon_module("quick_notepad"),
            on_pomodoro=lambda: self._summon_module("pomodoro"),
            on_clipboard=self._open_clipboard_quick,
            on_screenshot=lambda: run_screenshot_hotkey(self, full=False),
            on_screenshot_full=lambda: run_screenshot_hotkey(self, full=True),
            on_ocr=self._run_ocr_hotkey,
            on_restart=self._restart_app,
            on_exit=self._quit_app,
        )

        hk = get_hotkeys_config()
        bindings = {}
        if hk.get("enable_screenshot", True):
            if hk.get("screenshot"):
                bindings[str(hk["screenshot"])] = lambda: run_screenshot_hotkey(self, full=False)
            if hk.get("screenshot_region"):
                bindings[str(hk["screenshot_region"])] = lambda: run_screenshot_hotkey(
                    self, full=True
                )
        from services.module_hotkeys import global_module_bindings

        for seq, mid in global_module_bindings().items():
            # 截图等已占用的键不得被「打开模块」覆盖（曾导致 Alt+A 只进页不截图）
            if seq in bindings:
                continue
            if mid == "ocr_tool":
                bindings[seq] = self._run_ocr_hotkey
            elif mid == "clipboard_history":
                bindings[seq] = self._open_clipboard_quick
            else:
                bindings[seq] = lambda m=mid: self._summon_module(m)
        try:
            from services.edition_isolation import should_register_global_hotkeys

            ok, reason = should_register_global_hotkeys()
            if not ok:
                logger.info("跳过全局热键注册: %s", reason)
                bindings = {}
        except Exception:
            pass
        errs = get_hotkey_service().apply(bindings)
        if errs:
            logger.info("全局热键部分失败: %s", errs)

    def _run_ocr_hotkey(self) -> None:
        from services.screenshot_service import run_screenshot_ocr

        run_screenshot_ocr(self, full=False)
        self.navigate("ocr_tool")
        self._show_from_tray()

    def _on_bus_status(self, text: str, level: str) -> None:
        lvl = {
            "info": StatusLevel.INFO,
            "success": StatusLevel.SUCCESS,
            "warning": StatusLevel.WARNING,
            "error": StatusLevel.ERROR,
        }.get(level, StatusLevel.INFO)
        self.show_status(text, level=lvl)

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        """顶栏退出 / 托盘退出：完全结束进程（不进托盘）。"""
        from services.app_lifecycle import quit_application
        from services.single_instance import release_single_instance

        self._close_to_tray = False
        get_hotkey_service().shutdown()
        get_scheduler().shutdown()
        get_tray().stop()
        release_single_instance()
        quit_application()

    def _restart_app(self) -> None:
        """拉起新进程后完全退出当前实例。"""
        from services.app_lifecycle import quit_application, restart_process
        from services.single_instance import release_single_instance

        self._close_to_tray = False
        get_hotkey_service().shutdown()
        get_scheduler().shutdown()
        get_tray().stop()
        release_single_instance()
        if not restart_process():
            self.show_status("重启失败：无法拉起新进程，请运行 scripts/start_toa3.ps1", level=StatusLevel.ERROR)
            return
        # 稍候再退，给新进程时间占用单实例锁与加载配置
        quit_application(delay_ms=400)

    def closeEvent(self, event) -> None:  # noqa: N802
        # 窗口关闭钮：可按配置进托盘；顶栏「退出」走 _quit_app
        if getattr(self, "_close_to_tray", False) and get_tray()._tray is not None:
            event.ignore()
            self.hide()
            get_tray().show_message(self._st.brand_name(), "已最小化到托盘，双击图标可恢复。")
            return
        from services.single_instance import release_single_instance

        get_hotkey_service().shutdown()
        get_scheduler().shutdown()
        get_tray().stop()
        release_single_instance()
        super().closeEvent(event)

    def _build_chrome(self) -> None:
        spec = self._shell_spec
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._outer_layout = outer

        header = QWidget()
        header.setObjectName("ShellHeader")
        header.setFixedHeight(int(spec.get("header_height") or 48))
        self._header = header
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(16, 0, 10, 0)
        hlay.setSpacing(4)

        from services.system_info import logo_path

        logo_file = logo_path()
        if logo_file is not None:
            logo = QLabel()
            logo.setObjectName("ShellLogo")
            logo.setFixedSize(_HEADER_LOGO, _HEADER_LOGO)
            logo.setScaledContents(False)
            pix = brand_logo_pixmap(_HEADER_LOGO, _HEADER_LOGO, parent=self)
            if not pix.isNull():
                logo.setPixmap(pix)
                logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._header_logo_label = logo
                hlay.addWidget(logo)

        brand = QLabel(self._st.brand_name())
        brand.setObjectName("ShellBrand")
        self._brand_label = brand
        hlay.addWidget(brand)
        hlay.addStretch(1)

        user_name = self._st.display_name or self._st.username or "用户"
        self._user_btn = self._header_icon_button(
            "user", f"账号信息 · {user_name}", self._show_user_profile
        )
        hlay.addWidget(self._user_btn)
        hlay.addWidget(self._build_theme_button())
        hlay.addWidget(
            self._header_icon_button(
                "notifications",
                "通知中心",
                lambda: self.navigate("notifications"),
            )
        )
        hlay.addWidget(
            self._header_icon_button("settings", "系统设置", lambda: self.navigate("system_settings"))
        )
        hlay.addWidget(self._header_icon_button("about", "关于 / 愿景", self._show_about))
        hlay.addWidget(
            self._header_icon_button(
                "fullscreen",
                "沉浸桌面：隐藏顶栏/工具栏/状态栏 (F11)",
                self._toggle_chrome_focus,
            )
        )
        hlay.addWidget(
            self._header_icon_button("restart", "重启应用 (Ctrl+Shift+R)", self._restart_app)
        )
        hlay.addWidget(
            self._header_icon_button("exit", "完全退出 (Ctrl+Q)", self._quit_app, danger=True)
        )

        # 沉浸模式不占用顶栏退出条（Esc/F11 退出）
        self._focus_exit_bar = None

        outer.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav_width = int(spec.get("nav_width") or 200)
        self._nav_collapsed = False

        nav_wrap = QWidget()
        nav_wrap.setObjectName("ShellNav")
        nav_wrap.setFixedWidth(self._nav_width)
        self._nav_wrap = nav_wrap
        nav_outer = QVBoxLayout(nav_wrap)
        nav_outer.setContentsMargins(0, 0, 0, 0)
        nav_outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("ShellNavScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 始终预留滚动条槽位，避免有/无滚动条时右内边距跳动
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        nav_host = QWidget()
        self._nav_layout = QVBoxLayout(nav_host)
        self._nav_layout.setContentsMargins(10, 8, 6, 8)
        self._nav_layout.setSpacing(2)
        scroll.setWidget(nav_host)
        nav_outer.addWidget(scroll, 1)

        collapse_row = QHBoxLayout()
        collapse_row.setContentsMargins(4, 4, 4, 0)
        collapse_row.addStretch(1)
        collapse_btn = QToolButton()
        collapse_btn.setObjectName("NavCollapseBtn")
        collapse_btn.setToolTip("折叠侧栏")
        collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        collapse_btn.setAutoRaise(True)
        collapse_btn.setFixedSize(22, 22)
        collapse_btn.setIconSize(QSize(14, 14))
        collapse_btn.clicked.connect(self._toggle_nav_collapsed)
        collapse_row.addWidget(collapse_btn)
        nav_outer.insertLayout(0, collapse_row)
        self._nav_collapse_btn = collapse_btn
        self._apply_nav_collapse_icon()

        body.addWidget(nav_wrap)

        expand_rail = QToolButton()
        expand_rail.setObjectName("NavExpandRail")
        expand_rail.setToolTip("展开侧栏")
        expand_rail.setFixedWidth(_NAV_RAIL_WIDTH)
        expand_rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        expand_rail.setCursor(Qt.CursorShape.PointingHandCursor)
        expand_rail.setAutoRaise(True)
        expand_rail.setVisible(False)
        expand_rail.clicked.connect(self._toggle_nav_collapsed)
        self._nav_expand_rail = expand_rail
        body.addWidget(expand_rail)

        self._stack = QStackedWidget()
        self._stack.setObjectName("ModuleHost")
        body.addWidget(self._stack, 1)

        outer.addLayout(body, 1)

    def _toggle_nav_collapsed(self) -> None:
        """折叠/展开左侧主菜单，最大化模块可视区。"""
        self.set_nav_collapsed(not self._nav_collapsed)

    def set_nav_collapsed(self, collapsed: bool, *, show_rail: bool = True) -> None:
        self._nav_collapsed = bool(collapsed)
        if self._nav_collapsed:
            self._nav_wrap.setVisible(False)
            if show_rail:
                self._nav_expand_rail.setFixedWidth(_NAV_RAIL_WIDTH)
                self._nav_expand_rail.setVisible(True)
            else:
                self._nav_expand_rail.setVisible(False)
        else:
            self._nav_wrap.setVisible(True)
            self._nav_wrap.setFixedWidth(self._nav_width)
            self._nav_expand_rail.setVisible(False)

    def _show_user_profile(self) -> None:
        from app.user_profile_dialog import UserProfileDialog

        UserProfileDialog(self).exec()

    def _header_icon_button(
        self, icon_name: str, tooltip: str, handler, *, danger: bool = False
    ) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("ShellHeaderBtn")
        if danger:
            btn.setProperty("class", "danger")
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        fg = self._header_icon_color()
        btn.setIcon(get_header_icon(icon_name, color=fg, size=_HEADER_ICON, parent=self))
        btn.setIconSize(QSize(_HEADER_ICON, _HEADER_ICON))
        btn.setFixedSize(_HEADER_BTN, _HEADER_BTN)
        btn.clicked.connect(handler)
        self._header_icon_buttons.append((btn, icon_name))
        return btn

    def _build_theme_button(self) -> QToolButton:
        """顶栏一键换主题（下拉点选；悬停滚轮快速切换）。"""
        btn = _ThemeToolButton(self._cycle_theme_step, self)
        btn.setObjectName("ShellHeaderBtn")
        btn.setToolTip("切换主题（点击选择 · 悬停滚轮快速切换）")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setIcon(
            get_header_icon("theme", color=self._header_icon_color(), size=_HEADER_ICON, parent=self)
        )
        btn.setIconSize(QSize(_HEADER_ICON, _HEADER_ICON))
        btn.setFixedSize(_HEADER_BTN, _HEADER_BTN)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setProperty("hasMenu", "true")
        menu = QMenu(btn)
        menu.aboutToShow.connect(lambda: self._rebuild_theme_menu(menu))
        btn.setMenu(menu)
        self._header_icon_buttons.append((btn, "theme"))
        self._theme_btn = btn
        return btn

    def _cycle_theme_step(self, direction: int) -> None:
        """滚轮切换：direction +1 下一主题，-1 上一主题。"""
        from services.theme_catalog import selectable_themes

        themes = selectable_themes()
        if len(themes) < 2:
            return
        ids = [tid for tid, _ in themes]
        current = str(AppState.get().theme_id or "")
        try:
            idx = ids.index(current)
        except ValueError:
            idx = 0
        n = len(ids)
        step = 1 if direction >= 0 else -1
        new_idx = (idx + step) % n
        self.apply_user_theme(ids[new_idx])

    def _rebuild_theme_menu(self, menu: QMenu) -> None:
        menu.clear()
        from app.app_state import AppState
        from services.theme_catalog import selectable_themes

        current = str(AppState.get().theme_id or "")
        for tid, label in selectable_themes():
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(tid == current)
            act.triggered.connect(lambda _=False, t=tid: self.apply_user_theme(t))
            menu.addAction(act)

    def apply_user_theme(self, theme_id: str) -> None:
        """顶栏 / 设置共用：应用主题并持久化。"""
        from PySide6.QtWidgets import QApplication

        from app.theme_loader import apply_theme
        from services.config_service import save_ui_theme
        from services.theme_catalog import canonicalize_theme

        tid = canonicalize_theme(theme_id)
        app = QApplication.instance()
        if app is None:
            return
        palette = apply_theme(app, tid)
        save_ui_theme(tid)
        self.on_theme_changed(tid, palette)

    def _header_icon_color(self) -> str:
        """顶栏图标跟 header_fg，并与 header_bg 保证可读对比。"""
        pal = self._st.palette or {}
        bg = str(pal.get("header_bg") or pal.get("primary") or "#0F2744")
        fg = str(
            pal.get("header_fg")
            or pal.get("on_primary")
            or pal.get("text_on_primary")
            or "#FFFFFF"
        )
        if _contrast_hex(fg, bg) < 4.5:
            fg = "#FFFFFF" if _lum_hex(bg) < 0.45 else "#1A1A1A"
        return fg

    def _nav_collapse_icon_color(self) -> str:
        """侧栏折叠箭头跟 nav_fg，浅色主题须与 nav_bg 拉开对比。"""
        pal = self._st.palette or {}
        bg = str(pal.get("nav_bg") or pal.get("surface_sidebar") or "#EBEBF0")
        fg = str(pal.get("nav_fg") or pal.get("text_secondary") or "#1D1D1F")
        if _contrast_hex(fg, bg) < 4.5:
            fg = "#FFFFFF" if _lum_hex(bg) < 0.45 else "#1A1A1A"
        return fg

    def _apply_nav_collapse_icon(self) -> None:
        btn = getattr(self, "_nav_collapse_btn", None)
        if btn is None:
            return
        btn.setIcon(
            get_icon("left", color=self._nav_collapse_icon_color(), size=14, parent=self)
        )

    def _build_quick_bar(self) -> None:
        if self._outer_layout is None:
            return

        bar = QWidget()
        bar.setObjectName("ShellSubHeader")
        bar.setFixedHeight(44)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(2)

        self._domain_buttons.clear()
        for group_id in GROUP_ORDER:
            label = DOMAIN_TAB_LABELS.get(group_id, group_id)
            btn = QToolButton()
            btn.setObjectName("ShellDomainBtn")
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setText(label)
            btn.setCheckable(True)
            btn.setToolTip(f"{label}（子模块 · 子系统）")
            btn.clicked.connect(lambda _=False, g=group_id: self.select_domain(g))
            lay.addWidget(btn)
            self._domain_buttons[group_id] = btn

        lay.addStretch(1)

        self._quick_bar = bar
        self._quick_buttons.clear()
        # focus_exit 已移除：header(0) + body → 插在 index 1
        self._outer_layout.insertWidget(1, bar)
        self._rebuild_domain_tabs()
        self._update_domain_tab_checks()

    def _admin_sees_all_nav(self) -> bool:
        try:
            from services.license_manager import global_license_manager

            return bool(global_license_manager.is_admin_user())
        except Exception:
            return False

    def _rebuild_domain_tabs(self) -> None:
        """仅展示有可见模块的域 Tab。"""
        admin_all = self._admin_sees_all_nav()
        visible_groups: set[str] = set()
        for gid, _glab, items in grouped_menu_items(licensed_only=False):
            for item in items:
                mid = str(item.get("id") or "")
                if not mid:
                    continue
                if mid in SYSTEM_ACTIONS and not item.get("show", True) and not admin_all:
                    continue
                if admin_all or item.get("show", True) or mid in SYSTEM_ACTIONS:
                    visible_groups.add(gid)
        for gid, btn in self._domain_buttons.items():
            btn.setVisible(gid in visible_groups)

    def _update_domain_tab_checks(self) -> None:
        for gid, btn in self._domain_buttons.items():
            btn.setChecked(gid == self._current_domain)

    def select_domain(self, group_id: str, *, navigate_first: bool = True) -> None:
        """顶栏子模块（子系统）切换：侧栏只展示该子系统下的功能模块。"""
        gid = str(group_id or "home").strip().lower()
        if gid not in GROUP_ORDER and gid != "other":
            return
        self._current_domain = gid
        self._update_domain_tab_checks()
        self._apply_domain_filter()
        if not navigate_first:
            return
        cur_gid = self._module_groups.get(self._current_id)
        if cur_gid == gid:
            return
        for mid in self._nav_group_members.get(gid, []):
            item = self._nav_items.get(mid) or self._menu_meta.get(mid) or {}
            if not self._nav_item_want_show(mid, item):
                continue
            ok, _ = can_open(mid)
            if ok:
                self.navigate(mid)
                return
        # 有侧栏项但均未授权：提示后留在当前页
        members = self._nav_group_members.get(gid, [])
        if members and gid != "home":
            first = members[0]
            ok, reason = can_open(first)
            if not ok:
                self.show_status(reason or "该子模块需要授权", level=StatusLevel.WARNING)
        if gid == "home":
            self.navigate("home")

    def _sync_domain_for_module(self, module_id: str) -> None:
        gid = self._module_groups.get(module_id)
        if not gid:
            item = self._nav_items.get(module_id) or self._menu_meta.get(module_id) or {}
            gid = str(item.get("group") or "business").lower()
        if gid == self._current_domain:
            return
        self._current_domain = gid
        self._update_domain_tab_checks()
        self._apply_domain_filter()

    def _apply_domain_filter(self) -> None:
        """侧栏二级：仅当前子模块（子系统）下的功能模块。"""
        gid = self._current_domain
        for header_gid, header in self._nav_group_headers.items():
            header.setVisible(False)
        for mid, btn in self._nav_buttons.items():
            if mid in ("__about__",):
                continue
            item = self._nav_items.get(mid) or {}
            in_domain = self._module_groups.get(mid) == gid
            if mid in SYSTEM_ACTIONS and gid == "system":
                in_domain = True
            want_show = self._nav_item_want_show(mid, item)
            btn.setVisible(bool(in_domain and want_show))
            ok, reason = can_open(mid)
            btn.setEnabled(ok)
            tip = str(item.get("desc") or item.get("name") or mid)
            if not ok and reason:
                tip = f"{tip}\n（{reason}）"
            btn.setToolTip(tip)

    def _rebuild_modules_menu(self) -> None:
        """兼容旧调用：域 Tab 模式下改为刷新 Tab 可见性。"""
        self._rebuild_domain_tabs()

    def _register_hotkeys(self) -> None:
        for act in self._hotkey_actions:
            self.removeAction(act)
            act.deleteLater()
        self._hotkey_actions.clear()

        hk = get_hotkeys_config()
        fs_key = str(hk.get("toggle_fullscreen") or "F11").strip()
        mapping = {
            str(hk.get("exit_app") or "Ctrl+Q"): self._quit_app,
            str(hk.get("restart_app") or "Ctrl+Shift+R"): self._restart_app,
            str(hk.get("open_settings") or "Alt+S"): lambda: self.navigate("system_settings"),
            str(hk.get("open_about") or "Alt+Shift+O"): self._show_about,
            fs_key: self._toggle_fullscreen,
            str(hk.get("open_home") or "Ctrl+H"): lambda: self.navigate("home"),
            "Ctrl+K": self._open_command_palette,
        }
        from services.module_hotkeys import get_module_shortcut

        for mid in (
            "quick_notepad",
            "pomodoro",
            "ocr_tool",
            "clipboard_history",
            "harness_agent",
            "column_preview",
        ):
            seq = get_module_shortcut(mid)
            if not seq or seq.lower() == "none":
                continue
            if mid == "column_preview" and seq.upper() == fs_key.upper():
                continue
            if mid == "ocr_tool":
                mapping[seq] = self._run_ocr_hotkey
            elif mid == "clipboard_history":
                mapping[seq] = self._open_clipboard_quick
            elif mid == "column_preview":
                mapping[seq] = self.toggle_immersive
            else:
                mapping[seq] = lambda m=mid: self._summon_module(m)

        if hk.get("enable_screenshot", True):
            from services.screenshot_service import run_screenshot_hotkey

            shot = str(hk.get("screenshot") or "Alt+A")
            shot_full = str(hk.get("screenshot_region") or "Alt+Shift+A")
            if shot and shot.lower() != "none":
                mapping[shot] = lambda: run_screenshot_hotkey(self, full=False)
            if shot_full and shot_full.lower() != "none":
                mapping[shot_full] = lambda: run_screenshot_hotkey(self, full=True)

        summon_id = str(hk.get("summon_module_id") or "").strip()
        tw = str(hk.get("toggle_window") or "").strip()
        if summon_id and tw and tw.lower() != "none":
            mapping[tw] = lambda: self._summon_module(summon_id)

        app_ctx_keys = {fs_key.upper(), "F11"}
        for seq, fn in mapping.items():
            if not seq or seq.lower() == "none":
                continue
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            if seq.upper() in app_ctx_keys:
                act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            act.triggered.connect(fn)
            self.addAction(act)
            self._hotkey_actions.append(act)

        esc = QAction(self)
        esc.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        # 仅主窗前台：避免 ApplicationShortcut 抢走截图浮层的 Esc 取消
        esc.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        esc.triggered.connect(self._escape_immersive)
        self.addAction(esc)
        self._hotkey_actions.append(esc)

    def reload_window_hotkeys(self) -> None:
        """设置页保存后重载应用级快捷键。"""
        self._register_hotkeys()

    def set_page_shortcuts(self, bindings: dict[str, callable] | None) -> None:
        """当前模块页内快捷键（ApplicationShortcut，离开页时清除）。"""
        for sc in self._page_shortcuts:
            sc.deleteLater()
        self._page_shortcuts.clear()
        if not bindings:
            return
        for seq, fn in bindings.items():
            if not seq or str(seq).lower() == "none":
                continue
            sc = QShortcut(QKeySequence(str(seq)), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)
            self._page_shortcuts.append(sc)

    def _focus_in_editable(self) -> bool:
        from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit

        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox))

    def _should_handle_nav_keys(self) -> bool:
        """输入框、列表、内嵌浏览器内不切换菜单。"""
        if self._focus_in_editable():
            return False
        from PySide6.QtWidgets import QApplication, QAbstractItemView

        w = QApplication.focusWidget()
        while w is not None:
            if isinstance(w, QAbstractItemView):
                return False
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView

                if isinstance(w, QWebEngineView):
                    return False
            except ImportError:
                pass
            w = w.parentWidget()
        return True

    def _install_nav_key_filter(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        self._nav_key_filter = _ShellNavKeyFilter(self)
        app.installEventFilter(self._nav_key_filter)

    def jump_menu_group(self, group_id: str) -> None:
        """首页页内键：切子模块并打开该子系统首个可见功能。"""
        if self._focus_in_editable():
            return
        self.select_domain(group_id, navigate_first=True)

    def _visible_domain_ids(self) -> list[str]:
        return [
            gid
            for gid in GROUP_ORDER
            if gid in self._domain_buttons and self._domain_buttons[gid].isVisible()
        ]

    def _visible_nav_module_ids(self) -> list[str]:
        gid = self._current_domain
        out: list[str] = []
        for mid in self._nav_group_members.get(gid, []):
            btn = self._nav_buttons.get(mid)
            if btn is None or not btn.isVisible() or not btn.isEnabled():
                continue
            out.append(mid)
        return out

    def cycle_domain(self, step: int) -> None:
        """←/→：切换顶栏一级子模块。"""
        domains = self._visible_domain_ids()
        if not domains:
            return
        try:
            idx = domains.index(self._current_domain)
        except ValueError:
            idx = 0
        new_gid = domains[(idx + int(step)) % len(domains)]
        self.select_domain(new_gid, navigate_first=True)
        label = DOMAIN_TAB_LABELS.get(new_gid, new_gid)
        self.show_status(f"子模块：{label}", level=StatusLevel.INFO)

    def cycle_nav_module(self, step: int) -> None:
        """↑/↓：切换当前子模块下的侧栏功能模块。"""
        mods = self._visible_nav_module_ids()
        if not mods:
            return
        try:
            idx = mods.index(self._current_id)
        except ValueError:
            idx = 0
        mid = mods[(idx + int(step)) % len(mods)]
        self.navigate(mid)

    def handle_shell_arrow_key(self, key: int) -> bool:
        """←/→ 顶栏子模块 · ↑/↓ 侧栏功能模块。"""
        if not self._should_handle_nav_keys():
            return False
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.cycle_domain(-1 if key == Qt.Key.Key_Left else 1)
            return True
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.cycle_nav_module(-1 if key == Qt.Key.Key_Up else 1)
            return True
        return False

    def _open_command_palette(self) -> None:
        from app.command_palette import open_command_palette

        open_command_palette(self)

    def _open_clipboard_quick(self) -> None:
        """ClipX 式：热键/托盘 → 快速面板（可进完整页）。"""
        try:
            from modules.clipboard_history.clipboard_popup import open_clipboard_quick_popup

            open_clipboard_quick_popup(self)
        except Exception as exc:
            logger.exception("打开剪贴板速贴失败")
            try:
                from core.user_messages import show_error

                show_error(self, f"无法打开剪贴板速贴：{exc}", title="剪贴板")
            except Exception:
                pass
            self.show_status(f"剪贴板速贴失败：{exc}", level=StatusLevel.ERROR)

    def _summon_module(self, module_id: str) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.navigate(module_id)
        page = self._pages.get(module_id)
        if page is not None and hasattr(page, "focus_source_input"):
            page.focus_source_input()

    def _toggle_fullscreen(self) -> None:
        """F11：沉浸模式。"""
        self.toggle_immersive()

    def _escape_immersive(self) -> None:
        if self._chrome_focus:
            self.set_immersive(False)

    def is_immersive(self) -> bool:
        return bool(self._chrome_focus)

    def toggle_immersive(self) -> None:
        self.set_immersive(not self._chrome_focus)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange and not self.isFullScreen():
            if self._chrome_focus:
                self._restore_chrome_layout()
                self._chrome_focus = False
        super().changeEvent(event)

    def _restore_chrome_layout(self) -> None:
        if self._header is not None:
            self._header.setVisible(True)
        if self._quick_bar is not None:
            self._quick_bar.setVisible(True)
        bar = self.statusBar()
        if bar is not None:
            bar.setVisible(True)
        self.set_nav_collapsed(False, show_rail=True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_F11:
            self.toggle_immersive()
            event.accept()
            return
        if key == Qt.Key.Key_Escape and self._chrome_focus:
            self.set_immersive(False)
            event.accept()
            return
        if self.handle_shell_arrow_key(key):
            event.accept()
            return
        super().keyPressEvent(event)

    def set_immersive(self, on: bool) -> None:
        """沉浸桌面：隐藏顶栏、快捷条、状态栏与侧栏；系统全屏。Esc/F11 退出。"""
        on = bool(on)
        self._chrome_focus = on
        show_chrome = not on
        if self._header is not None:
            self._header.setVisible(show_chrome)
        if self._quick_bar is not None:
            self._quick_bar.setVisible(show_chrome)
        if self._focus_exit_bar is not None:
            self._focus_exit_bar.setVisible(False)
        bar = self.statusBar()
        if bar is not None:
            bar.setVisible(show_chrome)
        self.set_nav_collapsed(on, show_rail=not on)
        if on:
            self.showFullScreen()
        elif self.isFullScreen():
            self.showMaximized()
        page = self._pages.get(self._current_id)
        if page is not None and hasattr(page, "on_immersive_changed"):
            page.on_immersive_changed(on)

    def _toggle_chrome_focus(self) -> None:
        self.toggle_immersive()

    def _load_modules(self) -> None:
        """登记菜单元数据 + 构建分组侧栏；页面按需懒加载，互不影响启动性能。"""
        seen: set[str] = set()
        # 先清布局（不含 stretch）
        while self._nav_layout.count():
            item = self._nav_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        self._nav_buttons.clear()
        self._nav_items.clear()
        self._nav_group_headers.clear()
        self._nav_group_members.clear()
        self._nav_group_labels.clear()
        self._module_groups.clear()

        for gid, glab, items in grouped_menu_items(licensed_only=True):
            member_ids: list[str] = []
            for item in items:
                mid = str(item.get("id") or "")
                if not mid or mid in seen:
                    continue
                if mid in SYSTEM_ACTIONS and not item.get("show", True):
                    self._menu_meta[mid] = item
                    seen.add(mid)
                    continue
                seen.add(mid)
                self._menu_meta[mid] = item
                self._module_groups[mid] = gid
                member_ids.append(mid)

            if not member_ids:
                continue

            header = QPushButton(f"▾ {glab}")
            header.setObjectName("NavGroupHeader")
            header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            header.clicked.connect(lambda _=False, g=gid: self._toggle_nav_group(g))
            self._nav_group_headers[gid] = header
            self._nav_group_labels[gid] = glab
            self._nav_group_expanded[gid] = True
            self._nav_layout.addWidget(header)

            self._nav_group_members[gid] = member_ids
            for mid in member_ids:
                item = self._menu_meta[mid]
                self._add_nav_button(mid, str(item.get("name") or mid), item)

        for mid in SYSTEM_ACTIONS:
            if mid in seen:
                continue
            item = get_menu_item_by_id(mid) or {"id": mid, "name": mid, "show": False}
            self._menu_meta[mid] = item
            self._module_groups[mid] = "system"
            if item.get("show"):
                self._add_nav_button(mid, str(item.get("name") or mid), item)

        self._menu_meta["__about__"] = {"id": "__about__", "icon": "about", "name": "关于"}
        self._nav_layout.addStretch(1)

    def _add_nav_button(self, module_id: str, label: str, menu_item: dict) -> None:
        icon_key = str(menu_item.get("icon") or module_id)
        btn = QPushButton(label)
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setIcon(menu_item_icon(icon_key, size=_NAV_ICON, parent=self))
        btn.setIconSize(QSize(_NAV_ICON, _NAV_ICON))
        btn.setProperty("navItem", "true")
        btn.clicked.connect(lambda _=False, m=module_id: self.navigate(m))
        self._nav_buttons[module_id] = btn
        self._nav_items[module_id] = menu_item
        self._nav_layout.addWidget(btn)

    def _set_nav_group_header(self, group_id: str, expanded: bool) -> None:
        header = self._nav_group_headers.get(group_id)
        glab = self._nav_group_labels.get(group_id, "")
        if header is not None:
            header.setText(("▾ " if expanded else "▸ ") + glab)

    def _nav_item_want_show(self, mid: str, item: dict) -> bool:
        if self._admin_sees_all_nav():
            return True
        if mid in SYSTEM_ACTIONS and not item.get("show"):
            return False
        return bool(item.get("show", True))

    def _toggle_nav_group(self, group_id: str) -> None:
        expanded = not self._nav_group_expanded.get(group_id, True)
        self._nav_group_expanded[group_id] = expanded
        self._set_nav_group_header(group_id, expanded)
        for mid in self._nav_group_members.get(group_id, []):
            btn = self._nav_buttons.get(mid)
            if btn is None:
                continue
            item = self._nav_items.get(mid) or {}
            want_show = self._nav_item_want_show(mid, item)
            btn.setVisible(bool(want_show and expanded))

    def _ensure_page(self, module_id: str) -> BasePage | None:
        if module_id in self._pages:
            return self._pages[module_id]
        item = self._menu_meta.get(module_id) or get_menu_item_by_id(module_id) or {
            "id": module_id,
            "name": module_id,
        }
        page = create_page(module_id, item)
        self._pages[module_id] = page
        self._stack.addWidget(page)
        return page

    def _refresh_chrome_icons(self) -> None:
        clear_cache()
        header_fg = self._header_icon_color()
        for btn, icon_name in self._header_icon_buttons:
            btn.setIcon(
                get_header_icon(icon_name, color=header_fg, size=_HEADER_ICON, parent=self)
            )
            btn.setIconSize(QSize(_HEADER_ICON, _HEADER_ICON))
            btn.setFixedSize(_HEADER_BTN, _HEADER_BTN)
        for btn, icon_key, color in self._quick_buttons:
            btn.setIcon(get_icon(icon_key, color=color, size=_QUICK_ICON, parent=self))
        self._apply_nav_collapse_icon()
        for mid, btn in self._nav_buttons.items():
            item = self._nav_items.get(mid) or {}
            icon_key = str(item.get("icon") or mid)
            btn.setIcon(menu_item_icon(icon_key, size=_NAV_ICON, parent=self))

    def _on_nav_rebuild(self) -> None:
        """菜单配置变更后重建侧栏与模块下拉。"""
        self._load_modules()
        self.rebuild_nav()
        self._rebuild_modules_menu()
        self._refresh_chrome_icons()
        # 首页若已加载，下次进入会按新菜单重建；此处清缓存强制刷新
        if "home" in self._pages:
            old = self._pages.pop("home")
            self._stack.removeWidget(old)
            old.deleteLater()
            if self._current_id == "home":
                self.navigate("home")

    def _on_license_changed(self) -> None:
        """授权变更：刷新侧栏与状态栏。"""
        self.rebuild_nav()
        try:
            from services.license_manager import global_license_manager

            self.show_status(global_license_manager.get_validity_text(), level=StatusLevel.INFO)
        except Exception:
            pass
        cur = self._current_id
        if cur and cur not in ("home", "system_settings", "notifications", "job_scheduler"):
            ok, reason = can_open(cur)
            if not ok:
                if not self._try_renew_and_open(cur, reason):
                    show_warning(self, reason or "当前模块已不可用")
                self.navigate("home")

    def _try_renew_and_open(self, module_id: str, reason: str) -> bool:
        """到期拦截时弹续费窗，成功则重试打开模块。"""
        from services.subscription_renew import is_renewable_block

        if not is_renewable_block(reason):
            return False
        from app.renew_dialog import offer_renew_dialog

        if not offer_renew_dialog(self, reason=reason):
            return False
        ok, reason2 = can_open(module_id)
        if not ok:
            show_warning(self, reason2 or "续费后仍无法打开该模块")
            return False
        # 续费成功：直接走打开逻辑（避免 navigate 递归）
        page = self._ensure_page(module_id)
        if page is None:
            return False
        if self._current_id and self._current_id in self._pages:
            self._pages[self._current_id].on_leave()
        self.set_page_shortcuts(None)
        self._current_id = module_id
        self._stack.setCurrentWidget(page)
        self._st.set_module(module_id)
        self._sync_domain_for_module(module_id)
        for mid, btn in self._nav_buttons.items():
            btn.setChecked(mid == module_id)
        page.on_enter()
        if hasattr(page, "schedule_primary_focus"):
            page.schedule_primary_focus()
        title = page.page_title or module_id
        self.show_status(f"当前：{title}", level=StatusLevel.INFO)
        try:
            from services.license_manager import global_license_manager

            self.show_status(global_license_manager.get_validity_text(), level=StatusLevel.SUCCESS)
        except Exception:
            pass
        return True

    def rebuild_nav(self) -> None:
        """授权变更后刷新侧栏：按当前域过滤二级模块。"""
        self._rebuild_domain_tabs()
        self._apply_domain_filter()
        for mid, btn in self._nav_buttons.items():
            btn.setChecked(mid == self._current_id)

    def navigate(self, module_id: str) -> None:
        if module_id == "__about__":
            self._show_about()
            return

        ok, reason = can_open(module_id)
        if not ok:
            if self._try_renew_and_open(module_id, reason):
                return
            show_warning(self, reason or "无权限打开该模块")
            self.show_status(reason or "无权限", level=StatusLevel.WARNING)
            return

        page = self._ensure_page(module_id)
        if page is None:
            logger.warning("未知模块: %s", module_id)
            return

        if self._current_id and self._current_id in self._pages:
            self._pages[self._current_id].on_leave()

        self.set_page_shortcuts(None)
        self._current_id = module_id
        self._stack.setCurrentWidget(page)
        self._st.set_module(module_id)
        self._sync_domain_for_module(module_id)

        for mid, btn in self._nav_buttons.items():
            btn.setChecked(mid == module_id)

        page.on_enter()
        if hasattr(page, "schedule_primary_focus"):
            page.schedule_primary_focus()
        title = page.page_title or module_id
        self.show_status(f"当前：{title}", level=StatusLevel.INFO)

    def _show_about(self) -> None:
        from app.about_dialog import AboutDialog

        AboutDialog(self).exec()

    def show_status(self, text: str, *, level: StatusLevel = StatusLevel.INFO) -> None:
        self._last_status_level = level
        self.set_status_message(text)

    def set_status_message(self, text: str) -> None:
        bar = self.statusBar()
        if not bar:
            return
        ver = self._st.app_version()
        user = self._st.display_name or self._st.username or "—"
        bar.showMessage(f"{text}  |  用户: {user}  |  v{ver}")
        if self._status_user_label is not None:
            self._status_user_label.setText(user)
        if self._status_ver_label is not None:
            self._status_ver_label.setText(f"v{ver}")

    def refresh_brand_chrome(self) -> None:
        """用户修改系统信息后刷新顶栏品牌与 Logo。"""
        from services.system_info import get_system_info, logo_path

        info = get_system_info()
        if self._brand_label is not None:
            self._brand_label.setText(str(info.get("brand_name") or self._st.brand_name()))
        ui = get_ui_config()
        title = str(info.get("window_title") or ui.get("window_title") or info.get("brand_name") or "")
        if title:
            try:
                from services.edition_profile import window_title_suffix

                suffix = window_title_suffix()
            except Exception:
                suffix = ""
            self.setWindowTitle(f"{title} · TOA3{suffix}")
        if self._header_logo_label is not None and logo_path() is not None:
            pix = brand_logo_pixmap(_HEADER_LOGO, _HEADER_LOGO, parent=self)
            if not pix.isNull():
                self._header_logo_label.setPixmap(pix)
        if self._user_btn is not None:
            name = self._st.display_name or self._st.username or "用户"
            self._user_btn.setToolTip(f"账号信息 · {name}")
            self._user_btn.setIcon(
                get_header_icon("user", color=header_fg, size=_HEADER_ICON, parent=self)
            )

    def on_theme_changed(self, theme_id: str, palette: dict) -> None:
        self._st.set_theme(theme_id, palette)
        self._refresh_chrome_icons()
        for page in self._pages.values():
            page.on_theme_changed(theme_id, palette)
        try:
            from widgets.inputs import DateEdit

            for de in self.findChildren(DateEdit):
                de._refresh_icon()
        except Exception:
            pass
        from app.theme_loader import theme_display_name

        self.show_status(
            f"已切换主题：{theme_display_name(theme_id)}",
            level=StatusLevel.SUCCESS,
        )

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self._status_user_label = QLabel()
        self._status_ver_label = QLabel()
        self._status_user_label.setObjectName("StatusUser")
        self._status_ver_label.setObjectName("StatusVersion")
        bar.addPermanentWidget(self._status_user_label)
        bar.addPermanentWidget(self._status_ver_label)
        self._last_status_level = StatusLevel.READY
        self.show_status("就绪", level=StatusLevel.READY)
