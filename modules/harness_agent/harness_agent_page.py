# -*- coding: utf-8 -*-
"""
DeepSeek Harness · 侧栏任务页（group: engines）

流程：先画壳（启停 + 状态 + WebEngine 占位）→ 读安装 → 读服务 → 就绪后加载 URL。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import ask_confirm, show_saved, show_warning
from modules.harness_agent.feed_strip import FeedStrip
from modules.harness_agent.setup_gate import SetupGate
from services.harness_config import load_harness_config, web_url
from services.harness_export import export_most_recent_session
from services.harness_feed import copy_to_clipboard, format_feed_message, peek_feed, pop_feed
from services.harness_probe import HarnessPageState, probe_page_state
from services.harness_setup import install_harness_runtime, repair_harness_runtime
from services.harness_sidecar import (
    is_running,
    open_config_dir,
    prepare_sidecar_start,
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
from widgets import DangerButton, HintLabel, MenuButton, PrimaryButton, SecondaryButton, SectionTitle


def _webengine_available() -> bool:
    from services.qt_webengine_bootstrap import webengine_import_ok

    return webengine_import_ok()


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


def _make_harness_web_page(profile, view, *, base_url: str):
    from PySide6.QtCore import QUrl

    from services.webengine_host import ToaWebEnginePage

    base = QUrl(base_url)
    host = (base.host() or "").lower()

    def _accept(url, _nav_type, is_main_frame) -> bool:
        if is_main_frame and url.scheme() in ("http", "https") and host:
            target_host = (url.host() or "").lower()
            if target_host and target_host != host:
                return False
        return True

    return ToaWebEnginePage(profile, view, accept_nav=_accept)


class _HarnessWebHost(QWidget):
    """iframe 式宿主：与网页工作台同构 — placeholder + WebView 同槽位，浮层仅盖内容区。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HarnessWebHost")
        # 勿 WA_OpaquePaintEvent：与 GPU WebView 叠层时易悬停闪烁
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._placeholder = QLabel()
        self._placeholder.setObjectName("HarnessWebPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        lay.addWidget(self._placeholder, 1)
        self._overlay = QLabel(self)
        self._overlay.setObjectName("HarnessWebOverlay")
        self._overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overlay.setWordWrap(True)
        # 加载遮罩默认挡点击；揭开后 hide，避免误挡 WebView
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._overlay.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def set_placeholder(self, text: str) -> None:
        self._placeholder.setText(text)
        self._placeholder.show()

    def embed_view(self, view: QWidget) -> None:
        """把 WebView 放进槽位；遮罩盖住冷启动。不冻主窗。"""
        lay = self.layout()
        if lay is None:
            return
        if not (self._overlay.text() or "").strip():
            self._overlay.setText("正在准备 DeepSeek Harness…")
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._overlay.show()
        self._overlay.raise_()
        if lay.indexOf(view) < 0:
            view.hide()
            lay.addWidget(view, 1)
        self._placeholder.hide()
        view.show()
        self._overlay.raise_()

    def set_overlay_text(self, text: str | None) -> None:
        """仅用全局 QSS（HarnessWebOverlay）；禁止 setStyleSheet 以免整窗重绘抖动。"""
        if text:
            if self._overlay.text() != text:
                self._overlay.setText(text)
            self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            if not self._overlay.isVisible():
                self._overlay.show()
            self._overlay.raise_()
        else:
            # 就绪后彻底放开鼠标，避免透明层仍吃事件造成「点一下卡一下」
            self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            if self._overlay.isVisible():
                self._overlay.hide()
            self._overlay.clear()


class HarnessAgentPage(BasePage):
    page_id = "harness_agent"
    page_title = "DeepSeek Harness"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        self._profile = None
        self._web_ready = _webengine_available()
        self._action_busy = False
        self._setup_state = HarnessPageState.STOPPED
        self._status: HarnessStatus | None = None
        self._start_deadline = 0.0
        self._load_web_timer = QTimer(self)
        self._load_web_timer.setSingleShot(True)
        self._load_web_timer.timeout.connect(self._do_scheduled_load_web)
        self._load_web_force = False
        self._web_embedded_ok = False
        self._web_nav_overlay = False
        self._pending_prepare_after_reload = False
        self._prepare_retry = 0
        self._status_checked_at = 0.0
        self._STATUS_STALE_S = 12.0
        self._prewarm_done = False
        self._more_menu_signature: tuple[bool, bool] | None = None
        self._f11_filter = _HarnessF11Filter(self)
        self._auto_start_tried = False
        self._browser_surface_opened = False
        self._reveal_token = 0
        self._cred_heal_tried = False
        # 进/离页代次：作废 singleShot，避免引擎↔业务↔系统快切时原生闪退
        self._visit_gen = 0

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
        self._btn_start.setFixedWidth(92)
        self._btn_start.clicked.connect(self._on_start)

        self._btn_stop = DangerButton("停止服务")
        self._btn_stop.setFixedWidth(92)
        self._btn_stop.clicked.connect(self._on_stop)

        self._start_stop_stack = QStackedWidget()
        self._start_stop_stack.setFixedWidth(92)
        self._start_stop_stack.addWidget(self._btn_start)
        self._start_stop_stack.addWidget(self._btn_stop)
        bar.addWidget(self._start_stop_stack)

        self._btn_refresh = SecondaryButton("刷新")
        self._btn_refresh.clicked.connect(self._reload_web)
        bar.addWidget(self._btn_refresh)

        self._btn_more = MenuButton("更多")
        self._more_menu = QMenu(self)
        self._btn_more.setMenu(self._more_menu)
        bar.addWidget(self._btn_more)

        bar.addStretch(1)
        outer.addWidget(self._service_bar)
        self._rebuild_more_menu()

        # --- 状态行（安装 / 服务）---
        status_row = QVBoxLayout()
        status_row.setSpacing(2)
        self._install_line = HintLabel("安装：检测中…")
        self._install_line.setWordWrap(True)
        self._service_line = HintLabel("服务：检测中…")
        self._service_line.setWordWrap(True)
        status_row.addWidget(self._install_line)
        status_row.addWidget(self._service_line)
        outer.addLayout(status_row)

        self._feed_strip = FeedStrip(self)
        self._feed_strip.hide()
        self._feed_strip.apply_requested.connect(self._apply_feed_clipboard)
        self._feed_strip.dismissed.connect(self._dismiss_feed)
        self._feed_strip.open_folder_requested.connect(self._open_feed_workspace_folder)
        outer.addWidget(self._feed_strip)

        # --- 未安装 / 待 Key：一键安装 ---
        self._setup_gate = SetupGate(self)
        self._setup_gate.install_requested.connect(self._on_one_click_install)
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
            self._host.set_placeholder("当前环境未包含内嵌浏览器，请用「更多 → 在浏览器打开」。")
        else:
            self._host.set_placeholder("正在准备 DeepSeek Harness…")
        web_outer.addWidget(self._host, 1)
        self._body_stack.addWidget(self._web_wrap)
        self._body_stack.setCurrentIndex(1)
        outer.addWidget(self._body_stack, 1)

        self._sync_service_bar_placeholder()

    def _sync_service_bar_placeholder(self) -> None:
        self._btn_start.setEnabled(False)
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
        self._more_menu.addAction("在浏览器打开", self._open_external)
        if embed:
            self._more_menu.addAction("改用系统浏览器显示", self._switch_to_browser_surface)
        else:
            self._more_menu.addAction("改回套件内嵌显示", self._switch_to_embed_surface)
        self._more_menu.addAction("重启服务", self._on_restart)
        self._more_menu.addAction("接管并重启", self._on_takeover_restart)
        self._more_menu.addAction("修复运行环境", self._on_repair_env)
        self._more_menu.addSeparator()
        self._more_menu.addAction("导出最近会话", self._export_recent)
        self._more_menu.addAction("打开 DSH 目录", self._open_dsh_home)
        self._more_menu.addSeparator()
        self._more_menu.addAction("DeepSeek Harness 设置", self._open_settings)

    def primary_focus_widget(self):
        if self._setup_state == HarnessPageState.NEEDS_KEY and self._body_stack.currentIndex() == 0:
            return self._setup_gate._key_edit
        # 勿把焦点交给 WebEngine，避免进页时整窗闪动（网页工作台也只聚焦工具条）
        return self._btn_refresh if self._body_stack.currentIndex() == 1 else None

    def _page_active(self, visit: int | None = None) -> bool:
        if visit is not None and visit != self._visit_gen:
            return False
        win = self.window()
        if win is not None and getattr(win, "_current_id", None) != self.page_id:
            return False
        return True

    def on_enter(self) -> None:
        """切页先完成绘制，再刷状态；WebView 延后挂载。"""
        self._visit_gen += 1
        visit = self._visit_gen
        QTimer.singleShot(120, lambda v=visit: self._on_enter_deferred(v))

    def _on_enter_deferred(self, visit: int | None = None) -> None:
        if not self._page_active(visit):
            return
        try:
            from services.harness_model_defaults import ensure_official_default_model

            ensure_official_default_model()
        except Exception:
            pass
        self._apply_pending_feed()
        self._refresh_setup_sync()
        if self._setup_state in (HarnessPageState.NOT_INSTALLED, HarnessPageState.NEEDS_KEY):
            return
        self._show_workspace()
        if self._status is not None:
            self._install_line.setText(f"安装：{self._status.install_label}")
            self._service_line.setText(f"服务：{self._status.service_label}")
            self._sync_service_bar()
        if prefer_browser():
            if self._status_is_fresh() and self._status is not None:
                if self._status.running:
                    self._apply_browser_surface(self._status)
                elif not self._maybe_auto_start(self._status):
                    self._show_web_idle("服务未启动 · 点「启动服务」后将在浏览器打开")
            else:
                self._show_web_idle("正在连接 DeepSeek Harness…")
                QTimer.singleShot(0, lambda v=self._visit_gen: self._refresh_status_http_if(v))
            return
        if not self._web_ready:
            return
        # 离页已销毁 View：每次进页新建，勿复用旧 HWND（二次回电闪退）
        # 略延迟，等上一轮 deleteLater 走完事件循环
        self._show_web_idle("正在准备 DeepSeek Harness…")
        QTimer.singleShot(280, lambda v=self._visit_gen: self._ensure_view_after_chrome(v))

    def _refresh_status_http_if(self, visit: int) -> None:
        if not self._page_active(visit):
            return
        self._refresh_status_http()

    def _ensure_view_after_chrome(self, visit: int | None = None) -> None:
        if not self._page_active(visit):
            return
        if prefer_browser():
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
        """切走顶栏时先停定时器、作废回调；WebEngine 由壳层延迟销毁。"""
        self._auto_start_tried = False
        self._cred_heal_tried = False
        self._visit_gen += 1
        self._reveal_token += 1
        try:
            self._load_web_timer.stop()
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            if fw is not None and self._view is not None:
                if fw is self._view or self._view.isAncestorOf(fw):
                    fw.clearFocus()
        except Exception:
            pass
        self._show_web_idle("已切走 · 返回本页后重新嵌入")

    def on_leave(self) -> None:
        # 下次进页若仍停着，允许再走一次自动启动 / 密钥修复
        self.soft_leave()
        self._park_web_embed()

    def _park_web_embed(self) -> None:
        """兼容旧名：实际改为销毁 View。"""
        self._destroy_web_embed()

    def _destroy_web_embed(self) -> None:
        """离页销毁内嵌 View（保留 Profile），二次进页再新建。"""
        try:
            from PySide6.QtWidgets import QApplication

            fw = QApplication.focusWidget()
            if fw is not None and self._view is not None:
                if fw is self._view or self._view.isAncestorOf(fw):
                    fw.clearFocus()
        except Exception:
            pass
        view = self._view
        self._view = None
        self._web_embedded_ok = False
        self._web_nav_overlay = False
        self._show_web_idle("已切走 · 返回本页后重新嵌入")
        if view is None:
            return
        try:
            view.hide()
        except Exception:
            pass
        try:
            view.loadStarted.disconnect(self._on_web_load_started)
        except Exception:
            pass
        try:
            view.loadFinished.disconnect(self._on_web_loaded)
        except Exception:
            pass
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage

            page = view.page()
            if page is not None:
                page.triggerAction(QWebEnginePage.WebAction.Stop)
            # 勿在销毁路径 setUrl(about:blank)：与 deleteLater 竞态易二次回电闪退
            view.setPage(None)
        except Exception:
            pass
        try:
            view.setParent(None)
        except Exception:
            pass
        # 延迟 deleteLater：与壳层切页重叠时同步销毁易闪退
        QTimer.singleShot(320, lambda v=view: self._delete_view_later(v))

    @staticmethod
    def _delete_view_later(view) -> None:
        try:
            view.deleteLater()
        except Exception:
            pass

    def _should_keep_embed_on_enter(self) -> bool:
        if not self._web_embedded_ok or self._view is None:
            return False
        current = (self._view.url().toString() or "").rstrip("/")
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
        """进页自动启动：设置勾选且已安装就绪、服务未跑时拉起一次。"""
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
        self.report_status("正在自动启动 DeepSeek Harness…", level=StatusLevel.INFO)
        self._run_sidecar_start(busy_label="正在启动…")
        return True

    def _maybe_heal_credentials(self, status: HarnessStatus) -> bool:
        """外部实例 / 脏环境变量导致历史会话接不上模型时，自动接管并注入密钥。"""
        if self._action_busy or self._cred_heal_tried:
            return False
        if status.install != InstallState.READY:
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
        self.report_status(f"{reason}正在接管并重启…", level=StatusLevel.WARNING)
        self._set_action_busy(True, "正在修复密钥…")
        QTimer.singleShot(0, self._takeover_restart_on_main)
        return True

    def _on_heal_credentials(self) -> None:
        """兼容旧入口：与「接管并重启」同路径。"""
        self._on_takeover_restart()

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
        self._install_line.setText(f"安装：{status.install_label}")
        # 操作进行中：保留忙碌文案，避免仍显示「运行中/冲突」造成按钮与状态错位
        if self._action_busy:
            return
        svc = f"服务：{status.service_label}"
        if "⚠" in (status.detail or ""):
            svc += " · 需检查 API Key"
        self._service_line.setText(svc)
        self._sync_service_bar()
        if self._maybe_auto_start(status):
            return
        if self._maybe_heal_credentials(status):
            return
        if prev is not None and self._status_web_equivalent(prev, status):
            if self._web_embedded_ok or (
                prefer_browser() and self._browser_surface_opened
            ):
                return
        self._sync_web_for_status(status)

    def _sync_service_bar(self) -> None:
        st = self._status
        if self._action_busy or st is None:
            return
        if st.running:
            self._start_stop_stack.setCurrentIndex(1)
        else:
            self._start_stop_stack.setCurrentIndex(0)
            self._btn_start.setEnabled(st.install == InstallState.READY)
        self._rebuild_more_menu()
        self._btn_start.setEnabled(
            (not st.running) and st.install == InstallState.READY and not self._action_busy
        )
        self._btn_stop.setEnabled(st.running and not self._action_busy)
        self._btn_refresh.setEnabled(True)
        self._btn_more.setEnabled(True)
        self._btn_refresh.setToolTip("重新探测状态并刷新内嵌页")
        self._btn_more.setToolTip("")
        self._btn_stop.setToolTip("停止 Harness 服务")

    def _sync_web_for_status(self, status: HarnessStatus) -> None:
        if status.install != InstallState.READY:
            return
        if status.running:
            if prefer_browser():
                self._apply_browser_surface(status)
                return
            if not self._web_ready:
                self._show_web_idle("服务已运行 · 请用「更多 → 在浏览器打开」")
                return
            if self._view is not None:
                current = (self._view.url().toString() or "").rstrip("/")
                target = status.url.rstrip("/")
                if self._web_embedded_ok and current.startswith(target):
                    self._show_web_embed()
                    return
            self._schedule_load_web(delay_ms=120)
        else:
            interim_busy = status.port_busy and not status.http_ok
            if not interim_busy:
                self._web_embedded_ok = False
            if status.service == ServiceState.PORT_CONFLICT:
                self._show_web_idle(status.detail)
            elif interim_busy and self._should_keep_embed_on_enter():
                self._show_web_embed()
            else:
                self._show_web_idle("服务未启动 · 点「启动服务」后加载界面")

    def _apply_browser_surface(self, status: HarnessStatus) -> None:
        """surface_mode=browser：同一 URL 开系统浏览器，页内仅占位。

        注意：仅用户显式选「系统浏览器」时走此路径；dsh 侧已加 --no-open，
        避免启动时再弹一次外部浏览器。
        """
        url = status.url or web_url()
        first = not self._browser_surface_opened
        if first:
            open_in_system_browser()
            self._browser_surface_opened = True
        self._web_embedded_ok = False
        self._show_web_idle(
            f"已在系统浏览器打开 · {url}\n"
            "点「更多 → 改回套件内嵌显示」可收回 WebEngine。"
        )
        if first:
            self.report_status("已在系统浏览器打开 Harness", level=StatusLevel.SUCCESS)

    def _set_action_busy(self, busy: bool, label: str = "") -> None:
        self._action_busy = busy
        if busy and label:
            self._status_label.setText(label)
            self._service_line.setText(f"服务：处理中 · {label}")
            # 操作中：禁启停与更多，避免叠操作；刷新仍可用以便强制看状态
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(False)
            self._btn_more.setEnabled(False)
            self._btn_refresh.setEnabled(True)
            tip = f"正在执行：{label}（完成后可操作）"
            self._btn_start.setToolTip(tip)
            self._btn_stop.setToolTip(tip)
            self._btn_more.setToolTip(tip)
            self._btn_refresh.setToolTip("强制刷新状态/页面（当前操作仍在后台进行）")
        elif not busy:
            self._status_label.setText("DeepSeek Harness")
            self._sync_service_bar()
            if self._status is not None:
                svc = f"服务：{self._status.service_label}"
                if "⚠" in (self._status.detail or ""):
                    svc += " · 需检查 API Key"
                self._service_line.setText(svc)

    def _show_web_idle(self, text: str) -> None:
        if isinstance(self._host, _HarnessWebHost):
            self._host.set_overlay_text(text)

    def _show_web_embed(self) -> None:
        # 晚一帧再揭遮罩，等 Chromium 首帧画完，减轻大闪
        self._reveal_token += 1
        token = self._reveal_token
        visit = self._visit_gen
        QTimer.singleShot(80, lambda: self._reveal_web_embed(token, visit))

    def _reveal_web_embed(self, token: int | None = None, visit: int | None = None) -> None:
        if token is not None and token != self._reveal_token:
            return
        if not self._page_active(visit):
            return
        if not self._web_embedded_ok:
            return
        if self._view is not None and not self._view.isVisible():
            try:
                self._view.show()
            except Exception:
                pass
        if isinstance(self._host, _HarnessWebHost):
            self._host.set_overlay_text(None)

    def _refresh_status_async(self) -> None:
        if self._action_busy:
            QTimer.singleShot(400, self._refresh_status_async)
            return
        if (
            self._status_is_fresh()
            and self._status is not None
            and self._status.running
            and (self._web_embedded_ok or prefer_browser())
        ):
            return
        if self._should_keep_embed_on_enter():
            self._install_line.setText("安装：已安装")
            self._service_line.setText("服务：运行中 · 正在确认…")
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
        if not self._web_ready or self._view is not None:
            return
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from services.webengine_host import apply_webengine_view_defaults

        class _HarnessWebView(QWebEngineView):
            def keyPressEvent(self, event) -> None:  # noqa: N802
                if (
                    event.key() == Qt.Key.Key_F11
                    and event.modifiers() == Qt.KeyboardModifier.NoModifier
                ):
                    shell = self.window()
                    if shell is not None and hasattr(shell, "_toggle_fullscreen"):
                        shell._toggle_fullscreen()
                        event.accept()
                        return
                super().keyPressEvent(event)

        # 禁止整窗 setUpdatesEnabled(False)：顶栏会像「一点就退」
        self._show_web_idle("正在准备 DeepSeek Harness…")

        # 必须复用同一 Profile：同名再建会在二次进页时原生崩
        if self._profile is None:
            profile_dir = module_data_dir("harness_agent", create=True) / "browser_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            self._profile = QWebEngineProfile("toa3_harness_agent", self)
            self._profile.setPersistentStoragePath(str(profile_dir))
            self._profile.setCachePath(str(profile_dir / "cache"))

        self._view = _HarnessWebView(self._host)
        page = _make_harness_web_page(self._profile, self._view, base_url=web_url())
        self._view.setPage(page)
        apply_webengine_view_defaults(self._view)
        self._view.installEventFilter(self._f11_filter)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view.loadStarted.connect(self._on_web_load_started)
        self._view.loadFinished.connect(self._on_web_loaded)

        self._host.embed_view(self._view)
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
        force = self._load_web_force
        self._load_web_force = False
        self._load_web(force=force)

    def _focus_web_view(self) -> None:
        if self._view is None:
            return
        self._view.setFocus(Qt.FocusReason.OtherFocusReason)

    def _load_web(self, *, force: bool = False) -> None:
        st = self._status
        if not self._web_ready or st is None or not st.running:
            return
        if prefer_browser():
            self._apply_browser_surface(st)
            return
        self._ensure_view()
        if self._view is None:
            return
        url = web_url()
        current = (self._view.url().toString() or "").rstrip("/")
        target = url.rstrip("/")
        if not force and current.startswith(target) and self._web_embedded_ok:
            self._show_web_embed()
            return
        self._web_nav_overlay = True
        self._web_embedded_ok = False
        self._show_web_idle("DeepSeek Harness 加载中…")
        # URL 已正确但尚未标记就绪时必须 reload，否则遮罩会永久卡住
        if force or current.startswith(target):
            self._view.reload()
            return
        self._view.setUrl(QUrl(url))

    def _reload_web(self) -> None:
        st = self._status
        if st is None or not st.running:
            self.report_status("请先启动 Harness 服务", level=StatusLevel.WARNING)
            return
        if prefer_browser():
            open_in_system_browser()
            self._browser_surface_opened = True
            self.report_status("已在浏览器刷新打开", level=StatusLevel.INFO)
            return
        self._web_embedded_ok = False
        self._schedule_load_web(force=True, delay_ms=0)
        self.report_status("已刷新页面", level=StatusLevel.INFO)

    def _on_web_load_started(self) -> None:
        if self._web_nav_overlay or not self._web_embedded_ok:
            self._show_web_idle("DeepSeek Harness 加载中…")
            self.report_status("DeepSeek Harness 加载中…", level=StatusLevel.INFO)

    def _on_web_loaded(self, ok: bool) -> None:
        self._web_nav_overlay = False
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
            self._show_web_embed()
            self.report_status("DeepSeek Harness 已就绪", level=StatusLevel.SUCCESS)
            if self._pending_prepare_after_reload:
                self._pending_prepare_after_reload = False
                # 等侧栏工作区列表渲染完再切
                QTimer.singleShot(700, self._run_prepare_session)
        else:
            self._web_embedded_ok = False
            self._show_web_idle("页面加载失败 · 可点「刷新」或「启动服务」重试")
            self.report_status("Harness 页面未响应", level=StatusLevel.WARNING)
            if self._pending_prepare_after_reload:
                self._pending_prepare_after_reload = False
                self.report_status(
                    "刷新失败 · 请点「刷新」后手动选工作区，或用「打开扩展目录」在 Harness 点 + 添加",
                    level=StatusLevel.WARNING,
                )

    def _run_bg(self, fn, *, busy_label: str, on_ok, on_err=None) -> None:
        if self._action_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return

        def _wrapped_ok(payload) -> None:
            try:
                on_ok(payload)
            finally:
                self._set_action_busy(False)

        self._set_action_busy(True, busy_label)
        self.run_safe(fn, on_success=_wrapped_ok)

    def _after_sidecar_started(self, ok: bool, msg: str) -> None:
        self._apply_status(read_harness_status(probe_http=True, http_timeout=0.8))
        if not ok:
            self.report_status(msg, level=StatusLevel.WARNING)
            return
        self.report_status(msg, level=StatusLevel.SUCCESS)

    def _run_sidecar_start(self, *, busy_label: str, allow_busy: bool = False) -> None:
        if self._action_busy and not allow_busy:
            self.report_status("上一项操作仍在进行", level=StatusLevel.WARNING)
            return
        self._show_web_idle("正在启动 Sidecar…")
        if not self._action_busy:
            self._set_action_busy(True, busy_label)
        elif busy_label:
            self._status_label.setText(busy_label)
        self.run_safe(prepare_sidecar_start, on_success=self._on_prepare_done)

    def _on_prepare_done(self, result: tuple[bool, str, bool]) -> None:
        ok, msg, already = result
        if not ok:
            self._set_action_busy(False)
            self.report_status(msg, level=StatusLevel.WARNING)
            return
        if already:
            # 绝不能把「外部实例还在跑」当成启动成功——否则密钥未注入
            st = read_harness_status(probe_http=True, http_timeout=0.6)
            try:
                from services.harness_credentials import needs_credential_takeover

                need, reason = needs_credential_takeover(
                    running=bool(st.running), owned=bool(st.owned)
                )
            except Exception:
                need, reason = (bool(st.running and not st.owned), "外部实例未注入密钥")
            if need:
                self.report_status(
                    f"{reason}正在接管…",
                    level=StatusLevel.WARNING,
                )
                QTimer.singleShot(0, self._takeover_restart_on_main)
                return
            self._set_action_busy(False)
            self._after_sidecar_started(True, msg)
            return
        QTimer.singleShot(0, self._spawn_sidecar_on_main)

    def _spawn_sidecar_on_main(self) -> None:
        ok, msg = spawn_sidecar_process()
        if not ok:
            self._set_action_busy(False)
            self.report_status(msg, level=StatusLevel.WARNING)
            return
        self._start_deadline = time.monotonic() + 25.0
        QTimer.singleShot(350, self._poll_sidecar_start)

    def _poll_sidecar_start(self) -> None:
        if time.monotonic() > self._start_deadline:
            self._set_action_busy(False)
            self._show_web_idle("启动超时 · 请查看 sidecar 日志后重试")
            self.report_status("Harness 启动超时", level=StatusLevel.WARNING)
            return
        phase, msg = sidecar_start_progress()
        if phase == "ready":
            self._set_action_busy(False)
            self._after_sidecar_started(True, msg)
            return
        if phase == "failed":
            self._set_action_busy(False)
            self._show_web_idle("启动失败 · 见状态栏说明")
            self.report_status(msg, level=StatusLevel.WARNING)
            return
        self._status_label.setText("正在启动 Sidecar…")
        self._show_web_idle("Sidecar 启动中，请稍候…")
        QTimer.singleShot(350, self._poll_sidecar_start)

    def _on_start(self) -> None:
        self._run_sidecar_start(busy_label="正在启动…")

    def _on_stop(self) -> None:
        st = self._status
        force = False
        if st is not None and st.running and not st.owned:
            if not ask_confirm(
                self,
                "将结束本机端口上的 Harness（可能来自其它程序）。是否继续？",
                title="停止 Harness",
            ):
                return
            force = True

        self._set_action_busy(True, "正在停止…")
        QTimer.singleShot(0, lambda: self._stop_sidecar_on_main(force))

    def _stop_sidecar_on_main(self, force: bool) -> None:
        ok, msg = stop(force=force)
        self._set_action_busy(False)
        self._web_embedded_ok = False
        self._apply_status(read_harness_status(probe_http=True, http_timeout=0.8))
        level = StatusLevel.INFO if ok else StatusLevel.WARNING
        self.report_status(msg, level=level)

    def _on_takeover_restart(self) -> None:
        if not ask_confirm(self, "将结束当前 Harness 并由 TOA 重新启动。是否继续？", title="接管服务"):
            return
        self._set_action_busy(True, "正在接管…")
        QTimer.singleShot(0, self._takeover_restart_on_main)

    def _takeover_restart_on_main(self) -> None:
        """主线程：先强杀端口占用，等空闲后再 spawn（避免假成功复用外部）。"""
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
        self._status_label.setText("正在释放端口…")
        self._service_line.setText("服务：处理中 · 正在释放端口…")
        self._show_web_idle("正在结束外部 Harness 并注入 API Key…")
        QTimer.singleShot(150, self._heal_wait_port_then_spawn)

    def _heal_wait_port_then_spawn(self) -> None:
        from services.harness_sidecar import _find_listener_pids, _kill_pids, _port_open

        port = int(getattr(self, "_heal_port", 3081) or 3081)
        still = _port_open(port) or is_running(timeout=0.35)
        if still:
            if time.monotonic() > float(getattr(self, "_heal_deadline", 0) or 0):
                _kill_pids(_find_listener_pids(port))
                if _port_open(port) or is_running(timeout=0.35):
                    self._set_action_busy(False)
                    self.report_status(
                        f"端口 {port} 仍被占用，无法注入密钥。请结束 node.exe 后点「接管并重启」。",
                        level=StatusLevel.WARNING,
                    )
                    return
            else:
                QTimer.singleShot(200, self._heal_wait_port_then_spawn)
                return
        ok, msg = spawn_sidecar_process()
        if not ok:
            self._set_action_busy(False)
            self.report_status(msg, level=StatusLevel.WARNING)
            return
        self._start_deadline = time.monotonic() + 25.0
        self._status_label.setText("正在用设置页密钥启动…")
        self._service_line.setText("服务：处理中 · 正在用设置页密钥启动…")
        QTimer.singleShot(350, self._poll_sidecar_start)

    def _on_restart(self) -> None:
        st = self._status or read_harness_status(probe_http=True)
        if st.service == ServiceState.RUNNING_EXTERNAL:
            self._on_takeover_restart()
            return
        self._set_action_busy(True, "正在重启…")
        QTimer.singleShot(0, self._restart_sidecar_on_main)

    def _restart_sidecar_on_main(self) -> None:
        stop(force=False)
        self._run_sidecar_start(busy_label="正在重启…", allow_busy=True)

    def _open_external(self) -> None:
        open_in_system_browser()
        self._browser_surface_opened = True
        self.report_status("已在系统浏览器打开", level=StatusLevel.INFO)

    def _switch_to_browser_surface(self) -> None:
        set_surface_mode("browser")
        self._more_menu_signature = None
        self._rebuild_more_menu()
        st = self._status
        if st is not None and st.running:
            self._browser_surface_opened = False
            self._apply_browser_surface(st)
        else:
            self.report_status("已改为浏览器优先 · 启动后将打开系统浏览器", level=StatusLevel.INFO)

    def _switch_to_embed_surface(self) -> None:
        set_surface_mode("embed")
        self._browser_surface_opened = False
        self._more_menu_signature = None
        self._rebuild_more_menu()
        self.report_status("已改回套件内嵌", level=StatusLevel.INFO)
        st = self._status
        if st is not None and st.running:
            self._schedule_load_web(force=True, delay_ms=0)

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

    def _on_one_click_install(self) -> None:
        self._setup_gate.set_installing(True)

        def _after(result: tuple[bool, str]) -> None:
            self._setup_gate.set_installing(False)
            ok, text = result
            if not ok:
                show_warning(self, text)
                return
            self.report_status(text, level=StatusLevel.SUCCESS)
            self._deferred_enter()

        self._run_bg(install_harness_runtime, busy_label="正在安装…", on_ok=_after)

    def _after_key_saved(self) -> None:
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
        def _after(result: tuple[bool, str]) -> None:
            ok, text = result
            if not ok:
                self.report_status(text, level=StatusLevel.WARNING)
                return
            self.report_status(text, level=StatusLevel.SUCCESS)
            self._deferred_enter()

        self._run_bg(repair_harness_runtime, busy_label="正在修复环境…", on_ok=_after)

    def _open_dsh_home(self) -> None:
        open_in_file_manager(open_config_dir())

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
