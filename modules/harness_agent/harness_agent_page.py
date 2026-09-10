# -*- coding: utf-8 -*-
"""
DeepSeek Harness · 侧栏任务页（group: engines）

流程：先画壳（启停 + 状态 + WebEngine 占位）→ 读安装 → 读服务 → 就绪后加载 URL。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import ask_confirm, show_saved, show_warning
from modules.harness_agent.feed_strip import FeedStrip
from modules.harness_agent.setup_gate import SetupGate
from services.harness_chrome import BusyPhase, compute_chrome, infer_busy_phase
from services.harness_config import load_harness_config, web_url
from services.harness_progress import (
    HINT,
    IDLE,
    TITLE,
    TOAST,
    Progress,
    clip_user_detail,
    sanitize_user_text,
)
from services.harness_export import export_most_recent_session
from services.harness_feed import copy_to_clipboard, format_feed_message, peek_feed, pop_feed
from services.harness_probe import HarnessPageState, probe_page_state
from services.harness_setup import install_harness_runtime, repair_harness_runtime, uninstall_harness_runtime
from services.harness_sidecar import (
    is_running,
    log_suggests_plugin_boot_failure,
    open_config_dir,
    open_install_root,
    open_sidecar_log,
    prepare_sidecar_start,
    sidecar_log_path,
    sidecar_start_progress,
    spawn_sidecar_process,
    stop,
)
from services.harness_status import HarnessStatus, InstallState, ServiceState, read_harness_status
from services.harness_surface import (
    open_in_system_browser,
    prefer_browser,
    prefer_embed,
    set_surface_mode,
)
from services.os_open import open_in_file_manager
from services.storage_paths import module_data_dir, module_output_dir
from widgets import (
    DangerButton,
    HintLabel,
    MenuButton,
    PrimaryButton,
    SecondaryButton,
    SectionTitle,
    SoftActivityBar,
)


def _webengine_available() -> bool:
    from services.qt_webengine_bootstrap import webengine_import_ok

    return webengine_import_ok()


def _qt_alive(obj) -> bool:
    """C++ 对象是否仍有效（防 already deleted 拖垮主窗）。"""
    if obj is None:
        return False
    try:
        from shiboken6 import isValid

        return bool(isValid(obj))
    except Exception:
        try:
            obj.objectName()
            return True
        except RuntimeError:
            return False


class _HarnessInstallWorker(QObject):
    """后台下载/解压官方或预制包。"""

    progress = Signal(str, int, str)  # msg, pct, stage
    finished = Signal(bool, str, str)  # ok, text, flavor

    def __init__(self, flavor: str, cancel_event) -> None:
        super().__init__()
        self._flavor = flavor
        self._cancel_event = cancel_event

    def run(self) -> None:
        def _prog(msg: str, pct: int, stage: str = "") -> None:
            self.progress.emit(msg, int(pct), str(stage or ""))

        def _cancel() -> bool:
            return bool(self._cancel_event.is_set())

        try:
            ok, text = install_harness_runtime(
                self._flavor,
                progress=_prog,
                cancel=_cancel,
            )
            self.finished.emit(bool(ok), str(text or ""), self._flavor)
        except Exception as exc:
            self.finished.emit(False, str(exc) or exc.__class__.__name__, self._flavor)


class _HarnessF11Filter(QObject):
    """WebEngine 内拦截 F11，避免落到系统/浏览器快捷键。"""

    def __init__(self, page: "HarnessAgentPage") -> None:
        super().__init__(page)
        self._page = page

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            return False
        if event.key() != Qt.Key.Key_F11 or event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        shell = self._page.window()
        if shell is None or not hasattr(shell, "_toggle_fullscreen"):
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
        else:
            shell._toggle_fullscreen()
        return True


def _make_harness_accept_nav(*, base_url: str):
    from PySide6.QtCore import QUrl

    base = QUrl(base_url)
    host = (base.host() or "").lower()

    def _accept(url, _nav_type, is_main_frame) -> bool:
        if is_main_frame and url.scheme() in ("http", "https") and host:
            target_host = (url.host() or "").lower()
            if target_host and target_host != host:
                return False
        return True

    return _accept


def _make_harness_web_page(profile, view, *, base_url: str):
    from services.webengine_host import ToaWebEnginePage

    return ToaWebEnginePage(
        profile, view, accept_nav=_make_harness_accept_nav(base_url=base_url)
    )


class _HarnessWebHost(QWidget):
    """栈式宿主：占位 / WebView 互斥，避免 VBox 双控件 + 遮罩叠层抖窗。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HarnessWebHost")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        from PySide6.QtWidgets import QStackedLayout

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self._placeholder = QLabel()
        self._placeholder.setObjectName("HarnessWebPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)
        # 浮动遮罩已废弃：盖在 Chromium 上会持续闪；加载态只用栈内占位页
        self._overlay = QLabel(self)
        self._overlay.setObjectName("HarnessWebOverlay")
        self._overlay.hide()
        self._view = None

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def set_placeholder(self, text: str) -> None:
        try:
            self._placeholder.setText(text)
            self._stack.setCurrentWidget(self._placeholder)
            if self._overlay.isVisible():
                self._overlay.hide()
        except Exception:
            pass

    def clear_view_ref(self) -> None:
        self._view = None

    def detach_view(self, *, hide: bool = True) -> None:
        view = self._view
        self._view = None
        if view is None:
            return
        try:
            self._stack.setCurrentWidget(self._placeholder)
        except Exception:
            pass
        try:
            self._stack.removeWidget(view)
        except Exception:
            pass
        if hide:
            try:
                view.hide()
            except Exception:
                pass

    def embed_view(self, view: QWidget, *, loading: bool | None = None) -> None:
        """挂入 WebView。loading 时只显示占位，禁止半透明/不透明层盖在 Chromium 上。"""
        if view is None:
            return
        self._view = view
        already = False
        try:
            already = (
                self._stack.indexOf(view) >= 0
                and self._stack.currentWidget() is view
                and view.isVisible()
            )
        except Exception:
            already = False
        if self._stack.indexOf(view) < 0:
            try:
                view.hide()
            except Exception:
                pass
            self._stack.addWidget(view)
        show_loading = (not already) if loading is None else bool(loading)
        try:
            if self._overlay.isVisible():
                self._overlay.hide()
                self._overlay.clear()
        except Exception:
            pass
        if show_loading:
            if not (self._placeholder.text() or "").strip():
                self._placeholder.setText("正在准备 DeepSeek Harness…")
            try:
                view.hide()
            except Exception:
                pass
            self._stack.setCurrentWidget(self._placeholder)
            return
        try:
            view.show()
            self._stack.setCurrentWidget(view)
        except Exception:
            self._stack.setCurrentWidget(self._placeholder)

    def set_overlay_text(self, text: str | None, *, block_input: bool = True) -> None:
        """加载提示改走占位页；就绪必须回到 WebView（禁止浮动层盖 Chromium）。"""
        try:
            if self._overlay.isVisible():
                self._overlay.hide()
                self._overlay.clear()
        except Exception:
            pass
        try:
            if text and block_input:
                self._placeholder.setText(text)
                self._stack.setCurrentWidget(self._placeholder)
                if self._view is not None:
                    try:
                        self._view.hide()
                    except Exception:
                        pass
            else:
                # 揭罩：若已有 View 则显示
                if self._view is not None:
                    try:
                        self._view.show()
                        self._stack.setCurrentWidget(self._view)
                    except Exception:
                        pass
        except RuntimeError:
            pass


class HarnessAgentPage(BasePage):
    page_id = "harness_agent"
    page_title = "DeepSeek Harness"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        self._profile = None
        self._web_ready = _webengine_available()
        self._action_busy = False
        self._busy_phase = BusyPhase.IDLE
        self._busy_label = ""
        self._setup_state = HarnessPageState.STOPPED
        self._status: HarnessStatus | None = None
        self._start_deadline = 0.0
        self._load_web_timer = QTimer(self)
        self._load_web_timer.setSingleShot(True)
        self._load_web_timer.timeout.connect(self._do_scheduled_load_web)
        self._load_web_force = False
        self._web_embedded_ok = False
        self._web_nav_overlay = False
        self._load_started_wired = False
        self._pending_prepare_after_reload = False
        self._prepare_retry = 0
        self._status_checked_at = 0.0
        self._STATUS_STALE_S = 12.0
        self._prewarm_done = False
        self._more_menu_signature: tuple[bool, bool] | None = None
        self._f11_filter = _HarnessF11Filter(self)
        self._auto_start_tried = False
        self._browser_surface_opened = False
        # 用户点过「停止」后禁止 auto_start / 修密钥拉起，直到主动启动或重启
        self._user_stopped = False
        self._progress = Progress.ENTER
        self._reveal_token = 0
        self._load_watch_token = 0
        self._cred_heal_tried = False
        self._plugin_heal_tried = False
        # 进/离页代次：作废回调
        self._visit_gen = 0
        self._install_thread: QThread | None = None
        self._install_worker: _HarnessInstallWorker | None = None
        self._install_cancel = None
        self._install_flavor = ""

        m = page_content_margins()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(m[0], m[1], m[2], max(4, m[3]))
        outer.setSpacing(6)

        # --- 工具栏：启停 + 辅助 ---
        self._service_bar = QWidget()
        bar = QHBoxLayout(self._service_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)

        self._status_label = SectionTitle("DeepSeek Harness")
        self._status_label.setMinimumWidth(148)
        bar.addWidget(self._status_label)

        self._btn_start = PrimaryButton("启动服务")
        self._btn_start.setMinimumWidth(96)
        self._btn_start.setMinimumHeight(32)
        self._btn_start.clicked.connect(self._on_start)

        self._btn_stop = DangerButton("停止服务")
        self._btn_stop.setMinimumWidth(96)
        self._btn_stop.setMinimumHeight(32)
        self._btn_stop.clicked.connect(self._on_stop)

        self._start_stop_stack = QStackedWidget()
        self._start_stop_stack.setMinimumWidth(100)
        self._start_stop_stack.setMinimumHeight(32)
        self._start_stop_stack.addWidget(self._btn_start)
        self._start_stop_stack.addWidget(self._btn_stop)
        bar.addWidget(self._start_stop_stack)

        # 失败时一眼能点到，不藏「更多」里
        self._btn_repair = SecondaryButton("一键修复")
        self._btn_repair.setMinimumWidth(88)
        self._btn_repair.setMinimumHeight(32)
        self._btn_repair.setToolTip("修复运行环境后自动重启（坏了优先点这个）")
        self._btn_repair.clicked.connect(self._on_repair_env)
        bar.addWidget(self._btn_repair)

        # 浏览器 = 另开同一地址，不是另一套启停；次要按钮
        self._btn_open_browser = SecondaryButton("在浏览器打开")
        self._btn_open_browser.setMinimumWidth(120)
        self._btn_open_browser.setMinimumHeight(32)
        self._btn_open_browser.setToolTip("另开系统浏览器（与本页同一服务地址）")
        self._btn_open_browser.clicked.connect(self._open_external)
        bar.addWidget(self._btn_open_browser)

        self._btn_refresh = SecondaryButton("刷新")
        self._btn_refresh.setMinimumWidth(72)
        self._btn_refresh.setMinimumHeight(32)
        self._btn_refresh.setToolTip("回到 Harness 主界面并重新装载（深链卡住时用这个）")
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        bar.addWidget(self._btn_refresh)

        self._btn_more = MenuButton("更多")
        self._btn_more.setMinimumWidth(80)
        self._btn_more.setMinimumHeight(32)
        self._more_menu = QMenu(self)
        self._btn_more.setMenu(self._more_menu)
        bar.addWidget(self._btn_more)

        bar.addStretch(1)
        outer.addWidget(self._service_bar)
        self._rebuild_more_menu()

        # --- 状态一行 + 细活动条（常占位，忙碌淡入，避免进页咔咔蹦）---
        self._service_line = HintLabel("状态：检测中…")
        self._service_line.setWordWrap(True)
        outer.addWidget(self._service_line)

        self._action_progress = SoftActivityBar()
        outer.addWidget(self._action_progress)

        self._feed_strip = FeedStrip(self)
        self._feed_strip.hide()
        self._feed_strip.apply_requested.connect(self._apply_feed_clipboard)
        self._feed_strip.dismissed.connect(self._dismiss_feed)
        self._feed_strip.open_folder_requested.connect(self._open_feed_workspace_folder)
        outer.addWidget(self._feed_strip)

        # --- 未安装 / 待 Key：四步开用 ---
        self._setup_gate = SetupGate(self)
        self._setup_gate.install_requested.connect(self._on_one_click_install)
        self._setup_gate.cancel_install_requested.connect(self._on_cancel_install)
        self._setup_gate.key_saved.connect(self._after_key_saved)
        self._setup_gate.open_settings_requested.connect(self._open_settings)

        # --- 主区：安装门 vs 工作区（Stack 避免双 stretch 互 hide 引发布局抖动）---
        self._body_stack = QStackedWidget()
        self._body_stack.addWidget(self._setup_gate)

        self._web_wrap = QWidget()
        web_outer = QVBoxLayout(self._web_wrap)
        web_outer.setContentsMargins(0, 0, 0, 0)
        web_outer.setSpacing(0)

        self._host = _HarnessWebHost()
        if not self._web_ready:
            self._host.set_placeholder(
                "服务未启动时请点「启动服务」；无内嵌引擎时可「在浏览器打开」。"
            )
        else:
            self._host.set_placeholder(IDLE[Progress.NEED_START].replace("\n", " · "))
        web_outer.addWidget(self._host, 1)
        self._body_stack.addWidget(self._web_wrap)
        self._body_stack.setCurrentIndex(1)
        outer.addWidget(self._body_stack, 1)

        self._sync_service_bar_placeholder()

    def _sync_service_bar_placeholder(self) -> None:
        self._btn_start.setEnabled(False)
        self._btn_open_browser.setEnabled(False)
        self._start_stop_stack.setCurrentIndex(0)

    def _rebuild_more_menu(self) -> None:
        st = self._status
        running = bool(st.running) if st is not None else False
        embed = prefer_embed()
        signature = (running, embed)
        if signature == self._more_menu_signature:
            return
        self._more_menu_signature = signature
        self._more_menu.clear()

        # 日常：重启 / 回退（「一键修复」已在工具栏，勿重复）
        self._more_menu.addAction("重启服务", self._on_restart)
        self._more_menu.addAction("回到主界面", self._on_go_home)
        self._more_menu.addAction("恢复上次可用配置", self._on_restore_last_good)

        open_menu = self._more_menu.addMenu("打开…")
        open_menu.addAction("启动日志", self._open_sidecar_log)
        open_menu.addAction("安装目录", self._open_install_root)
        open_menu.addAction("会话数据目录", self._open_dsh_home)
        open_menu.addAction("导出最近会话", self._export_recent)

        self._more_menu.addSeparator()
        # 表面偏好：只影响是否默认另开浏览器，启停/主区装载口径不变
        if embed:
            self._more_menu.addAction("偏好：启动后另开系统浏览器", self._switch_to_browser_surface)
        else:
            self._more_menu.addAction("偏好：以套件内嵌为主", self._switch_to_embed_surface)

        self._more_menu.addSeparator()
        self._more_menu.addAction("设置…", self._open_settings)
        self._more_menu.addAction("卸载…", self._on_uninstall)

    def primary_focus_widget(self):
        if self._setup_state == HarnessPageState.NEEDS_KEY and self._body_stack.currentIndex() == 0:
            return self._setup_gate._key_edit
        # 未启动 → 启动；运行中 → 停止。勿把焦点丢给 WebEngine / 「在浏览器打开」
        if self._body_stack.currentIndex() != 1:
            return None
        st = self._status
        if st is None or not st.running:
            return self._btn_start
        return self._btn_stop

    def _page_active(self, visit: int | None = None) -> bool:
        if visit is not None and visit != self._visit_gen:
            return False
        win = self.window()
        if win is not None and getattr(win, "_current_id", None) != self.page_id:
            return False
        return True

    def on_enter(self) -> None:
        """切页：已在跑 → 直接装载；已停 → 结果态；勿无故重启。"""
        self._visit_gen += 1
        visit = self._visit_gen
        # 快速路径：本机已在跑 → 直接揭罩装载，禁止再走启动/修密钥重启
        if not self._user_stopped:
            try:
                st0 = read_harness_status(probe_http=True, http_timeout=0.45)
            except Exception:
                st0 = None
            if st0 is not None and st0.running and st0.install == InstallState.READY:
                self._status = st0
                self._status_checked_at = time.time()
                self._show_workspace()
                self._sync_service_bar()
                self._set_progress(Progress.LOADING_UI, idle=True, toast=False)
                self._sync_web_for_status(st0)
                QTimer.singleShot(0, lambda v=visit: self._on_enter_soft(v))
                return
        if self._user_stopped or (
            self._status_is_fresh()
            and self._status is not None
            and not self._status.running
        ):
            step = Progress.STOPPED if self._user_stopped else Progress.NEED_START
            self._set_progress(step, toast=False, idle=True)
            self._show_workspace()
            self._sync_service_bar()
            QTimer.singleShot(40, lambda v=visit: self._on_enter_deferred(v))
            return
        self._set_progress(Progress.ENTER, toast=False, idle=True)
        if (
            self._view is not None
            and self._web_embedded_ok
            and self._should_keep_embed_on_enter()
        ):
            self._show_workspace()
            self._reveal_web_embed_now()
            self._sync_service_bar()
            QTimer.singleShot(0, lambda v=visit: self._on_enter_soft(v))
            return
        QTimer.singleShot(40, lambda v=visit: self._on_enter_deferred(v))

    def _set_progress(
        self,
        step: Progress,
        *,
        toast: bool = True,
        idle: bool = True,
        level: StatusLevel | None = None,
        extra: str = "",
    ) -> None:
        """统一进度：标题 + 状态行 + 主区占位 + 底栏，口径一致。"""
        self._progress = step
        title = TITLE.get(step, "DeepSeek Harness")
        hint = HINT.get(step, "")
        detail = clip_user_detail(extra) if extra else ""
        if detail:
            hint = f"{hint} · {detail}" if hint else detail
        # 失败/已停：强制启停钮与真实进程一致（禁止「已退出」还显示停止）
        if step in (Progress.FAILED, Progress.STOPPED):
            self._align_chrome_not_running()
        elif step in (
            Progress.NEED_START,
            Progress.NEED_INSTALL,
            Progress.NEED_KEY,
            Progress.NEED_REPAIR,
        ):
            try:
                self._start_stop_stack.setCurrentIndex(0)
                self._btn_open_browser.setEnabled(False)
            except RuntimeError:
                pass

        # 进页短探测：只轻改状态行，不换大标题、不弹条、不 toast——避免咔咔蹦
        ephemeral = step in (
            Progress.ENTER,
            Progress.CHECK_INSTALL,
            Progress.CHECK_SERVICE,
        )
        if ephemeral:
            try:
                self._service_line.setText(hint)
            except RuntimeError:
                return
            return

        try:
            self._status_label.setText(title)
        except RuntimeError:
            return
        try:
            self._service_line.setText(hint)
        except RuntimeError:
            return
        # 活动条只跟服务启停；界面装载用主区遮罩，READY/LOADING 必须硬停条
        service_busy = step in (
            Progress.STOPPING,
            Progress.STARTING,
            Progress.RESTARTING,
        )
        if self._action_busy:
            pass  # 点按反馈已拉起活动条
        elif service_busy:
            self._set_action_progress_visible(True)
        else:
            # 含 LOADING_UI / READY / 停止结果：条必须停，装载只靠主区遮罩
            self._set_action_progress_visible(False)
        if idle and not self._web_embedded_ok:
            body = IDLE.get(step, "")
            if body:
                self._show_web_idle(body, block_input=step not in (
                    Progress.READY,
                    Progress.READY_BROWSER,
                    Progress.STOPPED,
                    Progress.NEED_START,
                    Progress.STARTED,
                ))
        if toast:
            msg = TOAST.get(step, "")
            if extra:
                msg = f"{msg} {clip_user_detail(extra)}".strip()
            if msg:
                lv = level
                if lv is None:
                    if step in (Progress.READY, Progress.READY_BROWSER, Progress.STARTED, Progress.STOPPED):
                        lv = StatusLevel.SUCCESS if step != Progress.STOPPED else StatusLevel.INFO
                    elif step == Progress.FAILED:
                        lv = StatusLevel.WARNING
                    else:
                        lv = StatusLevel.INFO
                self.report_status(msg, level=lv)

    def _paint_status_hint(
        self,
        *,
        install: str | None = None,
        service: str | None = None,
        busy: str | None = None,
    ) -> None:
        """状态栏只留一行：委托 chrome 状态机，保证与按钮一致。"""
        if busy:
            self._service_line.setText(f"状态：{busy}")
            return
        st = self._status
        inst = install
        svc = service
        warn = False
        ready = False
        running = False
        if st is not None:
            ready = st.install == InstallState.READY
            running = bool(st.running)
            if inst is None:
                inst = st.install_label
            if svc is None:
                svc = st.service_label
            warn = "⚠" in (st.detail or "")
        view = compute_chrome(
            install_ready=ready,
            running=running,
            phase=BusyPhase.IDLE,
            install_label=inst or "",
            service_label=svc or "",
            detail_warn=warn,
        )
        self._service_line.setText(view.status_hint)

    def _align_chrome_not_running(self) -> None:
        """进程已停/失败时：刷新状态并显示「启动服务」，勿留「停止服务」。"""
        try:
            st = read_harness_status(probe_http=True, http_timeout=0.45)
            self._status = st
            self._status_checked_at = time.time()
        except Exception:
            pass
        try:
            self._apply_chrome(phase=BusyPhase.IDLE)
        except RuntimeError:
            pass
        # 若探测仍短暂判 running（端口残留），失败态仍强制启动钮
        if self._progress in (Progress.FAILED, Progress.STOPPED, Progress.NEED_START):
            try:
                self._start_stop_stack.setCurrentIndex(0)
                self._btn_start.setEnabled(True)
                self._btn_stop.setEnabled(False)
                self._btn_open_browser.setEnabled(False)
            except RuntimeError:
                pass

    def _present_start_failed(self, msg: str) -> None:
        """启动失败统一出口：清 busy、对齐启停钮、短文案、可触发自愈。"""
        self._set_action_busy(False)
        self._align_chrome_not_running()
        self._set_progress(
            Progress.FAILED,
            extra=clip_user_detail(msg),
            level=StatusLevel.WARNING,
        )
        self._maybe_auto_heal_plugins(msg)

    def _apply_chrome(self, *, phase: BusyPhase | None = None, busy_label: str = "") -> None:
        """按状态机刷新启停栈与按钮（忙碌/空闲统一入口）。"""
        st = self._status
        ready = bool(st and st.install == InstallState.READY)
        running = bool(st and st.running)
        ph = self._busy_phase if phase is None else phase
        label = busy_label or self._busy_label
        inst = st.install_label if st else ""
        svc = st.service_label if st else ""
        warn = bool(st and "⚠" in (st.detail or ""))
        view = compute_chrome(
            install_ready=ready,
            running=running,
            phase=ph,
            busy_label=label,
            install_label=inst,
            service_label=svc,
            detail_warn=warn,
        )
        self._start_stop_stack.setCurrentIndex(view.stack_index)
        self._btn_start.setEnabled(view.start_enabled)
        self._btn_stop.setEnabled(view.stop_enabled)
        self._btn_open_browser.setEnabled(view.open_browser_enabled)
        # 忙碌时仍允许「刷新」探测，避免假死感且可救急
        self._btn_refresh.setEnabled(True)
        self._btn_more.setEnabled(view.more_enabled)
        # 一键修复：工具栏常显（不藏「更多」）
        try:
            self._btn_repair.setVisible(True)
            self._btn_repair.setEnabled(bool(ready) and not view.busy)
            self._btn_repair.setText("一键修复")
        except RuntimeError:
            pass
        self._status_label.setText(view.title)
        self._service_line.setText(view.status_hint)
        self._btn_start.setToolTip(view.tip_start)
        self._btn_stop.setToolTip(view.tip_stop)
        self._btn_open_browser.setToolTip(view.tip_browser)
        self._btn_refresh.setToolTip(
            "回到 Harness 主界面并重新装载（深链卡住时用这个）"
            + ("；当前有操作进行中，仍可强制刷新" if view.busy else "")
        )
        self._btn_more.setToolTip(view.tip_more)
        if view.busy:
            self._set_action_progress_visible(True)
            # 点按反馈：启停钮文案立刻变成进行中
            if ph == BusyPhase.STARTING:
                self._btn_start.setText("启动中…")
            elif ph == BusyPhase.STOPPING:
                self._btn_stop.setText("停止中…")
            elif ph == BusyPhase.RESTARTING:
                self._btn_start.setText("重启中…")
        else:
            self._set_action_progress_visible(False)
            self._btn_start.setText("启动服务")
            self._btn_stop.setText("停止服务")
            self._rebuild_more_menu()

    def _set_action_progress_visible(self, visible: bool, *, immediate: bool = False) -> None:
        try:
            self._action_progress.set_active(bool(visible), immediate=immediate)
        except RuntimeError:
            pass

    def _begin_click_feedback(
        self,
        label: str,
        *,
        phase: BusyPhase,
        progress: Progress | None = None,
    ) -> None:
        """点按当帧立刻反馈：进度条 + 忙碌文案 + 禁主钮（先于任何重活）。"""
        if progress is not None:
            self._set_progress(progress, toast=True)
        self._set_action_busy(True, label, phase=phase)
        # 点按立刻出活动条（不等延迟）
        self._set_action_progress_visible(True, immediate=True)
        # 强制本帧绘制，避免同步重活时看起来「没点上」
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass

    def _on_enter_soft(self, visit: int | None = None) -> None:
        """热回进：已粘住界面时只确认服务状态。"""
        if not self._page_active(visit):
            return
        self._apply_pending_feed()
        self._set_progress(Progress.CHECK_SERVICE, idle=False)
        if self._status_is_fresh() and self._status is not None and self._status.running:
            self._finish_ready_surface()
            return
        QTimer.singleShot(0, lambda v=self._visit_gen: self._refresh_status_http_if(v))

    def _on_enter_deferred(self, visit: int | None = None) -> None:
        if not self._page_active(visit):
            return
        # 已停：检查链静默进行，主区保持「已停止/请启动」，勿刷「正在进入」
        if self._user_stopped or (
            self._status_is_fresh()
            and self._status is not None
            and not self._status.running
        ):
            step = Progress.STOPPED if self._user_stopped else Progress.NEED_START
            self._set_progress(step, toast=False, idle=True)
        else:
            self._set_progress(Progress.ENTER)
        QTimer.singleShot(40, lambda v=visit: self._enter_check_install(v))

    def _enter_check_install(self, visit: int) -> None:
        if not self._page_active(visit):
            return
        # 已知停着：静默检查安装，勿把主区改成「正在检查安装」
        quiet_stopped = self._user_stopped or (
            self._status_is_fresh()
            and self._status is not None
            and not self._status.running
        )
        if not quiet_stopped:
            self._set_progress(Progress.CHECK_INSTALL)
        try:
            from services.harness_model_defaults import ensure_official_default_model

            ensure_official_default_model()
        except Exception:
            pass
        self._apply_pending_feed()
        self._refresh_setup_sync()
        if self._setup_state == HarnessPageState.NOT_INSTALLED:
            self._set_progress(Progress.NEED_INSTALL)
            return
        if self._setup_state == HarnessPageState.NEEDS_KEY:
            self._set_progress(Progress.NEED_KEY)
            return
        self._show_workspace()
        QTimer.singleShot(40, lambda v=visit: self._enter_check_service(v))

    def _enter_check_service(self, visit: int) -> None:
        if not self._page_active(visit):
            return
        quiet_stopped = self._user_stopped or (
            self._status_is_fresh()
            and self._status is not None
            and not self._status.running
        )
        if not quiet_stopped:
            self._set_progress(Progress.CHECK_SERVICE)

        def _done(status: HarnessStatus) -> None:
            if not self._page_active(visit):
                return
            self._status = status
            self._status_checked_at = time.time()
            self._sync_service_bar()
            if status.install != InstallState.READY:
                if status.install == InstallState.NEEDS_KEY:
                    self._set_progress(Progress.NEED_KEY)
                else:
                    self._set_progress(Progress.NEED_INSTALL)
                self._refresh_setup_sync()
                return
            if status.service == ServiceState.PORT_CONFLICT:
                self._set_progress(Progress.NEED_REPAIR, extra=status.detail)
                self._show_web_idle(IDLE[Progress.NEED_REPAIR], block_input=False)
                return
            if status.running:
                self._set_progress(Progress.STARTED, idle=False)
                QTimer.singleShot(80, lambda v=visit: self._enter_load_ui(v))
                return
            if self._user_stopped:
                self._set_progress(Progress.STOPPED)
                self._sync_web_for_status(status)
                return
            if self._maybe_auto_start(status):
                return
            self._set_progress(Progress.NEED_START)
            self._sync_web_for_status(status)

        self.run_safe(
            lambda: read_harness_status(probe_http=True, http_timeout=0.9),
            on_success=_done,
        )

    def _enter_load_ui(self, visit: int) -> None:
        if not self._page_active(visit):
            return
        st = self._status
        if st is None or not st.running:
            self._set_progress(Progress.NEED_START)
            return
        # 已在跑且 HTTP 通：直接装载，禁止进页因「修密钥」整段重启
        if st.http_ok:
            self._set_progress(Progress.LOADING_UI)
            QTimer.singleShot(40, lambda v=visit: self._enter_present(v))
            return
        if self._maybe_heal_credentials(st):
            return
        self._set_progress(Progress.LOADING_UI)
        QTimer.singleShot(60, lambda v=visit: self._enter_present(v))

    def _enter_present(self, visit: int) -> None:
        if not self._page_active(visit):
            return
        st = self._status
        if st is None or not st.running:
            self._set_progress(Progress.NEED_START)
            return
        # 内嵌 / 浏览器偏好：启停结果态同一套文案；有 WebEngine 就装载主区
        self._set_progress(Progress.LOADING_UI, idle=True)
        self._sync_web_for_status(st)
        if not self._web_ready:
            # 无内嵌能力时与有内嵌时状态文案仍一致，仅提示可用浏览器
            self._set_progress(Progress.READY, idle=True, toast=True)
            self._show_web_idle(
                "服务已启动\n本机暂无内嵌引擎，可点「在浏览器打开」（同一地址）",
                block_input=False,
            )

    def _finish_ready_surface(self) -> None:
        """服务已启动后的统一结果态：硬停活动条，再揭开界面。"""
        self._set_action_progress_visible(False)
        self._set_progress(Progress.READY, idle=False, toast=True)
        if self._view is not None and self._web_embedded_ok:
            self._reveal_web_embed_now()
        self._sync_service_bar()

    def _reveal_web_embed_now(self) -> None:
        """立刻把 WebView 切到前台（禁止只清遮罩却仍停在占位页）。"""
        if not _qt_alive(self._view):
            return
        if not isinstance(self._host, _HarnessWebHost):
            return
        try:
            self._host.embed_view(self._view, loading=False)
            self._host.set_overlay_text(None)
        except RuntimeError:
            pass

    def _refresh_status_http_if(self, visit: int) -> None:
        if not self._page_active(visit):
            return
        self._refresh_status_http()

    def _ensure_view_after_chrome(self, visit: int | None = None) -> None:
        if not self._page_active(visit):
            return
        if self._view is None:
            self._ensure_view()
        if not self._page_active(visit):
            return
        if self._status_is_fresh() and self._status is not None and self._status.running:
            self._load_web(force=False)
        else:
            self._show_web_idle("正在连接 DeepSeek Harness…")
            QTimer.singleShot(0, lambda v=self._visit_gen: self._refresh_status_http_if(v))

    def _prewarm_view_shell(self) -> None:
        """已禁用：后台预建 WebView 与离页销毁策略冲突，且易二次进页闪退。"""
        return

    def prewarm_embed(self) -> None:
        """已禁用：见 _prewarm_view_shell。"""
        return

    def soft_leave(self) -> None:
        """切走顶栏：作废回调、停加载；View 由壳层 purge（禁止离页后台建 WebEngine）。"""
        # 注意：不清除 _user_stopped——用户停了就停着，回来也不偷偷再启
        self._auto_start_tried = False
        self._cred_heal_tried = False
        self._visit_gen += 1
        self._reveal_token += 1
        try:
            self._load_web_timer.stop()
        except Exception:
            pass
        # 打断接管/启动链，避免离页后仍 _load_web 与其它引擎页叠崩
        if self._action_busy:
            try:
                self._set_action_busy(False)
            except Exception:
                self._action_busy = False
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            if fw is not None and _qt_alive(self._view):
                if fw is self._view or self._view.isAncestorOf(fw):
                    fw.clearFocus()
        except Exception:
            pass
        try:
            if isinstance(self._host, _HarnessWebHost):
                self._host.set_overlay_text(None)
        except Exception:
            pass

    def keep_web_embed_on_leave(self) -> bool:
        """壳层已改为跨模块强制拆 View；此标志仅作文档/兼容，不再阻止 purge。"""
        return False

    def uses_webengine_embed(self) -> bool:
        """壳层：内嵌偏好或 View 仍在时视为重 Guest（触发延迟 enter + purge）。"""
        try:
            if prefer_browser() and self._view is None:
                return False
        except Exception:
            pass
        # View 在或偏好内嵌都算重，确保切走会 delay/purge
        if self._view is not None:
            return True
        try:
            return bool(prefer_embed())
        except Exception:
            return self.page_id in ("harness_agent",)

    def on_leave(self) -> None:
        # 下次进页若仍停着，允许再走一次自动启动 / 密钥修复
        self.soft_leave()
        self._park_web_embed()

    def _park_web_embed(self) -> None:
        """兼容旧名：实际改为销毁 View。"""
        self._destroy_web_embed()

    def _handoff_web_embed(self) -> None:
        """引擎↔引擎：清本页引用，共享 View 不 hide/Stop。"""
        self._view = None
        self._web_embedded_ok = False
        self._web_nav_overlay = False
        self._load_started_wired = False
        try:
            self._host.detach_view(hide=False)
        except Exception:
            try:
                self._host.clear_view_ref()
            except Exception:
                pass

    def _destroy_web_embed(self) -> None:
        """离页归还共享 WebEngine（park；离引擎域由壳 shutdown）。"""
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            if fw is not None and self._view is not None:
                if fw is self._view or self._view.isAncestorOf(fw):
                    fw.clearFocus()
        except Exception:
            pass
        self._view = None
        self._web_embedded_ok = False
        self._web_nav_overlay = False
        self._load_started_wired = False
        try:
            self._host.detach_view(hide=True)
        except Exception:
            try:
                self._host.clear_view_ref()
            except Exception:
                pass
        try:
            from services.shared_local_webengine import release

            release("harness_agent", destroy=False, park=True)
        except Exception:
            pass
        # 拆 View 不得盖掉启停结果态（停了还写「正在进入」会气死人）
        if self._user_stopped:
            self._set_progress(Progress.STOPPED, toast=False, idle=True)
        elif self._status is not None and not self._status.running:
            self._set_progress(Progress.NEED_START, toast=False, idle=True)
        elif self._progress in (Progress.STOPPED, Progress.NEED_START, Progress.NEED_INSTALL, Progress.NEED_KEY):
            self._set_progress(self._progress, toast=False, idle=True)
        else:
            self._show_web_idle(IDLE[Progress.NEED_START], block_input=False)

    def _should_keep_embed_on_enter(self) -> bool:
        if not self._web_embedded_ok or not _qt_alive(self._view):
            if self._view is not None and not _qt_alive(self._view):
                self._view = None
            return False
        try:
            current = (self._view.url().toString() or "").rstrip("/")
        except RuntimeError:
            self._view = None
            return False
        target = web_url().rstrip("/")
        return bool(current.startswith(target))

    def apply_pending_feed_from_stash(self) -> None:
        self._apply_pending_feed()

    def _status_is_fresh(self) -> bool:
        if self._status is None:
            return False
        return (time.time() - self._status_checked_at) <= self._STATUS_STALE_S

    def _status_web_equivalent(self, prev: HarnessStatus, cur: HarnessStatus) -> bool:
        return (
            prev.running == cur.running
            and prev.install == cur.install
            and prev.service == cur.service
            and (prev.url or "").rstrip("/") == (cur.url or "").rstrip("/")
        )

    def _maybe_auto_start(self, status: HarnessStatus) -> bool:
        """进页自动启动：仅当用户未主动停止，且设置勾选 auto_start。"""
        if self._user_stopped:
            return False
        if self._action_busy or self._auto_start_tried:
            return False
        if status.install != InstallState.READY or status.running:
            return False
        if status.service == ServiceState.PORT_CONFLICT:
            return False
        cfg = load_harness_config()
        if not bool(cfg.get("auto_start", True)):
            return False
        self._auto_start_tried = True
        self._set_progress(Progress.STARTING, toast=True)
        self._run_sidecar_start(busy_label="正在启动服务…")
        return True

    def _maybe_heal_credentials(self, status: HarnessStatus) -> bool:
        """运行中且未托管时才可接管；停止态绝不因密钥再拉起。"""
        if self._user_stopped:
            return False
        if self._action_busy or self._cred_heal_tried:
            return False
        if status.install != InstallState.READY:
            return False
        if not status.running:
            return False
        try:
            from services.harness_credentials import needs_credential_takeover
        except Exception:
            return False
        need, reason = needs_credential_takeover(
            running=bool(status.running), owned=bool(status.owned)
        )
        if not need:
            return False
        self._cred_heal_tried = True
        self._set_progress(Progress.RESTARTING, extra="正在同步密钥…")
        self._set_action_busy(True, "正在重新启动…", phase=BusyPhase.RESTARTING)
        QTimer.singleShot(0, self._takeover_restart_on_main)
        return True

    def _on_heal_credentials(self) -> None:
        """兼容旧入口：与「重启服务」同路径。"""
        self._on_restart()

    def _refresh_setup_sync(self) -> None:
        state, msg = probe_page_state(check_running=False)
        if state == self._setup_state:
            if state not in (HarnessPageState.NOT_INSTALLED, HarnessPageState.NEEDS_KEY):
                return
        self._setup_state = state
        if state in (HarnessPageState.NOT_INSTALLED, HarnessPageState.NEEDS_KEY):
            self._body_stack.setCurrentIndex(0)
            self._setup_gate.show_state(state, msg)
            return
        self._show_workspace()

    def _show_workspace(self) -> None:
        self._body_stack.setCurrentIndex(1)

    def _apply_status(self, status: HarnessStatus) -> None:
        if not self._page_active():
            # 离页后的异步探测只缓存状态，不碰 WebEngine UI
            self._status = status
            self._status_checked_at = time.time()
            return
        prev = self._status
        self._status = status
        self._status_checked_at = time.time()
        # 操作进行中：保留忙碌文案，避免仍显示「运行中/冲突」造成按钮与状态错位
        if self._action_busy:
            return
        self._paint_status_hint()
        self._sync_service_bar()
        if not self._user_stopped:
            if self._maybe_auto_start(status):
                return
            if self._maybe_heal_credentials(status):
                return
        if prev is not None and self._status_web_equivalent(prev, status):
            if self._web_embedded_ok:
                return
        self._sync_web_for_status(status)

    def _sync_service_bar(self) -> None:
        st = self._status
        if self._action_busy or st is None:
            return
        self._apply_chrome(phase=BusyPhase.IDLE)

    def _sync_web_for_status(self, status: HarnessStatus) -> None:
        """启停结果态与表面偏好无关：能内嵌就装主区；浏览器只是另开同一地址。"""
        if status.install != InstallState.READY:
            return
        if status.running:
            if not self._web_ready:
                self._set_progress(Progress.READY, idle=True, toast=False)
                self._show_web_idle(
                    "服务已启动\n本机暂无内嵌引擎，可点「在浏览器打开」（同一地址）",
                    block_input=False,
                )
                return
            if self._view is not None:
                current = (self._view.url().toString() or "").rstrip("/")
                target = status.url.rstrip("/")
                if self._web_embedded_ok and current.startswith(target):
                    self._show_web_embed()
                    self._set_progress(Progress.READY, idle=False, toast=False)
                    return
            self._set_progress(Progress.LOADING_UI, idle=True, toast=False)
            self._schedule_load_web(delay_ms=120)
        else:
            interim_busy = status.port_busy and not status.http_ok
            if not interim_busy:
                self._web_embedded_ok = False
            if status.service == ServiceState.PORT_CONFLICT:
                self._set_progress(Progress.NEED_REPAIR, extra=sanitize_user_text(status.detail or ""))
            elif interim_busy and self._should_keep_embed_on_enter():
                self._show_web_embed()
            else:
                step = Progress.STOPPED if self._user_stopped else Progress.NEED_START
                self._set_progress(step, toast=False)

    def _apply_browser_surface(self, status: HarnessStatus, *, open_browser: bool = False) -> None:
        """仅「在浏览器打开」：另开窗口；主区仍保持与内嵌相同的就绪态文案。"""
        if open_browser:
            open_in_system_browser()
            self._browser_surface_opened = True
            self.report_status("已在系统浏览器打开（与本页同一服务）", level=StatusLevel.SUCCESS)
        # 不再清空主区、不再切 READY_BROWSER 分叉文案
        if status.running:
            self._set_progress(Progress.READY, idle=False, toast=False)

    def _set_action_busy(
        self,
        busy: bool,
        label: str = "",
        *,
        phase: BusyPhase | None = None,
    ) -> None:
        if busy:
            self._action_busy = True
            self._busy_label = (label or "").strip()
            self._busy_phase = phase or infer_busy_phase(self._busy_label)
            self._apply_chrome(phase=self._busy_phase, busy_label=self._busy_label)
            self._set_action_progress_visible(True, immediate=True)
        else:
            self._action_busy = False
            self._busy_phase = BusyPhase.IDLE
            self._busy_label = ""
            self._set_action_progress_visible(False)
            self._btn_start.setText("启动服务")
            self._btn_stop.setText("停止服务")
            # 空闲标题留给结果态 _set_progress / chrome，勿硬刷成产品名造成跳动
            self._sync_service_bar()
            if self._status is not None:
                self._paint_status_hint()

    def _show_web_idle(self, text: str, *, block_input: bool | None = None) -> None:
        if isinstance(self._host, _HarnessWebHost):
            # 已有可见网页时提示不得挡点击（插件开关/设置弹层）
            live = False
            if _qt_alive(self._view) and self._web_embedded_ok:
                try:
                    live = bool(self._view.isVisible())
                except RuntimeError:
                    self._view = None
                    live = False
            elif self._view is not None and not _qt_alive(self._view):
                self._view = None
            # 就绪后禁止任何遮罩：即便 WA_TransparentForMouseEvents，
            # 叠在 QWebEngineView 上仍会吞掉 Chromium 命中（设置里点「深色」无反应）
            if live and self._web_embedded_ok and block_input is not True:
                try:
                    self._host.set_overlay_text(None)
                except RuntimeError:
                    pass
                if (text or "").strip():
                    self.report_status(text, level=StatusLevel.INFO)
                return
            block = (not live) if block_input is None else bool(block_input)
            try:
                if not block:
                    # 不挡点击：占位文案即可，切勿抬半透明/不透明遮罩
                    if (text or "").strip():
                        self._host.set_placeholder(text)
                    self._host.set_overlay_text(None)
                else:
                    self._host.set_overlay_text(text, block_input=True)
            except RuntimeError:
                pass

    def _show_web_embed(self) -> None:
        # 晚一帧再揭罩，等 Chromium 首帧；揭罩必须切到 View，不能只清 overlay
        self._reveal_token += 1
        token = self._reveal_token
        visit = self._visit_gen
        QTimer.singleShot(80, lambda: self._reveal_web_embed(token, visit))

    def _reveal_web_embed(self, token: int | None = None, visit: int | None = None) -> None:
        if token is not None and token != self._reveal_token:
            return
        if not self._page_active(visit):
            return
        self._reveal_web_embed_now()

    def _refresh_status_async(self) -> None:
        if self._action_busy:
            QTimer.singleShot(400, self._refresh_status_async)
            return
        if (
            self._status_is_fresh()
            and self._status is not None
            and self._status.running
            and self._web_embedded_ok
        ):
            return
        if self._should_keep_embed_on_enter():
            self._paint_status_hint(install="已安装", service="运行中 · 正在确认…")
        QTimer.singleShot(0, self._refresh_status_http)

    def _refresh_status_http(self) -> None:
        if self._action_busy:
            return
        # 仅当「已在跑且刚探过」才跳过；停着时必须再探，才能触发 auto_start
        if (
            self._status_is_fresh()
            and self._status is not None
            and self._status.running
        ):
            if not self._web_embedded_ok and prefer_embed():
                self._sync_web_for_status(self._status)
            return

        def _on_ok(status: HarnessStatus) -> None:
            try:
                self._apply_status(status)
            except Exception as exc:
                self.handle_error(exc, title="Harness 状态探测")

        self.run_safe(
            lambda: read_harness_status(probe_http=True, http_timeout=0.6),
            on_success=_on_ok,
        )

    def _ensure_view(self) -> None:
        if not self._page_active():
            return
        if not self._web_ready:
            return
        if _qt_alive(self._view):
            # 已租到共享 View：就绪态禁止再抬遮罩（使用中闪烁主因）
            try:
                self._host.embed_view(self._view, loading=not self._web_embedded_ok)
            except Exception:
                pass
            return
        from services.shared_local_webengine import acquire
        from services.webengine_host import ToaWebEnginePage
        from services.webengine_prewarm import release_prewarm_hold

        # 禁止预热 View 与真引擎并存（首进抖窗主因）
        try:
            release_prewarm_hold()
        except Exception:
            pass

        self._show_web_idle("正在准备 DeepSeek Harness…")
        url = web_url()
        view = acquire(
            "harness_agent",
            url,
            host_ref=self,
            on_load_finished=self._on_web_loaded,
            event_filter=self._f11_filter,
        )
        if view is None:
            self._show_web_idle("无法创建共享 WebEngine")
            return
        # 只改 accept_nav，禁止反复 setPage（setPage=整页白闪）
        try:
            page = view.page()
            accept = _make_harness_accept_nav(base_url=url)

            if isinstance(page, ToaWebEnginePage):
                page.set_accept_nav(accept)
            else:
                view.setPage(_make_harness_web_page(view.page().profile(), view, base_url=url))
        except Exception:
            pass
        self._view = view
        # 仅在已接线时 disconnect，避免 Qt RuntimeWarning 刷屏
        if getattr(self, "_load_started_wired", False):
            try:
                view.loadStarted.disconnect(self._on_web_load_started)
            except (TypeError, RuntimeError):
                pass
            self._load_started_wired = False
        try:
            view.loadStarted.connect(self._on_web_load_started)
            self._load_started_wired = True
        except Exception:
            self._load_started_wired = False
        already_ok = False
        painted = ""
        try:
            painted = (view.url().toString() or "").rstrip("/")
            already_ok = bool(painted.startswith(url.rstrip("/")))
        except Exception:
            already_ok = False
        # 画面仍是其它引擎时必须遮罩/占位，禁止 Host=Harness 内容=Draw.io
        self._host.embed_view(self._view, loading=not already_ok)
        if already_ok:
            self._web_embedded_ok = True
            try:
                from services.webengine_host import ToaWebEnginePage

                page = view.page()
                if isinstance(page, ToaWebEnginePage):
                    page.end_forced_navigation()
            except Exception:
                pass
            self._show_web_embed()
        else:
            self._web_embedded_ok = False
            self._show_web_idle("正在连接 DeepSeek Harness…")
        self._apply_web_zoom()

    def _apply_web_zoom(self) -> None:
        if self._view is None:
            return
        cfg = load_harness_config()
        try:
            zoom = float(cfg.get("web_zoom") or 1.0)
        except (TypeError, ValueError):
            zoom = 1.0
        self._view.setZoomFactor(max(0.5, min(2.0, zoom)))

    def _schedule_load_web(self, *, force: bool = False, delay_ms: int = 180) -> None:
        st = self._status
        if not self._web_ready or st is None or not st.running:
            return
        if force:
            self._load_web_force = True
        delay = 0 if self._view is not None else 80
        self._load_web_timer.start(max(int(delay_ms), delay))

    def _do_scheduled_load_web(self) -> None:
        if not self._page_active():
            self._load_web_force = False
            return
        force = self._load_web_force
        self._load_web_force = False
        self._load_web(force=force)

    def _focus_web_view(self) -> None:
        if not self._page_active() or self._view is None:
            return
        self._view.setFocus(Qt.FocusReason.OtherFocusReason)

    def _load_web(self, *, force: bool = False) -> None:
        if not self._page_active():
            return
        st = self._status
        if not self._web_ready or st is None or not st.running:
            return
        # 表面偏好不阻断主区装载；浏览器只是另开同一地址
        self._ensure_view()
        if self._view is None or not self._page_active():
            return
        url = web_url()
        current = (self._view.url().toString() or "").rstrip("/")
        target = url.rstrip("/")
        if not force and current.startswith(target) and self._web_embedded_ok:
            self._show_web_embed()
            return
        self._begin_home_navigation(url, force=force)

    def _begin_home_navigation(self, url: str | None = None, *, force: bool = True) -> None:
        """强制回到 Harness 主 URL 并装载（深链/遮罩卡住时的主路径）。"""
        if not _qt_alive(self._view):
            self._ensure_view()
        if not _qt_alive(self._view):
            return
        home = (url or web_url()).rstrip("/")
        current = (self._view.url().toString() or "").rstrip("/")
        self._web_nav_overlay = True
        self._web_embedded_ok = False
        self._show_web_idle(IDLE[Progress.LOADING_UI], block_input=True)
        self._set_action_progress_visible(False)
        self._arm_loading_watchdog()
        try:
            from services.webengine_host import ToaWebEnginePage

            page = self._view.page()
            if isinstance(page, ToaWebEnginePage):
                page.begin_forced_navigation()
        except Exception:
            pass
        # 深链页必须 setUrl 回主页；仅同 URL 才 reload
        if force and current.rstrip("/") == home:
            self._view.reload()
            return
        self._view.setUrl(QUrl(home if home.endswith("/") else home + "/"))

    def _arm_loading_watchdog(self) -> None:
        """装载遮罩超时：同域则揭罩，异域则再拉主页——禁止永久白屏。"""
        self._load_watch_token += 1
        token = self._load_watch_token
        visit = self._visit_gen
        QTimer.singleShot(8000, lambda: self._loading_watchdog(token, visit))

    def _loading_watchdog(self, token: int, visit: int) -> None:
        if token != self._load_watch_token or not self._page_active(visit):
            return
        if self._web_embedded_ok:
            return
        if not _qt_alive(self._view):
            self._set_progress(Progress.FAILED, extra="界面未装载，请再点「刷新」或「一键修复」")
            return
        home = web_url().rstrip("/")
        try:
            current = (self._view.url().toString() or "").rstrip("/")
        except RuntimeError:
            current = ""
        # 仍停在装载遮罩：同域揭开当前页；否则强制回主页
        same_home = bool(current) and (
            current == home
            or current.startswith(home + "/")
            or current.startswith(home + "#")
            or current.startswith(home + "?")
        )
        if same_home:
            self._web_nav_overlay = False
            self._web_embedded_ok = True
            self._set_action_progress_visible(False)
            self._reveal_web_embed_now()
            self._set_progress(Progress.READY, idle=False, toast=False)
            self.report_status(
                "装载较慢，已显示当前页；可点「刷新」回到主界面",
                level=StatusLevel.INFO,
            )
            return
        self.report_status("装载超时，正在回到主界面…", level=StatusLevel.WARNING)
        self._begin_home_navigation(home, force=True)

    def _on_go_home(self) -> None:
        """更多 → 回到主界面。"""
        st = self._status
        if st is None or not st.running:
            self.report_status("请先启动服务", level=StatusLevel.WARNING)
            return
        self._status_label.setText("正在回到主界面…")
        self._service_line.setText("状态：正在回到主界面…")
        self._navigate_home_now()

    def _navigate_home_now(self) -> None:
        self._set_progress(Progress.LOADING_UI, idle=True, toast=False)
        self._begin_home_navigation(force=True)
        self.report_status("正在回到 Harness 主界面…", level=StatusLevel.INFO)

    def _on_refresh_clicked(self) -> None:
        """工具栏刷新：回到主界面并重新装载（勿只 reload 深链）。"""
        self._service_line.setText("状态：正在刷新…")
        self._status_label.setText("正在刷新…")
        self._set_action_progress_visible(True)
        self._btn_refresh.setText("刷新中…")
        self._btn_refresh.setEnabled(False)
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self) -> None:
        try:
            self._reload_web()
        finally:
            try:
                self._btn_refresh.setText("刷新")
                self._btn_refresh.setEnabled(True)
                if not self._action_busy:
                    self._set_action_progress_visible(False)
                    if self._status is not None:
                        self._paint_status_hint()
            except RuntimeError:
                pass

    def _reload_web(self) -> None:
        st = self._status
        if st is None:
            self.report_status("正在重新探测…", level=StatusLevel.INFO)
            self._refresh_status_http()
            return
        if not st.running:
            self.report_status("正在重新探测服务状态…", level=StatusLevel.INFO)
            self._status_checked_at = 0.0
            self._refresh_status_http()
            return
        # 服务在跑：一律回主 URL（解决深链卡死 / 遮罩揭不开）
        self._navigate_home_now()

    def _on_web_load_started(self) -> None:
        # 仅主动导航遮罩期抬提示；就绪后 SPA 内跳转禁止再挡画面 / 再开活动条
        if self._web_embedded_ok and not self._web_nav_overlay:
            return
        if self._web_nav_overlay or not self._web_embedded_ok:
            self._show_web_idle(IDLE[Progress.LOADING_UI], block_input=True)
            self._set_action_progress_visible(False)
            self.report_status(TOAST[Progress.LOADING_UI], level=StatusLevel.INFO)

    def _on_web_loaded(self, ok: bool) -> None:
        self._web_nav_overlay = False
        self._load_watch_token += 1  # 作废超时揭罩
        try:
            from services.webengine_host import ToaWebEnginePage

            page = self._view.page() if _qt_alive(self._view) else None
            if isinstance(page, ToaWebEnginePage):
                page.end_forced_navigation()
        except Exception:
            pass
        if not self._page_active():
            self._web_embedded_ok = bool(ok)
            return
        self._apply_web_zoom()
        if self._view is not None:
            self._view.page().runJavaScript(
                "window.addEventListener('keydown',function(e){"
                "if(e.key==='F11'){e.preventDefault();e.stopImmediatePropagation();}},true);"
            )
        if ok:
            self._web_embedded_ok = True
            # 装载完成：先硬停活动条，再揭开 Web（遮罩→内容，不半露半闪）
            self._set_action_progress_visible(False)
            self._reveal_web_embed_now()
            QTimer.singleShot(120, self._focus_web_view)
            self._set_progress(Progress.READY, idle=False, toast=True)
            if prefer_browser() and not self._browser_surface_opened:
                QTimer.singleShot(200, self._maybe_auto_open_browser)
            if self._pending_prepare_after_reload:
                self._pending_prepare_after_reload = False
                QTimer.singleShot(700, self._run_prepare_session)
            return
        # loadFinished=false：同域仍揭罩；异域再拉主页——禁止永久遮罩
        self._set_action_progress_visible(False)
        home = web_url().rstrip("/")
        current = ""
        try:
            if _qt_alive(self._view):
                current = (self._view.url().toString() or "").rstrip("/")
        except RuntimeError:
            pass
        if current.startswith(home) or current.startswith(home + "/") or current.startswith(home + "#"):
            self._web_embedded_ok = True
            self._reveal_web_embed_now()
            self._set_progress(Progress.READY, idle=False, toast=False)
            self.report_status("页面未完整响应，已显示当前内容；可再点「刷新」回主界面", level=StatusLevel.WARNING)
            if self._pending_prepare_after_reload:
                self._pending_prepare_after_reload = False
            return
        self._web_embedded_ok = False
        # 异域/空白：再拉一次主页，避免永久遮罩
        self.report_status("页面未响应，正在回到主界面…", level=StatusLevel.WARNING)
        QTimer.singleShot(200, lambda: self._begin_home_navigation(force=True) if self._page_active() else None)
        if self._pending_prepare_after_reload:
            self._pending_prepare_after_reload = False
        return

    def _run_bg(self, fn, *, busy_label: str, on_ok, on_err=None, phase: BusyPhase | None = None) -> None:
        if self._action_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return

        def _safe_fn():
            """把异常收成 (False, msg)，避免 run_safe 弹框后不清 busy。"""
            try:
                return fn()
            except OSError as exc:
                from services.harness_plugins import _friendly_os_error

                return False, _friendly_os_error(exc)
            except Exception as exc:
                return False, str(exc) or exc.__class__.__name__

        def _wrapped_ok(payload) -> None:
            chained = False
            try:
                if payload is None:
                    if on_err is not None:
                        on_err()
                    return
                # on_ok 返回 True 表示已转入下一忙碌操作（如修复→重启），勿清 busy
                chained = bool(on_ok(payload))
            finally:
                if not chained:
                    self._set_action_busy(False)

        self._set_action_busy(
            True,
            busy_label,
            phase=phase or infer_busy_phase(busy_label),
        )
        self._show_web_idle(busy_label, block_input=True)
        self.run_safe(_safe_fn, on_success=_wrapped_ok)

    def _after_sidecar_started(self, ok: bool, msg: str) -> None:
        if not self._page_active():
            self._set_action_busy(False)
            return
        self._apply_status(read_harness_status(probe_http=True, http_timeout=0.8))
        if not ok:
            self._present_start_failed(msg)
            return
        self._plugin_heal_tried = False
        self._set_progress(Progress.STARTED)
        QTimer.singleShot(80, self._after_started_load_ui)
        try:
            from services.harness_profile_versions import maybe_snapshot_after_healthy

            snap_ok, snap_msg = maybe_snapshot_after_healthy()
            if snap_ok:
                logger = __import__("logging").getLogger("TOA3.harness_agent")
                logger.info("%s", snap_msg)
        except Exception:
            pass

    def _after_started_load_ui(self) -> None:
        if not self._page_active():
            return
        st = self._status
        if st is None or not st.running:
            self._set_progress(Progress.NEED_START)
            return
        self._set_progress(Progress.LOADING_UI, idle=True)
        self._set_action_progress_visible(False)
        self._sync_web_for_status(st)
        # 装载结束后由 loadFinished / finish_ready 统一 READY；不因浏览器偏好分叉
        if not self._web_ready:
            QTimer.singleShot(80, self._finish_ready_surface)

    def _maybe_auto_open_browser(self) -> None:
        """偏好 browser 时另开系统窗；不改变主区启停态。"""
        if not prefer_browser() or self._browser_surface_opened:
            return
        st = self._status
        if st is None or not st.running:
            return
        open_in_system_browser()
        self._browser_surface_opened = True
        self.report_status("已另开系统浏览器（与本页同一服务）", level=StatusLevel.INFO)

    def _maybe_auto_heal_plugins(self, msg: str) -> None:
        """启动失败且日志像插件杀手时：自动剔除 denylist 并再启一次。"""
        if self._plugin_heal_tried:
            return
        text = msg or ""
        try:
            path = sidecar_log_path()
            if path.is_file():
                text = f"{text}\n{path.read_text(encoding='utf-8', errors='replace')[-1200:]}"
        except OSError:
            pass
        if not log_suggests_plugin_boot_failure(text):
            return
        self._plugin_heal_tried = True
        self.report_status(
            "检测到插件导致启动失败，正在自动剔除不兼容插件并重启…",
            level=StatusLevel.WARNING,
        )

        def _job() -> tuple[bool, str]:
            from services.harness_plugins import strip_boot_killer_plugins

            return strip_boot_killer_plugins()

        def _after(result: tuple[bool, str]) -> None:
            ok, text2 = result
            self.report_status(
                text2,
                level=StatusLevel.SUCCESS if ok else StatusLevel.WARNING,
            )
            if ok:
                self._on_restart(confirm=False)
                return True
            return False

        self._run_bg(
            _job,
            busy_label="正在剔除不兼容插件…",
            on_ok=_after,
            phase=BusyPhase.HEALING,
        )

    def _run_sidecar_start(self, *, busy_label: str, allow_busy: bool = False) -> None:
        if not self._page_active():
            return
        if self._action_busy and not allow_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return
        self._set_progress(Progress.STARTING)
        if not self._action_busy:
            self._set_action_busy(True, "正在启动服务…", phase=BusyPhase.STARTING)
        elif busy_label:
            self._busy_label = "正在启动服务…"
            self._busy_phase = BusyPhase.STARTING
            self._apply_chrome(phase=BusyPhase.STARTING, busy_label="正在启动服务…")
        self.run_safe(prepare_sidecar_start, on_success=self._on_prepare_done)

    def _on_prepare_done(self, result: tuple[bool, str, bool]) -> None:
        if not self._page_active():
            self._set_action_busy(False)
            return
        ok, msg, already = result
        if not ok:
            self._present_start_failed(msg)
            return
        if already:
            st = read_harness_status(probe_http=True, http_timeout=0.6)
            try:
                from services.harness_credentials import needs_credential_takeover

                need, _reason = needs_credential_takeover(
                    running=bool(st.running), owned=bool(st.owned)
                )
            except Exception:
                need = bool(st.running and not st.owned)
            if need and not self._user_stopped:
                self._set_progress(Progress.RESTARTING, extra="正在同步密钥…")
                QTimer.singleShot(0, self._takeover_restart_on_main)
                return
            self._set_action_busy(False)
            self._after_sidecar_started(True, "服务已启动")
            return
        QTimer.singleShot(0, self._spawn_sidecar_on_main)

    def _spawn_sidecar_on_main(self) -> None:
        if not self._page_active():
            self._set_action_busy(False)
            return
        ok, msg = spawn_sidecar_process()
        if not ok:
            self._present_start_failed(msg)
            return
        self._start_deadline = time.monotonic() + 25.0
        self._set_progress(Progress.STARTING, toast=False)
        QTimer.singleShot(350, self._poll_sidecar_start)

    def _poll_sidecar_start(self) -> None:
        if not self._page_active():
            self._set_action_busy(False)
            return
        if time.monotonic() > self._start_deadline:
            try:
                tail = sidecar_log_path().read_text(encoding="utf-8", errors="replace")[-800:]
            except OSError:
                tail = ""
            self._present_start_failed("启动超时，请一键修复或打开启动日志")
            self._maybe_auto_heal_plugins(tail)
            return
        phase, msg = sidecar_start_progress()
        if phase == "ready":
            self._set_action_busy(False)
            self._after_sidecar_started(True, msg)
            return
        if phase == "failed":
            self._present_start_failed(msg)
            return
        self._set_progress(Progress.STARTING, toast=False)
        QTimer.singleShot(350, self._poll_sidecar_start)

    def _on_start(self) -> None:
        if self._action_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return
        self._user_stopped = False
        self._begin_click_feedback(
            "正在启动服务…",
            phase=BusyPhase.STARTING,
            progress=Progress.STARTING,
        )
        QTimer.singleShot(0, self._do_start)

    def _do_start(self) -> None:
        if not self._page_active():
            self._set_action_busy(False)
            return
        self._run_sidecar_start(busy_label="正在启动服务…", allow_busy=True)

    def _on_stop(self) -> None:
        if self._action_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return
        st = self._status
        force = False
        if st is not None and st.running and not st.owned:
            if not ask_confirm(
                self,
                "将结束本机正在运行的 Harness 服务。是否继续？",
                title="停止服务",
            ):
                return
            force = True

        self._user_stopped = True
        self._auto_start_tried = True
        self._cred_heal_tried = True
        self._begin_click_feedback(
            "正在停止服务…",
            phase=BusyPhase.STOPPING,
            progress=Progress.STOPPING,
        )
        QTimer.singleShot(0, lambda: self._stop_sidecar_on_main(force))

    def _stop_sidecar_on_main(self, force: bool) -> None:
        ok, msg = stop(force=force)
        self._web_embedded_ok = False
        self._browser_surface_opened = False
        if self._view is not None:
            QTimer.singleShot(200, self._destroy_web_embed)
        self._set_action_busy(False)
        self._apply_status(read_harness_status(probe_http=True, http_timeout=0.8))
        if ok:
            self._set_progress(Progress.STOPPED)
        else:
            self._set_progress(Progress.FAILED, extra=sanitize_user_text(msg), level=StatusLevel.WARNING)

    def _on_takeover_restart(self) -> None:
        """兼容旧入口：与「重启服务」同路径。"""
        self._on_restart()

    def _takeover_restart_on_main(self) -> None:
        """主线程：先强杀端口占用，等空闲后再 spawn（避免假成功复用外部）。"""
        if not self._page_active():
            self._set_action_busy(False)
            return
        try:
            from services.harness_model_defaults import ensure_official_default_model

            changed, msg = ensure_official_default_model()
            if changed:
                self.report_status(msg, level=StatusLevel.INFO)
        except Exception:
            pass
        from services.harness_config import load_harness_config
        from services.harness_sidecar import _find_listener_pids, _kill_pids, _port_open

        ok, msg = stop(force=True)
        if not ok:
            # 仍尝试继续清端口
            self.report_status(msg, level=StatusLevel.WARNING)
        port = int(load_harness_config().get("web_port") or 3081)
        self._heal_port = port
        self._heal_deadline = time.monotonic() + 12.0
        self._set_progress(Progress.RESTARTING, extra="正在结束旧进程…", toast=False)
        self._show_web_idle(IDLE[Progress.RESTARTING], block_input=True)
        QTimer.singleShot(150, self._heal_wait_port_then_spawn)

    def _heal_wait_port_then_spawn(self) -> None:
        if not self._page_active():
            self._set_action_busy(False)
            return
        from services.harness_sidecar import _find_listener_pids, _kill_pids, _port_open

        port = int(getattr(self, "_heal_port", 3081) or 3081)
        still = _port_open(port) or is_running(timeout=0.35)
        if still:
            if time.monotonic() > float(getattr(self, "_heal_deadline", 0) or 0):
                _kill_pids(_find_listener_pids(port))
                if _port_open(port) or is_running(timeout=0.35):
                    self._set_action_busy(False)
                    self._set_progress(
                        Progress.FAILED,
                        extra=f"端口 {port} 仍被占用，请结束后再点「重启服务」",
                    )
                    return
            else:
                QTimer.singleShot(200, self._heal_wait_port_then_spawn)
                return
        ok, msg = spawn_sidecar_process()
        if not ok:
            self._set_action_busy(False)
            self._set_progress(Progress.FAILED, extra=sanitize_user_text(msg))
            return
        self._start_deadline = time.monotonic() + 25.0
        self._set_progress(Progress.STARTING, toast=False)
        QTimer.singleShot(350, self._poll_sidecar_start)

    def _on_restart(self, *, confirm: bool = True) -> None:
        if confirm:
            if self._action_busy:
                self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
                return
            if not ask_confirm(
                self,
                "将结束当前服务并用本页保存的密钥重新启动。是否继续？",
                title="重新启动",
            ):
                return
        self._user_stopped = False
        self._begin_click_feedback(
            "正在重新启动…",
            phase=BusyPhase.RESTARTING,
            progress=Progress.RESTARTING,
        )
        QTimer.singleShot(0, self._takeover_restart_on_main)

    def _restart_sidecar_on_main(self) -> None:
        """兼容旧调用：一律走强制干净重启。"""
        self._takeover_restart_on_main()

    def _open_external(self) -> None:
        if self._action_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return
        st = self._status
        if st is None or not st.running:
            self.report_status("请先启动服务，再在浏览器打开", level=StatusLevel.WARNING)
            return
        self._btn_open_browser.setText("打开中…")
        self._btn_open_browser.setEnabled(False)
        self._service_line.setText("状态：正在打开浏览器…")
        self._set_action_progress_visible(True)
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass
        try:
            open_in_system_browser()
            self._browser_surface_opened = True
            self.report_status("已在浏览器打开", level=StatusLevel.SUCCESS)
            # 保持与内嵌一致的「服务已启动」口径，不改主区
            self._set_progress(Progress.READY, idle=False, toast=False)
        finally:
            self._btn_open_browser.setText("在浏览器打开")
            self._btn_open_browser.setEnabled(True)
            if not self._action_busy:
                self._set_action_progress_visible(False)

    def _switch_to_browser_surface(self) -> None:
        set_surface_mode("browser")
        self._more_menu_signature = None
        self._rebuild_more_menu()
        self.report_status(
            "已设为偏好另开系统浏览器 · 启停与主区装载不变",
            level=StatusLevel.INFO,
        )
        st = self._status
        if st is not None and st.running:
            # 主区继续装载；可选立刻另开一窗
            self._sync_web_for_status(st)
            self._maybe_auto_open_browser()

    def _switch_to_embed_surface(self) -> None:
        set_surface_mode("embed")
        self._browser_surface_opened = False
        self._more_menu_signature = None
        self._rebuild_more_menu()
        self.report_status("已设为以套件内嵌为主 · 启停口径不变", level=StatusLevel.INFO)
        st = self._status
        if st is not None and st.running:
            self._show_web_idle("正在装载界面…", block_input=True)
            self._schedule_load_web(force=True, delay_ms=0)
        else:
            self._set_progress(Progress.NEED_START if not self._user_stopped else Progress.STOPPED)

    def _open_settings(self) -> None:
        w = self.window()
        if w is not None and hasattr(w, "navigate"):
            w.navigate("system_settings")
            page = getattr(w, "_pages", {}).get("system_settings")
            if page is not None and hasattr(page, "open_tab"):
                from modules.system_settings.settings_page import TAB_INTEGRATIONS

                page.open_tab(TAB_INTEGRATIONS)
            self.report_status("系统设置 · 能力接入 → DeepSeek Harness", level=StatusLevel.INFO)
        else:
            self.report_status("请从侧栏进入「系统设置」", level=StatusLevel.WARNING)

    def _on_one_click_install(self, flavor: str = "") -> None:
        from services.harness_prefab import FLAVOR_PREFAB, make_cancel_event, normalize_flavor

        if self._install_thread is not None:
            self.report_status("安装仍在进行", level=StatusLevel.WARNING)
            return
        f = normalize_flavor(flavor or FLAVOR_PREFAB)
        self._install_flavor = f
        cancel_ev, _ = make_cancel_event()
        self._install_cancel = cancel_ev
        self._setup_gate.set_installing(True, flavor=f)
        self.report_status("正在安装运行环境…", level=StatusLevel.INFO)

        thread = QThread(self)
        worker = _HarnessInstallWorker(f, cancel_ev)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_install_progress)
        worker.finished.connect(self._on_install_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._install_thread = thread
        self._install_worker = worker
        thread.start()

    def _on_install_progress(self, msg: str, pct: int, stage: str = "") -> None:
        self._setup_gate.set_install_progress(msg, pct, stage)

    def _on_cancel_install(self) -> None:
        if self._install_cancel is not None:
            self._install_cancel.set()
            self._setup_gate.set_install_progress("正在取消…", self._setup_gate._progress.value(), "cancel")
            self.report_status("正在取消安装…", level=StatusLevel.INFO)

    def _on_install_finished(self, ok: bool, text: str, flavor: str) -> None:
        self._install_thread = None
        self._install_worker = None
        self._install_cancel = None
        self._setup_gate.set_installing(False)
        if not ok:
            from services.harness_setup import NEED_NODE_PREFIX

            detail = str(text or "")
            if detail.startswith(NEED_NODE_PREFIX):
                self._setup_gate.mark_need_node(detail[len(NEED_NODE_PREFIX) :].strip())
            else:
                self._setup_gate.show_install_failed(detail, flavor=flavor)
                if detail and "已取消" not in detail:
                    show_warning(self, detail)
            self._deferred_enter()
            return
        self.report_status(text, level=StatusLevel.SUCCESS)
        self._auto_start_tried = False
        self._cred_heal_tried = False
        self._deferred_enter()

    def _after_key_saved(self) -> None:
        # ② 保存密钥后强制走 ③ 自动启动
        self._auto_start_tried = False
        self._cred_heal_tried = False
        self._deferred_enter()

    def _deferred_enter(self) -> None:
        self.on_enter()

    def _apply_pending_feed(self) -> None:
        feed = peek_feed()
        text = str(feed.get("text") or "").strip()
        if not text:
            self._feed_strip.hide()
            return
        title = str(feed.get("title") or feed.get("source") or "办公链")
        preview = text if len(text) <= 120 else text[:120] + "…"
        auto = str(feed.get("auto_prepare") or "") == "1"
        wt = str(feed.get("workspace_title") or "").strip()
        wp = str(feed.get("workspace_path") or "").strip()
        self._feed_strip.set_preview(
            title,
            preview,
            auto_prepare=auto,
            workspace_path=wp,
            workspace_title=wt,
        )
        self._feed_strip.show()
        self._feed_strip.raise_()
        if auto:
            # Host 侧栏经 SSE 稍晚出现，略延后定位
            delay = 900 if str(feed.get("session_id") or "").strip() else 400
            QTimer.singleShot(delay, self._auto_prepare_extension_feed)
        else:
            self._try_select_feed_workspace(feed)

    def _auto_prepare_extension_feed(self) -> None:
        feed = peek_feed()
        if str(feed.get("auto_prepare") or "") != "1":
            return
        text = format_feed_message(feed) if feed.get("text") else ""
        if not text.strip() and str(feed.get("already_prompted") or "") != "1":
            return
        if not self._web_embedded_ok or self._view is None:
            QTimer.singleShot(800, self._auto_prepare_extension_feed)
            return

        sid = str(feed.get("session_id") or "").strip()
        already = str(feed.get("already_prompted") or "") == "1"
        wt = str(feed.get("workspace_title") or "").strip()
        wp = str(feed.get("workspace_path") or "").strip()
        st = str(feed.get("session_title") or "").strip()
        if not st and wt:
            st = f"开发 · {wt}"

        # Host RPC 已建工作区/会话/投喂：展开工作区并点选会话
        if sid or already:
            from services.harness_toolkit import harness
            from services.harness_web_bridge import focus_extension_session

            self.report_status(
                f"正在定位：工作区「{wt or '扩展'}」→ 会话「{st or sid[:16]}」…",
                level=StatusLevel.INFO,
            )

            def _done(summary: str) -> None:
                focused = ("sess_clicked" in str(summary)) or (
                    "sess_selected" in str(summary)
                )
                hint_ws = f"「{wt}」" if wt else "扩展工作区"
                hint_ss = f"「{st}」" if st else "新会话"
                if focused:
                    pop_feed()
                    self._feed_strip.hide()
                    if already:
                        self.report_status(
                            f"已打开{hint_ws} · {hint_ss}（任务已在跑）",
                            level=StatusLevel.SUCCESS,
                        )
                    else:
                        ok = False
                        try:
                            ok = (
                                harness.prompt_session(sid, text, mode="queue")
                                if sid
                                else False
                            )
                        except Exception:
                            ok = False
                        self.report_status(
                            f"已打开{hint_ws} · {hint_ss}"
                            + (" · 已投喂" if ok else " · 可手动发送"),
                            level=StatusLevel.SUCCESS if ok else StatusLevel.WARNING,
                        )
                    return
                # 定位失败：条带保留明确路径，方便用户一眼找到
                self._feed_strip.set_preview(
                    str(feed.get("title") or wt or "开发扩展"),
                    f"请点左侧工作区 {hint_ws} → 会话 {hint_ss}",
                    auto_prepare=True,
                    workspace_path=wp,
                    workspace_title=wt,
                )
                self._feed_strip.show()
                self.report_status(
                    f"未能自动切换 · 请左侧点开 {hint_ws} 下的 {hint_ss}",
                    level=StatusLevel.WARNING,
                )

            focus_extension_session(
                self._view,
                workspace_title=wt,
                workspace_path=wp,
                session_id=sid,
                session_title=st,
                on_done=_done,
                retries=8,
                retry_ms=700,
            )
            return

        need_reload = str(feed.get("need_reload") or "") == "1" or bool(wp)
        if need_reload:
            self._start_prepare_with_reload()
        else:
            self._run_prepare_session()
    def _start_prepare_with_reload(self) -> None:
        """刷新内嵌页使 workspace.json 生效，再在 loadFinished 后准备会话。"""
        if self._view is None:
            self._run_prepare_session()
            return
        self.report_status("正在刷新 Harness 以加载新工作区…", level=StatusLevel.INFO)
        self._pending_prepare_after_reload = True
        self._prepare_retry = 0
        self._web_embedded_ok = False
        self._schedule_load_web(force=True, delay_ms=0)

    def _open_feed_workspace_folder(self) -> None:
        from services.harness_toolkit import harness

        feed = peek_feed()
        wp = str(feed.get("workspace_path") or "").strip()
        if not wp:
            self.report_status("没有扩展目录路径", level=StatusLevel.WARNING)
            return
        try:
            harness.open_folder(wp)
            harness.copy_text(wp)
            self.report_status(
                "已打开目录并复制路径 · 侧栏没有时在 Harness 点「+」添加该文件夹",
                level=StatusLevel.SUCCESS,
            )
        except Exception as exc:
            self.report_status(f"无法打开目录：{exc}", level=StatusLevel.WARNING)

    def _run_prepare_session(self) -> None:
        from services.harness_toolkit import PrepareResult, harness

        feed = peek_feed()
        text = format_feed_message(feed) if feed.get("text") else ""
        if not text.strip():
            return
        if not self._web_embedded_ok or self._view is None:
            QTimer.singleShot(600, self._run_prepare_session)
            return
        wt = str(feed.get("workspace_title") or "").strip()
        wp = str(feed.get("workspace_path") or "").strip()
        copy_to_clipboard(text)

        def _done(result: PrepareResult) -> None:
            hint = f"「{wt}」" if wt else "扩展目录"
            if result.ok and result.workspace == "clicked":
                pop_feed()
                self._feed_strip.hide()
                self.report_status(
                    f"已切换到{hint}并填入任务 · 确认路径后点发送",
                    level=StatusLevel.SUCCESS,
                )
                return
            if result.ok:
                pop_feed()
                self._feed_strip.hide()
                self.report_status(
                    f"已填入任务 · 请确认侧栏是{hint}后再发送",
                    level=StatusLevel.WARNING,
                )
                return
            # 侧栏仍无该工作区：保留条带，提示打开目录 / 再次刷新
            if result.workspace == "not_found" and self._prepare_retry < 1:
                self._prepare_retry += 1
                self.report_status(
                    f"侧栏暂无{hint} · 再刷新一次…",
                    level=StatusLevel.INFO,
                )
                QTimer.singleShot(400, self._start_prepare_with_reload)
                return
            self.report_status(
                f"侧栏未见{hint} · 点「打开扩展目录」，在 Harness「+」添加该路径后点「再次刷新并准备」",
                level=StatusLevel.WARNING,
            )

        harness.prepare_session(
            self._view,
            title=wt,
            path=wp,
            prompt=text,
            on_done=_done,
        )

    def _try_select_feed_workspace(self, feed: dict | None = None) -> None:
        from services.harness_toolkit import harness

        feed = feed or peek_feed()
        wt = str(feed.get("workspace_title") or "").strip()
        wp = str(feed.get("workspace_path") or "").strip()
        if not wt and not wp:
            return
        if not self._web_embedded_ok or self._view is None:
            return
        harness.select_workspace(self._view, title=wt, path=wp)

    def _dismiss_feed(self) -> None:
        self._pending_prepare_after_reload = False
        pop_feed()
        self._feed_strip.hide()

    def _apply_feed_clipboard(self) -> None:
        """手动点「准备」：优先 Host RPC 建区/会话/投喂，再点选。"""
        from services.harness_toolkit import harness

        feed = peek_feed()
        text = format_feed_message(feed) if feed.get("text") else ""
        if not text.strip():
            clip = QGuiApplication.clipboard()
            text = (clip.text() if clip is not None else "") or ""
        if not text.strip():
            self.report_status("没有可填入的内容", level=StatusLevel.WARNING)
            return
        copy_to_clipboard(text)
        wt = str(feed.get("workspace_title") or "").strip()
        wp = str(feed.get("workspace_path") or "").strip()
        if not wp:
            self._start_prepare_with_reload()
            return
        try:
            wid = harness.ensure_workspace(wp, title=wt or Path(wp).name)
            st = str(feed.get("session_title") or "").strip() or (
                f"开发 · {wt}" if wt else "开发扩展"
            )
            sid = harness.create_session(wid, title=st)
            ok = harness.prompt_session(sid, text, mode="queue") if sid else False
            from services.harness_feed import stash_feed

            stash_feed(
                text,
                title=str(feed.get("title") or ""),
                source=str(feed.get("source") or ""),
                workspace_title=wt,
                workspace_path=wp,
                auto_prepare=True,
                session_id=sid,
                already_prompted=ok,
                session_title=st,
            )
            self._auto_prepare_extension_feed()
        except Exception as exc:
            self.report_status(f"Host 投喂失败，尝试页面操作：{exc}", level=StatusLevel.WARNING)
            self._start_prepare_with_reload()

    def _on_repair_env(self) -> None:
        def _after(result: tuple[bool, str]):
            ok, text = result
            if not ok:
                self.report_status(text, level=StatusLevel.WARNING)
                return False
            self.report_status(text, level=StatusLevel.SUCCESS)
            # 修复后自动干净重启（不再二次确认）；返回 True 保留 busy 交给重启
            self._on_restart(confirm=False)
            return True

        self._run_bg(
            repair_harness_runtime,
            busy_label="正在修复环境…",
            on_ok=_after,
            phase=BusyPhase.REPAIRING,
        )

    def _on_backup_profile(self) -> None:
        def _job() -> tuple[bool, str]:
            from services.harness_profile_versions import snapshot_web_profile

            ok, msg, _ = snapshot_web_profile(reason="manual", mark_good=True)
            return ok, msg

        def _after(result: tuple[bool, str]):
            ok, text = result
            self.report_status(text, level=StatusLevel.SUCCESS if ok else StatusLevel.WARNING)
            return False

        self._run_bg(_job, busy_label="正在备份配置…", on_ok=_after)

    def _on_restore_last_good(self) -> None:
        def _job() -> tuple[bool, str]:
            from services.harness_plugins import strip_boot_killer_plugins
            from services.harness_profile_versions import restore_last_good

            ok, msg = restore_last_good()
            # 恢复后再扫一遍 denylist，防止旧快照仍含杀手插件
            _, kill_msg = strip_boot_killer_plugins()
            if "移除" in kill_msg:
                msg = f"{msg}；{kill_msg}"
            return ok, msg

        def _after(result: tuple[bool, str]):
            ok, text = result
            if not ok:
                self.report_status(text, level=StatusLevel.WARNING)
                return False
            self.report_status(text, level=StatusLevel.SUCCESS)
            self._on_restart(confirm=False)
            return True

        self._run_bg(
            _job,
            busy_label="正在恢复配置…",
            on_ok=_after,
            phase=BusyPhase.RESTORING,
        )

    def _open_dsh_home(self) -> None:
        open_in_file_manager(open_config_dir())

    def _open_install_root(self) -> None:
        open_in_file_manager(open_install_root())

    def _open_sidecar_log(self) -> None:
        path = open_sidecar_log()
        show_saved(self, "启动日志", str(path))

    def _on_uninstall(self) -> None:
        if not ask_confirm(
            self,
            "将停止服务并删除本机 Harness 安装包（~/.toa3/harness-runtime）。\n"
            "默认保留会话数据（.dsh）。是否继续？",
            title="卸载 Harness",
        ):
            return

        def _after(result: tuple[bool, str]):
            ok, text = result
            self._web_embedded_ok = False
            self._apply_status(read_harness_status(probe_http=True, http_timeout=0.6))
            self.report_status(text, level=StatusLevel.SUCCESS if ok else StatusLevel.WARNING)
            # 卸后回到三步门
            try:
                self._refresh_setup_sync()
            except Exception:
                pass
            return False

        self._run_bg(
            lambda: uninstall_harness_runtime(delete_install=True, keep_user_data=True),
            busy_label="正在卸载…",
            on_ok=_after,
            phase=BusyPhase.UNINSTALLING,
        )

    def _export_recent(self) -> None:
        out_dir = module_output_dir("harness_agent", create=True)
        self._run_bg(
            lambda: export_most_recent_session(out_dir),
            busy_label="正在导出…",
            on_ok=self._after_export,
        )

    def _after_export(self, payload) -> None:
        path, title = payload
        if path is None or not path.is_file():
            self.report_status("暂无可导出的会话", level=StatusLevel.WARNING)
            return
        show_saved(self, f"已导出：{title or path.name}", str(path.parent))
