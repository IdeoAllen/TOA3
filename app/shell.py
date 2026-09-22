# -*- coding: utf-8 -*-
"""主应用壳：顶栏、快捷条、侧栏导航、模块宿主、状态栏。"""
from __future__ import annotations

import logging

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QSize, QEvent, QUrl
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
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
from services.icon_registry import clear_cache, get_header_icon, get_icon, menu_item_icon
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

_HEADER_ICON = 18
_HEADER_BTN = 30
# 离开这些页时若挂了 WebEngine，需延迟拆 View（切页立刻响应壳，Guest 后清）
_WEBENGINE_MODULE_IDS = frozenset(
    {
        "harness_agent",
        "open_pencil",
        "drawio_web",
        "comfyui_web",
        "web_workspace",
    }
)
# 首次建页偏重的模块（仍走通用 Loading；保留常量供审计/文档引用）
_HEAVY_BUILD_MODULE_IDS = frozenset(
    {
        "media_studio",
    }
)


class _LoadingGuestPage(BasePage):
    """子页未就位时的壳内占位：带不确定进度，可随时被 navigate 切走。"""

    def __init__(self, module_id: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.page_id = module_id
        self.page_title = title or module_id
        from widgets import HintLabel, ProgressBar

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 32, 32, 32)
        lay.setSpacing(12)
        lay.addStretch(1)
        tip = HintLabel(f"正在打开「{self.page_title}」…")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tip)
        self._progress = ProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setMinimumHeight(8)
        self._progress.setMaximumHeight(8)
        self._progress.setMaximumWidth(320)
        lay.addWidget(self._progress, 0, Qt.AlignmentFlag.AlignHCenter)
        sub = HintLabel("可随时点其它菜单离开，主窗口不会卡住。")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addStretch(2)
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
    """Esc 退出沉浸；F11 应用内切换；Ctrl+Tab 切换顶栏主菜单。"""

    def __init__(self, shell: "MainShell") -> None:
        super().__init__(shell)
        self._shell = shell

    @staticmethod
    def _domain_cycle_step(event) -> int | None:
        """Ctrl+Tab → +1；Ctrl+Shift+Tab / Ctrl+Backtab → -1。"""
        key = event.key()
        mods = event.modifiers()
        if not (mods & Qt.KeyboardModifier.ControlModifier):
            return None
        if mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
            return None
        if key == Qt.Key.Key_Backtab or (
            key == Qt.Key.Key_Tab and bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ):
            return -1
        if key == Qt.Key.Key_Tab:
            return 1
        return None

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.ShortcutOverride:
            if not self._shell_key_target():
                return False
            if self._domain_cycle_step(event) is not None:
                event.accept()
                return True
            if (
                event.key() == Qt.Key.Key_F11
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and bool(get_hotkeys_config().get("enable_immersive_hotkey", True))
            ):
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Escape and self._shell.is_immersive():
                event.accept()
                return True
            return False
        if et != QEvent.Type.KeyPress:
            return False
        if not self._shell_key_target():
            return False
        step = self._domain_cycle_step(event)
        if step is not None:
            self._shell.cycle_domain(step)
            return True
        if (
            event.key() == Qt.Key.Key_Escape
            and self._shell.is_immersive()
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
            and bool(get_hotkeys_config().get("enable_immersive_hotkey", True))
        ):
            self._shell._toggle_fullscreen()
            return True
        return False

    def _shell_key_target(self) -> bool:
        """主壳可见且无截图/模态挡路（WebEngine 焦点时也要能接到 F11/Esc）。"""
        from PySide6.QtWidgets import QApplication

        if QApplication.activeModalWidget() is not None:
            return False
        shell = self._shell
        if not shell.isVisible():
            return False
        try:
            from services.screenshot_overlay import is_screenshot_session_active

            if is_screenshot_session_active():
                return False
        except Exception:
            pass
        aw = QApplication.activeWindow()
        if aw is shell:
            return True
        if aw is not None and (shell.isAncestorOf(aw) or aw is shell.window()):
            return True
        # 已沉浸全屏时，部分环境 activeWindow 异常，仍放行 Esc/F11
        if shell.is_immersive():
            return True
        return bool(shell.isActiveWindow())


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
        self._loading_guests: dict[str, BasePage] = {}
        self._nav_seq = 0
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_items: dict[str, dict] = {}
        self._nav_group_headers: dict[str, QPushButton] = {}
        self._nav_group_members: dict[str, list[str]] = {}
        self._nav_group_labels: dict[str, str] = {}
        self._nav_group_expanded: dict[str, bool] = {}
        self._module_groups: dict[str, str] = {}
        self._current_domain: str = "home"
        self._domain_buttons: dict[str, QToolButton] = {}
        self._domain_btn_group: QButtonGroup | None = None
        self._domain_nav_token: int = 0
        self._nav_seq: int = 0
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

        self._apply_shell_feature_flags()
        if not defer_startup:
            self.complete_startup()

    def _apply_shell_feature_flags(self) -> None:
        """热键/拖入等全局壳开关（与 settings 保存后 reload 同源）。"""
        hk = get_hotkeys_config()
        self._close_to_tray = bool(hk.get("close_to_background", True))
        self.setAcceptDrops(bool(hk.get("enable_drop_open_desktop", True)))

    def open_drop_paths(self, paths: list[str] | list[Path]) -> None:
        """拖入/启动参数：进 MACOS 桌面，根=文件父目录并预览。"""
        if not bool(get_hotkeys_config().get("enable_drop_open_desktop", True)):
            self.show_status("已关闭「拖入打开桌面浏览」", level=StatusLevel.WARNING)
            return
        cleaned: list[str] = []
        for raw in paths or []:
            s = str(raw or "").strip()
            if not s:
                continue
            try:
                p = Path(s).expanduser()
                if p.exists():
                    cleaned.append(str(p.resolve()))
            except OSError:
                continue
        if not cleaned:
            self.show_status("拖入路径无效或不可读", level=StatusLevel.WARNING)
            return
        from services.win_foreground import force_widget_foreground

        force_widget_foreground(self)
        self.navigate("column_preview")
        page = self._pages.get("column_preview")
        if page is not None and hasattr(page, "open_paths"):
            page.open_paths(cleaned)
        else:
            self.show_status("无法打开 MACOS 桌面", level=StatusLevel.WARNING)

    def _paths_from_mime(self, mime) -> list[str]:
        if mime is None or not mime.hasUrls():
            return []
        out: list[str] = []
        for u in mime.urls():
            if not isinstance(u, QUrl) or not u.isLocalFile():
                continue
            p = Path(u.toLocalFile())
            try:
                if p.exists():
                    out.append(str(p.resolve()))
            except OSError:
                continue
        return out

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if bool(get_hotkeys_config().get("enable_drop_open_desktop", True)) and self._paths_from_mime(
            event.mimeData()
        ):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if bool(get_hotkeys_config().get("enable_drop_open_desktop", True)) and self._paths_from_mime(
            event.mimeData()
        ):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if not bool(get_hotkeys_config().get("enable_drop_open_desktop", True)):
            super().dropEvent(event)
            return
        paths = self._paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.open_drop_paths(paths)
            return
        super().dropEvent(event)

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
        # pandas 另线程；WebEngine 已在 main.show 前锚定主壳，勿再挂主壳预热
        QTimer.singleShot(2800, self._idle_prewarm_pandas)

    def _idle_prewarm_pandas(self) -> None:
        def _warm() -> None:
            import pandas  # noqa: F401

            from modules.schedule_reminder.schedule_reminder_service import (
                data_file_path,
                query_all_scenes,
            )

            if data_file_path().is_file():
                query_all_scenes()

        try:
            from services.harness_task_runner import HarnessTaskRunner

            runner = HarnessTaskRunner(self)
            runner.run(_warm, on_done=lambda *_: None)
        except Exception:
            logger.debug("pandas/课表预热失败", exc_info=True)

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
        self._start_hotkey_watchdog()

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

        # 先拆尽 WebEngine，再关窗（否则 Qt 析构顺序易原生闪退）
        try:
            self._purge_stale_web_embeds(except_mid=None)
        except Exception:
            logger.debug("退出前 purge WebEmbed 失败", exc_info=True)
        try:
            from services.shared_local_webengine import shutdown as shutdown_shared_web

            shutdown_shared_web()
        except Exception:
            logger.debug("退出前 shutdown shared webengine 失败", exc_info=True)

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

        # 顶栏只留文字品牌名，不放 Logo 图（窗口/任务栏图标仍走 app icon）
        self._header_logo_label = None

        brand = QLabel(self._st.brand_name())
        brand.setObjectName("ShellBrand")
        self._brand_label = brand
        hlay.addWidget(brand, 0, header_align)

        # 紧贴品牌名的小号授权标签（间距跟顶栏 spacing=4，不拉开）
        self._license_chip = MessageKindButton("基础版", kind="info")
        self._license_chip.setObjectName("ShellLicenseChip")
        self._license_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._license_chip.setFixedHeight(18)
        self._license_chip.setMaximumHeight(18)
        self._license_chip.setMaximumWidth(96)
        self._license_chip.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
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
        # 二级菜单项通常装得下：不预留滚动条槽；仅内容溢出时再出现
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_host = QWidget()
        self._nav_layout = QVBoxLayout(nav_host)
        self._nav_layout.setContentsMargins(10, 8, 10, 8)
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
        self._domain_btn_group = QButtonGroup(bar)
        self._domain_btn_group.setExclusive(True)
        for group_id in get_group_order():
            label = group_label(group_id)
            btn = QToolButton()
            btn.setObjectName("ShellDomainBtn")
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setText(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(False)  # 交由 QButtonGroup 互斥，避免点一下又弹回
            btn.setToolTip(f"{label}（子模块 · 子系统）")
            self._domain_btn_group.addButton(btn)
            # 用 pressed+强制选中，避免 checkable 自切换造成「一点就推」
            btn.clicked.connect(lambda _=False, g=group_id: self.select_domain(g))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, g=group_id, b=btn: self._on_domain_context_menu(
                    g, b.mapToGlobal(pos)
                )
            )
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
        btn.setAutoExclusive(False)
        btn.setToolTip(f"{label}（子模块 · 子系统）")
        btn.clicked.connect(lambda _=False, g=gid: self.select_domain(g))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, g=gid, b=btn: self._on_domain_context_menu(g, b.mapToGlobal(pos))
        )
        if self._domain_btn_group is not None:
            self._domain_btn_group.addButton(btn)
        self._domain_buttons[gid] = btn
        return btn

    def _on_domain_context_menu(self, group_id: str, global_pos) -> None:
        """顶栏自定义子模块右键：取消一级菜单（侧栏被隐藏时仍可降回）。"""
        from core.user_messages import ask_confirm, show_warning
        from services.menu_promote import demote_module_from_top_level
        from services.menu_registry import is_custom_group_id

        gid = str(group_id or "").strip().lower()
        if not is_custom_group_id(gid):
            return
        # 自定义 Tab 通常 group==module_id
        name = group_label(gid)
        menu = QMenu(self)
        act = menu.addAction("取消一级菜单")
        chosen = menu.exec(global_pos)
        if chosen is not act:
            return
        if not ask_confirm(self, f"将「{name}」取消一级菜单，降回侧栏？", title="取消一级菜单"):
            return
        ok, msg = demote_module_from_top_level(gid)
        if not ok:
            show_warning(self, msg)
            return
        self._on_nav_rebuild()
        self.show_status(msg, level=StatusLevel.SUCCESS)
        item2 = get_menu_item_by_id(gid) or {}
        dest = str(item2.get("group") or "business")
        self.select_domain(dest, navigate_first=False)
        if item2:
            self.navigate(gid)

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
            # 重建互斥组，避免旧按钮残留
            self._domain_btn_group = QButtonGroup(bar)
            self._domain_btn_group.setExclusive(True)
            for gid in get_group_order():
                btn = self._ensure_domain_button(gid)
                if self._domain_btn_group is not None and btn.group() is not self._domain_btn_group:
                    self._domain_btn_group.addButton(btn)
                lay.addWidget(btn)
            lay.addStretch(1)

        for gid, btn in self._domain_buttons.items():
            btn.setVisible(gid in visible_groups)
        self._refresh_domain_tab_labels()
        self._update_domain_tab_checks()

    def _refresh_domain_tab_labels(self) -> None:
        for gid, btn in self._domain_buttons.items():
            label = group_label(gid)
            btn.setText(label)
            btn.setToolTip(f"{label}（子模块 · 子系统）")

    def _update_domain_tab_checks(self) -> None:
        for gid, btn in self._domain_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(gid == self._current_domain)
            btn.blockSignals(False)

    def select_domain(self, group_id: str, *, navigate_first: bool = True) -> None:
        """顶栏子模块（子系统）切换：侧栏只展示该子系统下的功能模块。"""
        # 防止此前 WebEngine 冻窗未恢复导致顶栏「点了没反应」
        if not self.updatesEnabled():
            self.setUpdatesEnabled(True)
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
        # 先刷新侧栏，下一帧再打开首项；代次作废快切时的过期导航
        from PySide6.QtCore import QTimer

        self._domain_nav_token += 1
        token = self._domain_nav_token
        QTimer.singleShot(0, lambda g=gid, t=token: self._navigate_first_in_domain(g, t))

    def _sync_nav_checks(self, module_id: str | None = None) -> None:
        mid = self._current_id if module_id is None else module_id
        for m, btn in self._nav_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(m == mid)
            btn.blockSignals(False)

    def _on_nav_clicked(self, module_id: str) -> None:
        self.navigate(module_id)

    def _navigate_first_in_domain(self, gid: str, token: int | None = None) -> None:
        """打开当前子模块下侧栏首个可见且可打开的二级页。"""
        if token is not None and token != self._domain_nav_token:
            return
        if self._current_domain != gid:
            return
        # 系统域固定优先系统设置（壳必备，避免成员表异常时被打回首页）
        preferred = {
            "home": "home",
            "system": "system_settings",
            "engines": "harness_agent",
        }.get(gid)
        members = list(self._nav_group_members.get(gid, []))
        ordered: list[str] = []
        if preferred:
            ordered.append(preferred)
        for mid in members:
            if mid not in ordered:
                ordered.append(mid)

        for mid in ordered:
            item = self._nav_items.get(mid) or self._menu_meta.get(mid) or {}
            # preferred 即使未进侧栏也可开
            if mid != preferred and not self._nav_item_want_show(mid, item):
                continue
            ok, _ = can_open(mid)
            if ok:
                self.navigate(mid)
                return

        if gid == "home":
            self.navigate("home")
            return

        # 切子模块失败时不要推回首页（否则顶栏「系统」一点就弹回）
        reason = ""
        for mid in ordered:
            item = self._nav_items.get(mid) or {}
            if mid != preferred and not self._nav_item_want_show(mid, item):
                continue
            ok, reason = can_open(mid)
            if not ok:
                break
        try:
            from services.user_plan_presentation import user_access_block_message

            block_msg = user_access_block_message()
        except Exception:
            block_msg = "该功能需正式版"
        self.show_status(
            reason or block_msg or "该子模块暂无可用功能",
            level=StatusLevel.WARNING,
        )
        self._update_domain_tab_checks()

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
        immersive_on = bool(hk.get("enable_immersive_hotkey", True))
        mapping = {
            str(hk.get("exit_app") or "Ctrl+Q"): self._quit_app,
            str(hk.get("restart_app") or "Ctrl+Shift+R"): self._restart_app,
            str(hk.get("open_settings") or "Alt+S"): self.open_system_settings,
            str(hk.get("switch_user") or "Alt+U"): self._show_switch_user,
            str(hk.get("open_about") or "Alt+Shift+O"): self._show_about,
            str(hk.get("open_home") or "Ctrl+H"): self._go_home,
            "Ctrl+K": self._open_command_palette,
            # 顶栏主菜单循环；事件过滤器优先拦截 Tab 焦点占用，此处作 ApplicationShortcut 兜底
            str(hk.get("next_domain") or "Ctrl+Tab"): lambda: self.cycle_domain(1),
            str(hk.get("prev_domain") or "Ctrl+Shift+Tab"): lambda: self.cycle_domain(-1),
        }
        # 沉浸全屏：仅 ApplicationShortcut（禁止 RegisterHotKey）；可配置关闭
        if immersive_on and fs_key and fs_key.lower() != "none":
            mapping[fs_key] = self._toggle_fullscreen
            if fs_key.upper() != "F11":
                mapping["F11"] = self._toggle_fullscreen
        from services.module_hotkeys import (
            get_module_shortcut,
            global_module_bindings,
            normalize_module_id,
        )

        # 应用前台快捷键与 OS 全局绑定同源，避免双开跳过 RegisterHotKey 后 Alt+T 等失效
        for seq, mid in global_module_bindings().items():
            if not seq or seq in mapping:
                continue
            if mid == "ocr_tool":
                mapping[seq] = self._run_ocr_hotkey
            elif mid == "clipboard_history":
                mapping[seq] = self._open_clipboard_quick
            else:
                mapping[seq] = lambda _checked=False, m=mid: self._summon_module(m)

        # 沉浸/列预览：不进 RegisterHotKey，仅应用级
        for mid in ("column_preview",):
            seq = get_module_shortcut(mid)
            if not seq or seq.lower() == "none" or seq in mapping:
                continue
            if mid == "column_preview" and seq.upper() in (fs_key.upper(), "F11"):
                continue
            mapping[seq] = self.toggle_immersive

        # 截图：优先 OS 全局 RegisterHotKey；此处 ApplicationShortcut 作窗内兜底
        # （全局注册成功时系统不会把键交给 Qt，不会双开；全局失败时前台仍可截）
        if hk.get("enable_screenshot", True):
            from services.screenshot_service import run_screenshot_hotkey

            shot = str(hk.get("screenshot") or "").strip()
            if shot and shot.lower() != "none" and shot not in mapping:
                mapping[shot] = lambda: run_screenshot_hotkey(self, full=False)
            shot_full = str(hk.get("screenshot_region") or "").strip()
            if shot_full and shot_full.lower() != "none" and shot_full not in mapping:
                mapping[shot_full] = lambda: run_screenshot_hotkey(self, full=True)

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

    def _start_hotkey_watchdog(self) -> None:
        """被占用后自动重试；开发版遇正式版时让出。"""
        if getattr(self, "_hotkey_watch", None) is not None:
            return
        from PySide6.QtCore import QTimer

        timer = QTimer(self)
        timer.setInterval(4000)
        timer.timeout.connect(self._reconcile_global_hotkeys)
        timer.start()
        self._hotkey_watch = timer
        QTimer.singleShot(1200, self._reconcile_global_hotkeys)
        QTimer.singleShot(3500, self._reconcile_global_hotkeys)

    def _reconcile_global_hotkeys(self) -> None:
        try:
            from services.global_hotkey_bindings import reconcile_global_hotkeys_for_shell

            reconcile_global_hotkeys_for_shell(self)
        except Exception:
            logger.debug("hotkey reconcile failed", exc_info=True)

    def reload_window_hotkeys(self) -> dict[str, str]:
        """设置页保存后重载应用级 + 全局快捷键。"""
        self._apply_shell_feature_flags()
        self._register_hotkeys()
        self._update_fullscreen_button_tip()
        self._start_hotkey_watchdog()
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
        """Ctrl+Tab / Ctrl+Shift+Tab：循环切换顶栏一级子模块（主菜单）。"""
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
        if (
            event.key() == Qt.Key.Key_F11
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and bool(get_hotkeys_config().get("enable_immersive_hotkey", True))
        ):
            self._toggle_fullscreen()
            event.accept()
            return
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
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, m=module_id, b=btn: self._on_nav_context_menu(m, b.mapToGlobal(pos))
        )
        btn.clicked.connect(lambda _=False, m=module_id: self._on_nav_clicked(m))
        self._nav_buttons[module_id] = btn
        self._nav_items[module_id] = menu_item
        self._nav_layout.addWidget(btn)

    def _on_nav_context_menu(self, module_id: str, global_pos) -> None:
        """侧栏右键：置为 / 取消一级菜单（写本机 menu.yml）。"""
        from core.user_messages import ask_confirm, show_warning
        from services.menu_promote import (
            PROMOTE_BLOCK_IDS,
            demote_module_from_top_level,
            is_top_level_module,
            promote_module_to_top_level,
        )

        mid = str(module_id or "").strip()
        if not mid or mid in SYSTEM_ACTIONS or mid.startswith("__"):
            return
        item = self._nav_items.get(mid) or self._menu_meta.get(mid) or {}
        name = str(item.get("name") or mid)
        menu = QMenu(self)
        if is_top_level_module(mid, item=item):
            act = menu.addAction("取消一级菜单")
            act.setToolTip("降回原来的侧栏分组")
            chosen = menu.exec(global_pos)
            if chosen is not act:
                return
            if not ask_confirm(self, f"将「{name}」取消一级菜单，降回侧栏？", title="取消一级菜单"):
                return
            ok, msg = demote_module_from_top_level(mid)
        else:
            if mid in PROMOTE_BLOCK_IDS:
                show_warning(self, "系统入口不可置为一级菜单。")
                return
            act = menu.addAction("置为一级菜单")
            act.setToolTip("提升为顶栏独立 Tab；仅一项时侧栏会自动隐藏")
            chosen = menu.exec(global_pos)
            if chosen is not act:
                return
            if not ask_confirm(
                self,
                f"将「{name}」置为一级菜单？\n顶栏将出现独立 Tab。",
                title="置为一级菜单",
            ):
                return
            ok, msg = promote_module_to_top_level(mid)
        if not ok:
            show_warning(self, msg)
            return
        self._on_nav_rebuild()
        self.show_status(msg, level=StatusLevel.SUCCESS)
        if ok and not is_top_level_module(mid):
            # 刚降级：回到目标域
            item2 = get_menu_item_by_id(mid) or {}
            gid = str(item2.get("group") or "business")
            self.select_domain(gid, navigate_first=False)
            self.navigate(mid)
        elif ok:
            self.select_domain(mid, navigate_first=True)

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
        try:
            page = create_page(module_id, item)
        except SystemExit as e:
            logger.error("模块建页试图退出进程（已拦截）mid=%s code=%s", module_id, e.code)
            show_warning(self, f"「{self._loading_guest_title(module_id)}」加载异常，外壳仍可用。")
            return None
        except Exception:
            logger.exception("创建模块页失败: %s", module_id)
            show_warning(self, f"无法打开「{self._loading_guest_title(module_id)}」，外壳仍可用。")
            return None
        if page is None:
            return None
        self._pages[module_id] = page
        self._stack.addWidget(page)
        return page

    def _safe_call_page(self, page, method: str, *args, **kwargs) -> None:
        """Guest 页回调失败不得拖垮主壳（含拦截 SystemExit）。"""
        if page is None or not hasattr(page, method):
            return
        try:
            getattr(page, method)(*args, **kwargs)
        except SystemExit as e:
            logger.error(
                "页面 %s.%s 试图退出进程（已拦截）code=%s",
                type(page).__name__,
                method,
                e.code,
            )
            self.show_status("子页异常已隔离，外壳继续", level=StatusLevel.WARNING)
        except Exception:
            logger.exception("页面 %s.%s 异常（已隔离，壳继续）", type(page).__name__, method)
            try:
                self.show_status("子页异常已隔离，外壳继续", level=StatusLevel.WARNING)
            except Exception:
                pass

    def _safe_purge_web_embed(self, page) -> None:
        """仅销毁内嵌 WebEngine View；禁止 processEvents / 禁止丢弃整页。"""
        if page is None:
            return
        mid = getattr(page, "page_id", None) or type(page).__name__
        logger.debug("purge web embed mid=%s", mid)
        try:
            if hasattr(page, "_destroy_web_embed"):
                page._destroy_web_embed()
        except SystemExit:
            logger.error("销毁 WebEmbed 时试图退出进程（已拦截）")
        except Exception:
            logger.debug("延迟销毁 WebEngine 失败", exc_info=True)

    def _purge_stale_web_embeds(self, *, except_mid: str | None = None) -> None:
        """进任一引擎页前，拆掉其它模块残留 View，禁止多 Chromium 并存。"""
        for mid, page in list(self._pages.items()):
            if except_mid and mid == except_mid:
                continue
            if mid not in _WEBENGINE_MODULE_IDS:
                continue
            self._safe_purge_web_embed(page)

    def _page_is_web_heavy(self, module_id: str | None, page) -> bool:
        if not module_id or module_id not in _WEBENGINE_MODULE_IDS or page is None:
            return False
        check = getattr(page, "uses_webengine_embed", None)
        if callable(check):
            try:
                return bool(check())
            except Exception:
                return False
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            return any(isinstance(c, QWebEngineView) for c in page.findChildren(QWebEngineView))
        except Exception:
            return module_id in _WEBENGINE_MODULE_IDS

    def _leave_guest(self, leaving: str | None, leaving_page, *, mid: str) -> bool:
        """软离当前 Guest。返回是否曾为 web-heavy。"""
        if leaving_page is None or not leaving or leaving == mid:
            return False
        web_heavy = self._page_is_web_heavy(leaving, leaving_page)
        if hasattr(leaving_page, "soft_leave"):
            self._safe_call_page(leaving_page, "soft_leave")
        else:
            self._safe_call_page(leaving_page, "on_leave")
        return web_heavy

    def _handoff_engine_embed(self, page) -> None:
        """引擎↔引擎：只清本页引用，共享 View 留给下一页 acquire（禁止 hide/Stop）。"""
        if page is None:
            return
        mid = getattr(page, "page_id", None) or type(page).__name__
        logger.debug("handoff engine embed mid=%s", mid)
        try:
            if hasattr(page, "_handoff_web_embed"):
                page._handoff_web_embed()
            elif hasattr(page, "_host") and hasattr(page._host, "detach_view"):
                setattr(page, "_view", None)
                setattr(page, "_embedded_url", "")
                setattr(page, "_web_embedded_ok", False)
                page._host.detach_view(hide=False)
        except SystemExit:
            logger.error("引擎 handoff 时试图退出进程（已拦截）")
        except Exception:
            logger.debug("引擎 handoff 失败", exc_info=True)

    def _schedule_purge_if_needed(self, web_heavy: bool, leaving_page) -> None:
        """跨模块离开 web-heavy：立刻拆引用（deleteLater 仍由业务页延迟）。

        禁止再「等 300ms 再 purge」——下一页 enter 会在等待窗口内再建第二份 WebEngine，原生闪退。
        引擎↔引擎勿走此路径（用 _handoff_engine_embed）。
        """
        if not web_heavy or leaving_page is None:
            return
        self._safe_purge_web_embed(leaving_page)

    def _loading_guest_title(self, module_id: str) -> str:
        item = self._menu_meta.get(module_id) or get_menu_item_by_id(module_id) or {}
        return str(item.get("name") or module_id)

    def _ensure_loading_guest(self, module_id: str) -> BasePage:
        existing = self._loading_guests.get(module_id)
        if existing is not None:
            return existing
        page = _LoadingGuestPage(module_id, self._loading_guest_title(module_id), self)
        self._loading_guests[module_id] = page
        self._stack.addWidget(page)
        return page

    def _discard_loading_guest(self, module_id: str) -> None:
        page = self._loading_guests.pop(module_id, None)
        if page is None:
            return
        try:
            self._stack.removeWidget(page)
            page.deleteLater()
        except Exception:
            logger.debug("discard loading guest failed", exc_info=True)

    def _apply_nav_chrome(self, mid: str, *, title: str | None = None) -> None:
        """只更新壳 chrome（顶栏域/侧栏勾选/状态），不创建业务页。"""
        if not self.updatesEnabled():
            self.setUpdatesEnabled(True)
        self.set_page_shortcuts(None)
        self._current_id = mid
        self._st.set_module(mid)
        self._sync_domain_for_module(mid)
        for nav_mid, btn in self._nav_buttons.items():
            btn.setChecked(nav_mid == mid)
        label = title or self._loading_guest_title(mid)
        self.show_status(f"当前：{label}", level=StatusLevel.INFO)

    def navigate(self, module_id: str) -> None:
        """固若金汤：先切壳，子页未就绪显示 Loading；狂切也不应拖垮主窗。"""
        try:
            self._navigate_impl(module_id)
        except SystemExit as e:
            logger.error("navigate 试图退出进程（已拦截）code=%s", e.code)
            self.show_status("导航异常已隔离", level=StatusLevel.WARNING)
        except Exception:
            logger.exception("navigate 异常（已隔离，壳继续） mid=%r", module_id)
            try:
                self.show_status("导航异常已隔离，外壳仍可用", level=StatusLevel.WARNING)
                self._sync_nav_checks()
            except Exception:
                pass

    def _navigate_impl(self, module_id: str) -> None:
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

        try:
            self._clear_webengine_focus()
        except Exception:
            logger.debug("clear webengine focus failed", exc_info=True)

        from PySide6.QtCore import QTimer

        leaving = self._current_id
        leaving_page = self._pages.get(leaving) if leaving else None
        web_heavy = self._leave_guest(leaving, leaving_page, mid=mid)

        self._nav_seq = getattr(self, "_nav_seq", 0) + 1
        seq = self._nav_seq
        self._apply_nav_chrome(mid)

        # 子页尚未缓存：Loading 进度 → 下一拍建页（可随时点走）
        if mid not in self._pages:
            guest = self._ensure_loading_guest(mid)
            try:
                self._stack.setCurrentWidget(guest)
            except Exception:
                logger.exception("切换 LoadingGuest 失败 mid=%s", mid)
                self._sync_nav_checks()
                return
            self.show_status(
                f"正在打开：{self._loading_guest_title(mid)}",
                level=StatusLevel.INFO,
            )
            # 立刻拆离开页 View；enter 再等 deleteLater / 共享归还落稳
            enter_delay = 0
            engine_handoff = (
                web_heavy
                and leaving in _WEBENGINE_MODULE_IDS
                and mid in _WEBENGINE_MODULE_IDS
            )
            if engine_handoff:
                # 引擎↔引擎：软交接共享 View，短延迟仅等主栈切页，禁止 hide/Stop 白闪
                enter_delay = 80
                self._handoff_engine_embed(leaving_page)
            elif web_heavy and leaving_page is not None and leaving != mid:
                # 引擎 → 业务/其它：彻底拆 Chromium 再进页（900ms 不够仍会与 Excel 叠崩）
                enter_delay = 1200 if mid not in _WEBENGINE_MODULE_IDS else 500
                self._schedule_purge_if_needed(web_heavy, leaving_page)
                if mid in _WEBENGINE_MODULE_IDS:
                    self._purge_stale_web_embeds(except_mid=mid)
                else:
                    self._purge_stale_web_embeds(except_mid=None)
                    try:
                        from services.shared_local_webengine import shutdown as shutdown_shared

                        shutdown_shared()
                    except Exception:
                        pass
            elif mid in _WEBENGINE_MODULE_IDS:
                self._purge_stale_web_embeds(except_mid=mid)
            logger.info(
                "navigate mid=%s leaving=%s web_heavy=%s enter_delay=%s",
                mid,
                leaving,
                web_heavy,
                enter_delay,
            )
            QTimer.singleShot(
                0,
                lambda s=seq, m=mid, d=enter_delay: self._async_ensure_page(
                    s, m, enter_delay=d
                ),
            )
            return

        page = self._pages[mid]
        self._discard_loading_guest(mid)
        try:
            self._stack.setCurrentWidget(page)
        except Exception:
            logger.exception("切换 ModuleHost 失败 mid=%s", mid)
            self._sync_nav_checks()
            return
        title = page.page_title or mid
        self.show_status(f"当前：{title}", level=StatusLevel.INFO)

        enter_delay = 0
        engine_handoff = (
            web_heavy
            and leaving in _WEBENGINE_MODULE_IDS
            and mid in _WEBENGINE_MODULE_IDS
        )
        if engine_handoff:
            enter_delay = 80
            self._handoff_engine_embed(leaving_page)
        elif web_heavy and leaving_page is not None and leaving != mid:
            enter_delay = 1200 if mid not in _WEBENGINE_MODULE_IDS else 500
            self._schedule_purge_if_needed(web_heavy, leaving_page)
            if mid in _WEBENGINE_MODULE_IDS:
                self._purge_stale_web_embeds(except_mid=mid)
            else:
                self._purge_stale_web_embeds(except_mid=None)
                try:
                    from services.shared_local_webengine import shutdown as shutdown_shared

                    shutdown_shared()
                except Exception:
                    pass
        elif mid in _WEBENGINE_MODULE_IDS:
            self._purge_stale_web_embeds(except_mid=mid)
        logger.info(
            "navigate mid=%s leaving=%s web_heavy=%s enter_delay=%s (cached)",
            mid,
            leaving,
            web_heavy,
            enter_delay,
        )
        QTimer.singleShot(enter_delay, lambda s=seq, m=mid: self._deferred_page_enter(s, m))

    def _async_ensure_page(self, seq: int, mid: str, *, enter_delay: int = 0) -> None:
        """异步建页。用户已点走时仍可后台建缓存，但不抢栈、不进 on_enter。"""
        from PySide6.QtCore import QTimer

        try:
            still_here = getattr(self, "_nav_seq", 0) == seq and self._current_id == mid
            page = self._pages.get(mid)
            if page is None:
                page = self._ensure_page(mid)
            if page is None:
                if still_here:
                    self._discard_loading_guest(mid)
                    self.show_status(
                        f"无法打开「{self._loading_guest_title(mid)}」",
                        level=StatusLevel.WARNING,
                    )
                return

            if hasattr(page, "request_deferred_ui"):
                self._safe_call_page(page, "request_deferred_ui")

            if not still_here:
                self._discard_loading_guest(mid)
                if self._stack.currentWidget() is page:
                    cur = self._pages.get(self._current_id)
                    if cur is not None and cur is not page:
                        try:
                            self._stack.setCurrentWidget(cur)
                        except Exception:
                            pass
                return

            self._discard_loading_guest(mid)
            try:
                self._stack.setCurrentWidget(page)
            except Exception:
                logger.exception("异步切到页面失败 mid=%s", mid)
                return
            title = page.page_title or mid
            self.show_status(f"当前：{title}", level=StatusLevel.INFO)
            delay = max(0, int(enter_delay or 0))
            if delay > 0:
                QTimer.singleShot(
                    delay, lambda s=seq, m=mid: self._deferred_page_enter(s, m)
                )
            else:
                self._deferred_page_enter(seq, mid)
        except SystemExit as e:
            logger.error("异步建页试图退出进程（已拦截）mid=%s code=%s", mid, e.code)
        except Exception:
            logger.exception("异步建页失败 mid=%s（壳继续）", mid)
            if getattr(self, "_nav_seq", 0) == seq and self._current_id == mid:
                try:
                    self._discard_loading_guest(mid)
                    self.show_status(
                        f"打开「{self._loading_guest_title(mid)}」失败，外壳仍可用",
                        level=StatusLevel.WARNING,
                    )
                except Exception:
                    pass

    def _deferred_page_enter(self, seq: int, mid: str) -> None:
        if getattr(self, "_nav_seq", 0) != seq:
            return
        if self._current_id != mid:
            return
        page = self._pages.get(mid)
        if page is None:
            return
        if hasattr(page, "request_deferred_ui"):
            self._safe_call_page(page, "request_deferred_ui")
        self._safe_call_page(page, "on_enter")
        self._safe_call_page(page, "schedule_primary_focus")

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

    def _clear_webengine_focus(self) -> None:
        """切页前卸掉 WebEngine 焦点，减轻 Windows 上栈切换原生闪退。"""
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception:
            return
        fw = QApplication.focusWidget()
        while fw is not None:
            if isinstance(fw, QWebEngineView):
                fw.clearFocus()
                self.setFocus(Qt.FocusReason.OtherFocusReason)
                return
            fw = fw.parentWidget()

    def _open_module_direct(self, module_id: str) -> bool:
        """授权已通过校验后直接打开模块（避免 navigate 递归）。"""
        # 与 navigate 同一套离开 WebEngine 逻辑
        self.navigate(module_id)
        return self._current_id == module_id

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
        """用户修改系统信息后刷新顶栏品牌。"""
        from services.system_info import get_system_info

        info = get_system_info()
        if self._brand_label is not None:
            self._brand_label.setText(str(info.get("brand_name") or self._st.brand_name()))
        ui = get_ui_config()
        title = str(info.get("window_title") or ui.get("window_title") or info.get("brand_name") or "")
        if title:
            self._apply_window_title(title)
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
