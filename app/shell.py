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
    get_group_order,
    group_label,
    SYSTEM_ACTIONS,
    grouped_menu_items,
    show_in_sidebar,
)
from services.access_control import can_open, nav_clickable, requires_purchase_redirect
from services.notify_bus import get_bus
from services.job_scheduler import get_scheduler
from services.tray_service import get_tray
from services.platform_experience import get_platform_experience
from services.hotkey_service import get_hotkey_service
from services.screenshot_service import run_screenshot_hotkey
from core.user_messages import show_warning
from widgets import MessageKindButton

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
    """Esc 退出沉浸；F11 由应用级过滤器优先于 WebEngine / 系统热键。"""

    def __init__(self, shell: "MainShell") -> None:
        super().__init__(shell)
        self._shell = shell

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.KeyPress:
            if (
                event.key() == Qt.Key.Key_Escape
                and self._shell.is_immersive()
                and self._shell_key_target()
            ):
                try:
                    from services.screenshot_overlay import is_screenshot_session_active

                    if is_screenshot_session_active():
                        return False
                except Exception:
                    pass
                self._shell.set_immersive(False)
                return True
            if (
                event.key() == Qt.Key.Key_F11
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and self._shell_key_target()
            ):
                self._shell._toggle_fullscreen()
                return True
        elif et == QEvent.Type.ShortcutOverride:
            if (
                event.key() == Qt.Key.Key_F11
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and self._shell_key_target()
            ):
                event.accept()
                return True
        return False

    def _shell_key_target(self) -> bool:
        """主壳前台且无模态弹窗（WebEngine 焦点不在 Qt 树内时也拦截 F11）。"""
        from PySide6.QtWidgets import QApplication

        if QApplication.activeModalWidget() is not None:
            return False
        shell = self._shell
        if not shell.isVisible() or not shell.isActiveWindow():
            return False
        try:
            from services.screenshot_overlay import is_screenshot_session_active

            if is_screenshot_session_active():
                return False
        except Exception:
            pass
        return True


class MainShell(QMainWindow):
    """TOA3 主窗口壳。"""

    def __init__(self, *, defer_startup: bool = False) -> None:
        super().__init__()
        self._st = AppState.get()
        ui = get_ui_config()
        self._startup_complete = False

        title = str(ui.get("window_title") or self._st.brand_name())
        self._apply_window_title(title)

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
        self._immersive_enter_pending = False
        self._hotkey_actions: list[QAction] = []
        self._page_shortcuts: list[QShortcut] = []
        self._global_fullscreen_hotkey_ok = False
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
        if ui.get("nav_default_collapsed"):
            self.set_nav_collapsed(True, show_rail=True)
        if ui.get("default_fullscreen"):
            self.showMaximized()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(600, self._maybe_prompt_renew_on_start)

    def _maybe_prompt_renew_on_start(self) -> None:
        try:
            from app.commerce_dialog import open_purchase_dialog
            from services.access_control import requires_purchase_redirect
            from services.license_manager import global_license_manager as lm

            if requires_purchase_redirect():
                open_purchase_dialog(self, reason=lm.get_validity_text(), forced=True)
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

        get_platform_experience().attach_shell(self)
        self.refresh_brand_chrome()

        self.reapply_global_hotkeys()
        self._register_hotkeys()

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
        from services.win_foreground import force_widget_foreground

        force_widget_foreground(self)

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
        header_align = Qt.AlignmentFlag.AlignVCenter

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
                hlay.addWidget(logo, 0, header_align)

        brand = QLabel(self._st.brand_name())
        brand.setObjectName("ShellBrand")
        self._brand_label = brand
        hlay.addWidget(brand, 0, header_align)

        self._license_chip = MessageKindButton("试用版", kind="info")
        self._license_chip.setObjectName("ShellLicenseChip")
        self._license_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._license_chip.setFixedHeight(26)
        self._license_chip.setMaximumHeight(26)
        self._license_chip.setMaximumWidth(140)
        self._license_chip.clicked.connect(self._on_license_chip_clicked)
        hlay.addWidget(self._license_chip, 0, header_align)

        hlay.addStretch(1)

        self._home_btn = self._header_icon_button(
            "home",
            "检索工作 · 打开功能搜索 (Ctrl+K)",
            self._open_command_palette,
        )
        hlay.addWidget(self._home_btn)
        hlay.addWidget(
            self._header_icon_button(
                "settings",
                "系统设置 (Alt+S)",
                self._open_system_settings,
            )
        )
        hlay.addWidget(self._build_user_menu_button())

        # 沉浸模式不占用顶栏退出条（Esc/F11 退出）
        self._focus_exit_bar = None

        outer.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav_width = int(spec.get("nav_width") or 200)
        self._nav_collapsed = False
        self._nav_auto_hidden = False

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
        self._apply_nav_sidebar_layout(show_rail=show_rail)

    def _visible_nav_count_in_domain(self, group_id: str | None = None) -> int:
        """当前子模块下会在侧栏展示的二级功能模块数量。"""
        gid = str(group_id or self._current_domain or "home").strip().lower()
        count = 0
        for mid in self._nav_group_members.get(gid, []):
            if mid in ("__about__",):
                continue
            item = self._nav_items.get(mid) or {}
            if self._module_groups.get(mid) != gid:
                continue
            if self._nav_item_want_show(mid, item):
                count += 1
        return count

    def _apply_nav_sidebar_layout(self, *, show_rail: bool = True) -> None:
        """侧栏布局：仅 1 个二级项时不展示侧栏；2 个及以上再尊重折叠偏好。"""
        if getattr(self, "_chrome_focus", False):
            self._nav_wrap.setVisible(False)
            self._nav_expand_rail.setVisible(False)
            return

        auto_hide = self._visible_nav_count_in_domain() <= 1
        self._nav_auto_hidden = auto_hide
        if auto_hide:
            self._nav_wrap.setVisible(False)
            self._nav_expand_rail.setVisible(False)
            return

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

    def _show_switch_user(self) -> None:
        from services.settings_access import can_switch_local_identity

        if not can_switch_local_identity():
            from core.user_messages import show_warning

            show_warning(self, "切换身份仅管理员可用，且本机需有多个已发卡账号。")
            return
        from app.switch_user_dialog import SwitchUserDialog

        SwitchUserDialog(self).exec()

    def _build_user_menu_button(self) -> QToolButton:
        """账号入口：查看、退出。"""
        user_name = self._st.display_name or self._st.username or "用户"
        btn = QToolButton()
        btn.setObjectName("ShellHeaderBtn")
        btn.setToolTip(f"账号 · {user_name} · 点击查看/退出")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        fg = self._header_icon_color()
        btn.setIcon(get_header_icon("user", color=fg, size=_HEADER_ICON, parent=self))
        btn.setIconSize(QSize(_HEADER_ICON, _HEADER_ICON))
        btn.setFixedSize(_HEADER_BTN, _HEADER_BTN)
        btn.clicked.connect(self._show_user_profile)

        self._header_icon_buttons.append((btn, "user"))
        self._user_btn = btn
        return btn

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
        for group_id in get_group_order():
            label = group_label(group_id)
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

    def _ensure_domain_button(self, group_id: str) -> QToolButton:
        """顶栏子模块 Tab：出厂 + 用户提升的自定义子模块。"""
        gid = str(group_id or "").strip().lower()
        btn = self._domain_buttons.get(gid)
        if btn is not None:
            return btn
        btn = QToolButton()
        btn.setObjectName("ShellDomainBtn")
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        label = group_label(gid)
        btn.setText(label)
        btn.setCheckable(True)
        btn.setToolTip(f"{label}（子模块 · 子系统）")
        btn.clicked.connect(lambda _=False, g=gid: self.select_domain(g))
        self._domain_buttons[gid] = btn
        return btn

    def _rebuild_domain_tabs(self) -> None:
        """按当前 group_order 重排顶栏，并仅展示有可见模块的域 Tab。"""
        visible_groups: set[str] = set()
        for gid, _glab, items in grouped_menu_items(licensed_only=False):
            for item in items:
                mid = str(item.get("id") or "")
                if not mid or not item.get("show", True):
                    continue
                visible_groups.add(gid)

        bar = self._quick_bar
        lay = bar.layout() if bar is not None else None
        if lay is not None:
            while lay.count():
                lay.takeAt(0)
            for gid in get_group_order():
                btn = self._ensure_domain_button(gid)
                lay.addWidget(btn)
            lay.addStretch(1)

        for gid, btn in self._domain_buttons.items():
            btn.setVisible(gid in visible_groups)
        self._refresh_domain_tab_labels()

    def _refresh_domain_tab_labels(self) -> None:
        for gid, btn in self._domain_buttons.items():
            label = group_label(gid)
            btn.setText(label)
            btn.setToolTip(f"{label}（子模块 · 子系统）")

    def _update_domain_tab_checks(self) -> None:
        for gid, btn in self._domain_buttons.items():
            btn.setChecked(gid == self._current_domain)

    def select_domain(self, group_id: str, *, navigate_first: bool = True) -> None:
        """顶栏子模块（子系统）切换：侧栏只展示该子系统下的功能模块。"""
        gid = str(group_id or "home").strip().lower()
        allowed = set(get_group_order()) | {"other"}
        if gid not in allowed:
            return
        self._current_domain = gid
        self._update_domain_tab_checks()
        self._apply_domain_filter()
        if not navigate_first:
            return
        cur_gid = self._module_groups.get(self._current_id)
        if cur_gid == gid:
            return
        # 先刷新侧栏，下一帧再打开首项，避免切 Tab 时界面卡住
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda g=gid: self._navigate_first_in_domain(g))

    def _sync_nav_checks(self, module_id: str | None = None) -> None:
        mid = self._current_id if module_id is None else module_id
        for m, btn in self._nav_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(m == mid)
            btn.blockSignals(False)

    def _on_nav_clicked(self, module_id: str) -> None:
        self.navigate(module_id)

    def _navigate_first_in_domain(self, gid: str) -> None:
        """打开当前子模块下侧栏首个可见且可打开的二级页。"""
        if self._current_domain != gid:
            return
        for mid in self._nav_group_members.get(gid, []):
            item = self._nav_items.get(mid) or self._menu_meta.get(mid) or {}
            if not self._nav_item_want_show(mid, item):
                continue
            ok, _ = can_open(mid)
            if ok:
                self.navigate(mid)
                return
        if gid == "home":
            self.navigate("home")
            return
        reason = ""
        for mid in self._nav_group_members.get(gid, []):
            item = self._nav_items.get(mid) or {}
            if not self._nav_item_want_show(mid, item):
                continue
            ok, reason = can_open(mid)
            if not ok:
                break
        self.navigate("home")
        try:
            from services.user_plan_presentation import user_access_block_message

            block_msg = user_access_block_message()
        except Exception:
            block_msg = "该功能需付费版"
        self.show_status(
            reason or block_msg,
            level=StatusLevel.WARNING,
        )

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
            want_show = self._nav_item_want_show(mid, item)
            visible = bool(in_domain and want_show)
            ok, reason = nav_clickable(mid)
            btn.setVisible(visible)
            if not visible:
                continue
            btn.setEnabled(ok)
            tip = str(item.get("desc") or item.get("name") or mid)
            if not ok and reason:
                tip = f"{tip}\n（{reason}）"
            elif ok and reason and requires_purchase_redirect():
                tip = f"{tip}\n（{reason} · 点击前往升级）"
            btn.setToolTip(tip)
        self._apply_nav_sidebar_layout()

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
            str(hk.get("open_settings") or "Alt+S"): self.open_system_settings,
            str(hk.get("switch_user") or "Alt+U"): self._show_switch_user,
            str(hk.get("open_about") or "Alt+Shift+O"): self._show_about,
            str(hk.get("open_home") or "Ctrl+H"): self._go_home,
            "Ctrl+K": self._open_command_palette,
        }
        # F11：ApplicationShortcut + 应用级 eventFilter（WebEngine 内不依赖 OS 全局热键）
        if fs_key and fs_key.lower() != "none":
            mapping[fs_key] = self._toggle_fullscreen
        if fs_key.upper() != "F11":
            mapping["F11"] = self._toggle_fullscreen
        from services.module_hotkeys import get_module_shortcut, normalize_module_id

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
            if mid == "column_preview" and seq.upper() in (fs_key.upper(), "F11"):
                continue
            if mid == "ocr_tool":
                mapping[seq] = self._run_ocr_hotkey
            elif mid == "clipboard_history":
                mapping[seq] = self._open_clipboard_quick
            elif mid == "column_preview":
                mapping[seq] = self.toggle_immersive
            else:
                mapping[seq] = lambda _checked=False, m=mid: self._summon_module(m)

        # 截图只走全局 RegisterHotKey（_wire_platform），勿再挂 QAction，否则前台双开多层

        summon_id = normalize_module_id(hk.get("summon_module_id"))
        tw = str(hk.get("toggle_window") or "").strip()
        if summon_id and tw and tw.lower() != "none":
            from services.double_ctrl_summon import is_double_ctrl_spec

            if not is_double_ctrl_spec(tw):
                mapping[tw] = lambda: self._summon_module(summon_id)

        for seq, fn in mapping.items():
            if not seq or seq.lower() == "none":
                continue
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
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

    def reapply_global_hotkeys(self) -> dict[str, str]:
        """RegisterHotKey 全局热键（与设置页保存、启动共用）。"""
        from services.global_hotkey_bindings import apply_global_hotkeys_for_shell

        return apply_global_hotkeys_for_shell(self)

    def reload_window_hotkeys(self) -> dict[str, str]:
        """设置页保存后重载应用级 + 全局快捷键。"""
        self._register_hotkeys()
        self._update_fullscreen_button_tip()
        return self.reapply_global_hotkeys()

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
            for gid in get_group_order()
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
        """←/→：切换顶栏一级子模块（保留 API，壳层不再绑方向键）。"""
        domains = self._visible_domain_ids()
        if not domains:
            return
        try:
            idx = domains.index(self._current_domain)
        except ValueError:
            idx = 0
        new_gid = domains[(idx + int(step)) % len(domains)]
        self.select_domain(new_gid, navigate_first=True)
        label = group_label(new_gid)
        self.show_status(f"子模块：{label}", level=StatusLevel.INFO)

    def cycle_nav_module(self, step: int) -> None:
        """↑/↓：切换当前子模块下的侧栏功能模块（保留 API，壳层不再绑方向键）。"""
        mods = self._visible_nav_module_ids()
        if not mods:
            return
        try:
            idx = mods.index(self._current_id)
        except ValueError:
            idx = 0
        mid = mods[(idx + int(step)) % len(mods)]
        self.navigate(mid)

    def _go_home(self, *_args) -> None:
        """Ctrl+H：回到首页子模块。"""
        try:
            from PySide6.QtWidgets import QApplication
            from app.command_palette import CommandPalette

            for w in list(QApplication.topLevelWidgets()):
                if isinstance(w, CommandPalette) and w.isVisible():
                    w.reject()
        except Exception:
            pass
        try:
            self.select_domain("home")
        except Exception:
            self.navigate("home")

    def _open_command_palette(self) -> None:
        """顶栏 ⌂ 与 Ctrl+K：弹出检索工作对话框。"""
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
        mid = self._coerce_module_id(module_id)
        if not mid:
            logger.warning("忽略无效模块唤起: %r", module_id)
            return
        from services.win_foreground import force_widget_foreground

        force_widget_foreground(self)
        self.navigate(mid)
        page = self._pages.get(mid)
        if page is not None and hasattr(page, "focus_source_input"):
            page.focus_source_input()

    @staticmethod
    def _coerce_module_id(module_id: object) -> str:
        from services.module_hotkeys import normalize_module_id

        return normalize_module_id(module_id)

    def _toggle_fullscreen(self) -> None:
        """F11：沉浸模式。"""
        try:
            from services.screenshot_overlay import is_screenshot_session_active

            if is_screenshot_session_active():
                return
        except Exception:
            pass
        self.toggle_immersive()

    def _escape_immersive(self) -> None:
        # 截图浮层为独立顶层窗时，勿用壳层 Esc 抢焦点；沉浸退出也让位
        try:
            from services.screenshot_overlay import is_screenshot_session_active

            if is_screenshot_session_active():
                return
        except Exception:
            pass
        if self._chrome_focus:
            self.set_immersive(False)

    def is_immersive(self) -> bool:
        return bool(self._chrome_focus)

    def toggle_immersive(self) -> None:
        import time

        now = time.monotonic()
        last = float(getattr(self, "_last_immersive_toggle_ts", 0.0) or 0.0)
        if now - last < 0.35:
            return
        self._last_immersive_toggle_ts = now
        self.set_immersive(not self._chrome_focus)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange:
            super().changeEvent(event)
            if self._chrome_focus:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, self._sync_immersive_window_state)
            return
        super().changeEvent(event)

    def _sync_immersive_window_state(self) -> None:
        """Windows 下 showFullScreen 过渡瞬间 isFullScreen 仍为 false，须延后判断。"""
        if not self._chrome_focus:
            return
        # 正在进入全屏：勿误判为「用户退出」而清沉浸态
        if self._immersive_enter_pending:
            return
        if self.isFullScreen():
            return
        if self.windowState() & Qt.WindowState.WindowFullScreen:
            return
        self._restore_chrome_layout()
        self._chrome_focus = False

    def _restore_chrome_layout(self) -> None:
        if self._header is not None:
            self._header.setVisible(True)
        if self._quick_bar is not None:
            self._quick_bar.setVisible(True)
        bar = self.statusBar()
        if bar is not None:
            bar.setVisible(True)
        from services.config_service import nav_default_collapsed

        self.set_nav_collapsed(nav_default_collapsed(), show_rail=True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # F11 仅走全局热键 → _toggle_fullscreen，此处不再处理以免双触发
        if event.key() == Qt.Key.Key_Escape and self._chrome_focus:
            try:
                from services.screenshot_overlay import is_screenshot_session_active

                if is_screenshot_session_active():
                    super().keyPressEvent(event)
                    return
            except Exception:
                pass
            self.set_immersive(False)
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
        if on:
            self._immersive_enter_pending = True
            self.set_nav_collapsed(True, show_rail=False)
            self.showFullScreen()
            from PySide6.QtCore import QTimer

            QTimer.singleShot(300, self._clear_immersive_enter_pending)
        else:
            self._immersive_enter_pending = False
            from services.config_service import nav_default_collapsed

            if self.isFullScreen():
                self.showMaximized()
            self.set_nav_collapsed(nav_default_collapsed(), show_rail=True)
        page = self._pages.get(self._current_id)
        if page is not None and hasattr(page, "on_immersive_changed"):
            page.on_immersive_changed(on)
        self._update_fullscreen_button_tip()
        self.show_status(
            "沉浸全屏 · Esc / F11 退出" if on else "已退出沉浸全屏",
            level=StatusLevel.INFO,
        )

    def _clear_immersive_enter_pending(self) -> None:
        self._immersive_enter_pending = False
        # 进入完成后若仍非全屏，再补一次（部分 Windows 需二次）
        if self._chrome_focus and not self.isFullScreen():
            self.showFullScreen()

    def _update_fullscreen_button_tip(self) -> None:
        btn = getattr(self, "_fullscreen_btn", None)
        if btn is None:
            return
        fs_key = str(get_hotkeys_config().get("toggle_fullscreen") or "F11").strip()
        if self._chrome_focus:
            btn.setToolTip(f"退出沉浸全屏 ({fs_key} / Esc)")
        else:
            btn.setToolTip(f"沉浸全屏 ({fs_key}) · Esc 退出")

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
                self._menu_meta[mid] = item
                seen.add(mid)
                if not show_in_sidebar(item):
                    continue
                if mid in SYSTEM_ACTIONS and not item.get("show", True):
                    continue
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
            if item.get("show") and show_in_sidebar(item):
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
        btn.clicked.connect(lambda _=False, m=module_id: self._on_nav_clicked(m))
        self._nav_buttons[module_id] = btn
        self._nav_items[module_id] = menu_item
        self._nav_layout.addWidget(btn)

    def _set_nav_group_header(self, group_id: str, expanded: bool) -> None:
        header = self._nav_group_headers.get(group_id)
        glab = self._nav_group_labels.get(group_id, "")
        if header is not None:
            header.setText(("▾ " if expanded else "▸ ") + glab)

    def _nav_item_want_show(self, mid: str, item: dict) -> bool:
        if not show_in_sidebar(item):
            return False
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

    def _invalidate_cached_page(self, module_id: str) -> None:
        """身份/菜单变更后丢弃懒加载页，下次进入按新角色重建。"""
        page = self._pages.pop(module_id, None)
        if page is None:
            return
        self._stack.removeWidget(page)
        page.deleteLater()
        if self._current_id == module_id:
            self.navigate(module_id)

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
        # 用户插件热更新：清掉已缓存的插件页，避免旧代码残留
        for mid in list(self._pages.keys()):
            item = self._menu_meta.get(mid) or {}
            if str(item.get("source") or "") == "user_plugin":
                self._invalidate_cached_page(mid)
            else:
                try:
                    from services.plugin_registry import get_plugin_record

                    if get_plugin_record(mid):
                        self._invalidate_cached_page(mid)
                except Exception:
                    pass
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

    def _on_license_chip_clicked(self) -> None:
        from app.commerce_dialog import open_account_dialog, open_purchase_dialog
        from services.access_control import requires_purchase_redirect

        try:
            if requires_purchase_redirect():
                open_purchase_dialog(self, forced=True)
                return
        except Exception:
            pass
        open_account_dialog(self)

    def open_subscription_settings(self) -> None:
        """终端用户走统一购买弹窗；管理员仍进系统设置授权页。"""
        from services.settings_access import is_settings_admin

        if is_settings_admin():
            self.navigate("system_settings")
            page = self._pages.get("system_settings")
            if page is not None and hasattr(page, "open_license_or_subscription"):
                page.open_license_or_subscription()
            return
        from app.commerce_dialog import open_purchase_dialog

        open_purchase_dialog(self, forced=False)

    def _on_license_changed(self) -> None:
        """授权变更：刷新侧栏、状态栏与顶栏 Chip。"""
        self.rebuild_nav()
        get_platform_experience().refresh_license_chip()
        self.refresh_brand_chrome()
        self._refresh_status_plan_label()
        # 用户正在设置页时不销毁懒加载页，避免云同步/联网校验回调栈内卡死
        if self._current_id != "system_settings":
            self._invalidate_cached_page("system_settings")
        try:
            from services.license_manager import global_license_manager

            if requires_purchase_redirect():
                from services.user_plan_presentation import user_access_block_message

                self.show_status(user_access_block_message(), level=StatusLevel.WARNING)
            else:
                self.show_status("授权已更新", level=StatusLevel.INFO)
        except Exception:
            pass
        cur = self._current_id
        if cur and cur not in ("home", "system_settings", "notifications", "job_scheduler"):
            ok, reason = can_open(cur)
            if not ok:
                nav_ok, nav_reason = nav_clickable(cur)
                if requires_purchase_redirect() and nav_ok:
                    self._redirect_to_purchase(nav_reason or reason, module_id=cur)
                    return
                if not self._try_purchase_and_open(cur, reason):
                    show_warning(self, reason or "当前模块已不可用")
                self.navigate("home")

    def _open_module_direct(self, module_id: str) -> bool:
        """授权已通过校验后直接打开模块（避免 navigate 递归）。"""
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
        return True

    def _try_purchase_and_open(self, module_id: str, reason: str) -> bool:
        from app.commerce_dialog import open_purchase_dialog

        if not open_purchase_dialog(self, reason=reason, module_id=module_id, forced=False):
            return False
        ok, reason2 = can_open(module_id)
        if not ok:
            show_warning(self, reason2 or "开通后仍无法打开该模块")
            return False
        return self._open_module_direct(module_id)

    def _try_renew_and_open(self, module_id: str, reason: str) -> bool:
        """兼容旧入口。"""
        return self._try_purchase_and_open(module_id, reason)

    def rebuild_nav(self) -> None:
        """授权变更后刷新侧栏：按当前域过滤二级模块。"""
        self._rebuild_domain_tabs()
        self._apply_domain_filter()
        for mid, btn in self._nav_buttons.items():
            btn.setChecked(mid == self._current_id)

    def _redirect_to_purchase(self, reason: str = "", *, module_id: str = "") -> None:
        from app.commerce_dialog import open_purchase_dialog

        open_purchase_dialog(self, reason=reason, module_id=module_id, forced=True)

    def navigate(self, module_id: str) -> None:
        mid = self._coerce_module_id(module_id)
        if not mid:
            logger.warning("忽略无效模块导航: %r", module_id)
            return
        if mid == "__about__":
            self._show_about()
            return

        ok, reason = can_open(mid)
        if not ok:
            nav_ok, nav_reason = nav_clickable(mid)
            if requires_purchase_redirect() and nav_ok:
                self._redirect_to_purchase(nav_reason or reason, module_id=mid)
                return
            if self._try_purchase_and_open(mid, reason):
                return
            show_warning(self, reason or "无权限打开该模块")
            self.show_status(reason or "无权限", level=StatusLevel.WARNING)
            self._sync_nav_checks()
            return

        page = self._ensure_page(mid)
        if page is None:
            logger.warning("未知模块: %s", mid)
            self._sync_nav_checks()
            return

        if self._current_id and self._current_id in self._pages:
            self._pages[self._current_id].on_leave()

        self.set_page_shortcuts(None)
        self._current_id = mid
        self._stack.setCurrentWidget(page)
        self._st.set_module(mid)
        self._sync_domain_for_module(mid)

        for nav_mid, btn in self._nav_buttons.items():
            btn.setChecked(nav_mid == mid)

        page.on_enter()
        if hasattr(page, "schedule_primary_focus"):
            page.schedule_primary_focus()
        title = page.page_title or mid
        self.show_status(f"当前：{title}", level=StatusLevel.INFO)

    def _open_system_settings(self) -> None:
        self.navigate("system_settings")
        page = self._pages.get("system_settings")
        if page is not None and hasattr(page, "open_system_tab"):
            page.open_system_tab()

    def open_system_settings(self) -> None:
        """外部入口：打开系统设置并定位「系统」页签。"""
        self._open_system_settings()

    def _sign_out_user(self, *, confirmed: bool = False) -> None:
        from core.user_messages import ask_confirm
        from services.license_manager import global_license_manager

        if not confirmed and not ask_confirm(self, "退出当前账号？将返回登录界面。"):
            return
        try:
            global_license_manager.sign_out_local()
        except Exception:
            logger.debug("退出登录清理失败", exc_info=True)
        self._st.set_user("", "")
        self._restart_app()

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
        bar.showMessage(text)
        self._refresh_status_plan_label()
        if self._status_ver_label is not None:
            self._refresh_status_version_label()

    def _apply_window_title(self, title: str) -> None:
        try:
            from services.user_plan_presentation import dev_build_tag

            tag = dev_build_tag()
        except Exception:
            tag = ""
        suffix = f" · {tag}" if tag else ""
        self.setWindowTitle(f"{title} · TOA3{suffix}")

    def _refresh_status_plan_label(self) -> None:
        if self._status_user_label is None:
            return
        try:
            from services.user_plan_presentation import user_status_plan_label

            self._status_user_label.setText(user_status_plan_label())
        except Exception:
            self._status_user_label.setText("")

    def _refresh_status_version_label(self) -> None:
        if self._status_ver_label is None:
            return
        try:
            from services.user_plan_presentation import user_status_bar_version_label

            self._status_ver_label.setText(user_status_bar_version_label())
        except Exception:
            self._status_ver_label.setText(f"v{self._st.app_version()}")

    def refresh_brand_chrome(self) -> None:
        """用户修改系统信息后刷新顶栏品牌与 Logo。"""
        from services.system_info import get_system_info, logo_path

        info = get_system_info()
        if self._brand_label is not None:
            self._brand_label.setText(str(info.get("brand_name") or self._st.brand_name()))
        ui = get_ui_config()
        title = str(info.get("window_title") or ui.get("window_title") or info.get("brand_name") or "")
        if title:
            self._apply_window_title(title)
        if self._header_logo_label is not None and logo_path() is not None:
            pix = brand_logo_pixmap(_HEADER_LOGO, _HEADER_LOGO, parent=self)
            if not pix.isNull():
                self._header_logo_label.setPixmap(pix)
        if self._user_btn is not None:
            name = self._st.display_name or self._st.username or "用户"
            self._user_btn.setToolTip(f"账号 · {name} · 点击查看/退出")
            self._user_btn.setIcon(
                get_header_icon(
                    "user",
                    color=self._header_icon_color(),
                    size=_HEADER_ICON,
                    parent=self,
                )
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
        self._status_user_label.setObjectName("StatusPlan")
        self._status_ver_label.setObjectName("StatusVersion")
        bar.addPermanentWidget(self._status_user_label)
        bar.addPermanentWidget(self._status_ver_label)
        self._last_status_level = StatusLevel.READY
        self._refresh_status_plan_label()
        self._refresh_status_version_label()
        self.show_status("就绪", level=StatusLevel.READY)
