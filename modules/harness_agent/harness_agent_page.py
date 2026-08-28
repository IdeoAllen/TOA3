# -*- coding: utf-8 -*-
"""
编码智能体 · 小白路径

进页自动检测 → 未安装一键安装 → 已安装启停服务 → 主区 Harness Web。
"""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import ask_confirm, show_info, show_saved, show_warning
from modules.harness_agent.feed_strip import FeedStrip
from modules.harness_agent.setup_gate import SetupGate
from services.harness_config import load_harness_config, web_url
from services.harness_export import export_most_recent_session
from services.harness_feed import copy_to_clipboard, format_feed_message, peek_feed, pop_feed
from services.harness_probe import HarnessPageState, probe_page_state
from services.harness_setup import install_harness_runtime, repair_harness_runtime
from services.harness_sidecar import (
    health_status,
    is_running,
    open_config_dir,
    restart,
    restart_owned,
    start,
    stop,
)
from services.harness_surface import open_in_system_browser, prefer_browser
from services.harness_web_bridge import inject_prompt
from services.os_open import open_in_file_manager
from services.storage_paths import module_output_dir
from widgets import DangerButton, HintLabel, PrimaryButton, SecondaryButton


def _webengine_available() -> bool:
    from services.qt_webengine_bootstrap import webengine_import_ok

    return webengine_import_ok()


class HarnessAgentPage(BasePage):
    page_id = "harness_agent"
    page_title = "编码智能体"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        self._profile = None
        self._web_ready = _webengine_available()
        self._pending_feed_inject = False
        self._ui_external_only = False
        self._page_state = HarnessPageState.CHECKING
        self._web_load_ok = False
        self._load_status_reported = False

        m = page_content_margins()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(m[0], m[1], m[2], max(4, m[3]))
        outer.setSpacing(6)

        self._service_bar = QWidget()
        bar = QHBoxLayout(self._service_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)

        self._status_label = QLabel("正在检测…")
        self._status_label.setObjectName("HarnessServiceStatus")
        bar.addWidget(self._status_label)

        self._btn_start = PrimaryButton("启动服务")
        self._btn_start.clicked.connect(lambda: self._on_start(silent=False))
        bar.addWidget(self._btn_start)

        self._btn_stop = DangerButton("停止服务")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.hide()
        bar.addWidget(self._btn_stop)

        self._btn_feed = SecondaryButton("投喂")
        self._btn_feed.setToolTip("将办公链或剪贴板内容送入 Harness")
        self._btn_feed.clicked.connect(self._apply_feed_clipboard)
        bar.addWidget(self._btn_feed)

        self._btn_browser = SecondaryButton("浏览器打开")
        self._btn_browser.clicked.connect(self._open_external)
        bar.addWidget(self._btn_browser)

        self._btn_more = SecondaryButton("更多")
        self._btn_more.setMenu(self._build_more_menu())
        bar.addWidget(self._btn_more)

        bar.addStretch(1)
        self._service_bar.hide()
        outer.addWidget(self._service_bar)

        self._feed_strip = FeedStrip(self)
        self._feed_strip.hide()
        self._feed_strip.apply_requested.connect(self._apply_feed_clipboard)
        self._feed_strip.dismissed.connect(self._dismiss_feed)
        outer.addWidget(self._feed_strip)

        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self._setup_gate = SetupGate(self._body)
        self._setup_gate.install_requested.connect(self._on_one_click_install)
        self._setup_gate.key_saved.connect(self._after_key_saved)
        self._setup_gate.open_settings_requested.connect(self._open_settings)
        body_lay.addWidget(self._setup_gate, 1)

        self._external_hint = HintLabel("已在浏览器打开 · 点工具栏「浏览器打开」可切回内嵌")
        self._external_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._external_hint.hide()
        body_lay.addWidget(self._external_hint, 1)

        self._host = QWidget()
        self._host.setObjectName("HarnessWebHost")
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        host_lay = QVBoxLayout(self._host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel("点击「启动服务」后，Harness 界面将显示在此处")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("HarnessIdleHint")
        host_lay.addWidget(self._placeholder, 1)
        body_lay.addWidget(self._host, 1)

        outer.addWidget(self._body, 1)
        self._show_body_gate()

    def _build_more_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("切回内嵌显示", self._show_embed_surface)
        menu.addAction("接管并重启", self._on_takeover_restart)
        menu.addAction("重启服务", self._on_restart)
        menu.addAction("修复运行环境", self._on_repair_env)
        menu.addSeparator()
        menu.addAction("导出最近会话", self._export_recent)
        menu.addAction("打开 DSH 目录", self._open_dsh_home)
        menu.addSeparator()
        menu.addAction("编码智能体设置", self._open_settings)
        return menu

    def _show_body_gate(self) -> None:
        self._setup_gate.show()
        self._host.hide()
        self._external_hint.hide()

    def _show_body_web(self) -> None:
        self._setup_gate.hide()
        self._external_hint.hide()
        self._host.show()

    def _show_body_external_hint(self) -> None:
        self._setup_gate.hide()
        self._host.hide()
        self._external_hint.show()

    def _open_settings(self) -> None:
        w = self.window()
        if w is not None and hasattr(w, "navigate"):
            w.navigate("system_settings")
            self.report_status("系统设置 · 能力接入 → Harness", level=StatusLevel.INFO)
        else:
            show_warning(self, "请从侧栏进入「系统设置」。")

    def primary_focus_widget(self):
        if self._page_state == HarnessPageState.NEEDS_KEY and self._setup_gate.isVisible():
            return self._setup_gate._key_edit
        # 内嵌 Harness 自行管理焦点；壳层抢焦点会导致弹层闪动
        return None

    def on_enter(self) -> None:
        self._apply_pending_feed()
        state, msg = probe_page_state()
        if state == HarnessPageState.RUNNING:
            self._apply_page_state(state, msg)
            if self._web_load_ok and self._view is not None:
                self._ensure_view_visible()
            else:
                self._present_running_surface()
            return
        if state == HarnessPageState.STOPPED:
            self._apply_page_state(state, msg)
            cfg = load_harness_config()
            if bool(cfg.get("auto_start", True)):
                self._on_start(silent=True)
            return
        self._apply_page_state(state, msg)

    def on_leave(self) -> None:
        pass

    def apply_pending_feed_from_stash(self) -> None:
        self._apply_pending_feed()

    def _run_probe(self, *, auto_start_after: bool = False) -> None:
        self._apply_page_state(HarnessPageState.CHECKING, "正在检测 Harness…")
        self.run_safe(
            probe_page_state,
            title="检测 Harness",
            on_success=lambda r: self._after_probe(r, auto_start_after),
        )

    def _after_probe(
        self,
        result: tuple[HarnessPageState, str],
        auto_start_after: bool,
    ) -> None:
        state, msg = result
        self._apply_page_state(state, msg)
        if auto_start_after and state == HarnessPageState.STOPPED:
            cfg = load_harness_config()
            if bool(cfg.get("auto_start", True)):
                self._on_start(silent=True)
        elif state == HarnessPageState.RUNNING:
            if self._web_load_ok and self._view is not None:
                self._ensure_view_visible()
            else:
                self._present_running_surface()

    def _apply_page_state(self, state: HarnessPageState, message: str = "") -> None:
        prev = self._page_state
        self._page_state = state

        if state in (HarnessPageState.RUNNING, HarnessPageState.STOPPED) and prev == state:
            self._sync_service_bar(state)
            return

        if state == HarnessPageState.CHECKING:
            self._service_bar.show()
            self._status_label.setText(message or "正在检测…")
            self._btn_start.hide()
            self._btn_stop.hide()
            self._btn_feed.setEnabled(False)
            self._btn_browser.setEnabled(False)
            if not self._web_load_ok:
                self._show_body_gate()
                self._setup_gate.show_state(state, message)
            return

        if state in (HarnessPageState.NOT_INSTALLED, HarnessPageState.NEEDS_KEY):
            self._service_bar.hide()
            self._show_body_gate()
            self._setup_gate.show_state(state, message)
            self._placeholder.show()
            return

        self._service_bar.show()
        if self._ui_external_only:
            self._show_body_external_hint()
        else:
            self._show_body_web()
        self._sync_service_bar(state)

    def _sync_service_bar(self, state: HarnessPageState) -> None:
        if state == HarnessPageState.RUNNING:
            st = health_status()
            if st.get("owned"):
                self._status_label.setText("● TOA 托管 · 运行中")
            else:
                self._status_label.setText("● 外部实例 · 运行中")
            self._btn_start.hide()
            self._btn_stop.show()
            self._btn_feed.setEnabled(True)
            self._btn_browser.setEnabled(True)
        else:
            self._status_label.setText("○ 服务未启动")
            self._btn_stop.hide()
            self._btn_start.show()
            self._btn_feed.setEnabled(False)
            self._btn_browser.setEnabled(False)
            self._placeholder.show()

        if self._ui_external_only:
            self._btn_browser.setText("切回内嵌")
        else:
            self._btn_browser.setText("浏览器打开")

    def _on_one_click_install(self) -> None:
        self._setup_gate.set_installing(True)

        def _after(result: tuple[bool, str]) -> None:
            self._setup_gate.set_installing(False)
            ok, text = result
            if not ok:
                show_warning(self, text)
                return
            show_info(self, text)
            state, msg = probe_page_state()
            self._apply_page_state(state, msg)
            if state == HarnessPageState.STOPPED:
                show_info(self, "点击「启动服务」即可使用。")

        self.run_safe(install_harness_runtime, title="安装 DeepSeek Harness", on_success=_after)

    def _after_key_saved(self) -> None:
        state, msg = probe_page_state()
        self._apply_page_state(state, msg)
        if state == HarnessPageState.STOPPED:
            self._on_start(silent=False)

    def _apply_pending_feed(self) -> None:
        feed = peek_feed()
        text = str(feed.get("text") or "").strip()
        if not text:
            self._feed_strip.hide()
            self._pending_feed_inject = False
            return
        title = str(feed.get("title") or feed.get("source") or "办公链")
        preview = text if len(text) <= 120 else text[:120] + "…"
        self._feed_strip.set_preview(title, preview)
        self._feed_strip.show()
        self._pending_feed_inject = bool(load_harness_config().get("feed_auto_inject", False))

    def _dismiss_feed(self) -> None:
        pop_feed()
        self._feed_strip.hide()

    def _apply_feed_clipboard(self) -> None:
        if not is_running():
            show_warning(self, "请先启动服务。")
            return
        feed = peek_feed()
        text = format_feed_message(feed) if feed.get("text") else ""
        if not text.strip():
            clip = QGuiApplication.clipboard()
            text = (clip.text() if clip is not None else "") or ""
        if not text.strip():
            show_warning(self, "剪贴板为空。")
            return
        copy_to_clipboard(text)
        pop_feed()
        self._feed_strip.hide()
        self._ensure_view()
        if self._view:
            inject_prompt(self._view, text, self._on_inject_result)
        else:
            show_info(self, "已复制到剪贴板。")

    def _on_inject_result(self, result: str) -> None:
        if result == "ok":
            self.report_status("已填入 Harness", level=StatusLevel.SUCCESS)
        else:
            show_info(self, "已复制到剪贴板，请手动粘贴。")

    def _show_embed_surface(self) -> None:
        self._ui_external_only = False
        if is_running():
            self._ensure_view()
            if self._web_load_ok:
                self._ensure_view_visible()
            else:
                self._load_web()
        self._apply_page_state(probe_page_state()[0])

    def _present_running_surface(self) -> None:
        if prefer_browser() and not self._ui_external_only:
            open_in_system_browser()
            self._ui_external_only = True
        else:
            self._ui_external_only = False
            self._ensure_view()
            if not self._web_load_ok:
                self._load_web()
            else:
                self._ensure_view_visible()
        self._apply_page_state(HarnessPageState.RUNNING)

    def _on_start(self, silent: bool = False) -> None:
        def _run() -> None:
            ok, msg = start()
            state, _ = probe_page_state()
            if ok:
                if state == HarnessPageState.RUNNING and self._web_load_ok:
                    self._apply_page_state(state)
                else:
                    self._apply_page_state(state)
                    self._present_running_surface()
                if not silent:
                    self.report_status(msg, level=StatusLevel.SUCCESS)
            else:
                self._apply_page_state(state)
                show_warning(self, msg)

        self.run_safe(_run, title="启动 Harness 服务")

    def _on_stop(self) -> None:
        st = health_status()
        if st.get("running") and not st.get("owned"):
            if not ask_confirm(
                self,
                "将结束本机端口上的 Harness（可能来自 WorkBuddy 或其它程序）。是否继续？",
                title="停止 Harness 服务",
            ):
                return
            force = True
        else:
            force = False

        def _run() -> None:
            ok, msg = stop(force=force)
            state, _ = probe_page_state()
            if ok:
                self._web_load_ok = False
                self._load_status_reported = False
            self._apply_page_state(state)
            if ok:
                self.report_status(msg, level=StatusLevel.INFO)
            else:
                show_warning(self, msg)

        self.run_safe(_run, title="停止 Harness 服务")

    def _on_takeover_restart(self) -> None:
        if not ask_confirm(
            self,
            "将结束当前 Harness 并由 TOA 重新启动（便于启停托管）。是否继续？",
            title="接管 Harness 服务",
        ):
            return

        def _run() -> None:
            ok, msg = restart_owned()
            state, _ = probe_page_state()
            self._apply_page_state(state)
            if ok:
                self._present_running_surface()
                self.report_status(msg, level=StatusLevel.SUCCESS)
            else:
                show_warning(self, msg)

        self.run_safe(_run, title="接管 Harness 服务")

    def _on_restart(self) -> None:
        if not is_running():
            show_warning(self, "服务未在运行。")
            return

        def _run() -> None:
            ok, msg = restart()
            state, _ = probe_page_state()
            self._apply_page_state(state)
            if ok:
                self._present_running_surface()
                self.report_status(msg, level=StatusLevel.SUCCESS)
            else:
                show_warning(self, msg)

        self.run_safe(_run, title="重启 Harness 服务")

    def _on_repair_env(self) -> None:
        def _after(result: tuple[bool, str]) -> None:
            ok, text = result
            if not ok:
                show_warning(self, text)
                return
            show_info(self, text)
            state, msg = probe_page_state()
            self._apply_page_state(state, msg)

        self.run_safe(repair_harness_runtime, title="修复 Harness 环境", on_success=_after)

    def _open_external(self) -> None:
        if not is_running():
            show_warning(self, "请先启动服务。")
            return
        if self._ui_external_only:
            self._show_embed_surface()
            return
        url = open_in_system_browser()
        self._ui_external_only = True
        self._apply_page_state(HarnessPageState.RUNNING)
        show_info(self, f"已在浏览器打开：{url}")

    def _ensure_view_visible(self) -> None:
        if self._view is None:
            return
        self._placeholder.hide()
        if not self._view.isVisible():
            self._view.show()
        self._show_body_web()

    def _ensure_view(self) -> None:
        if not self._web_ready:
            return
        if self._view is not None:
            return
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from services.storage_paths import module_data_dir

        profile_dir = module_data_dir("harness_agent", create=True) / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile("toa3_harness_agent", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(profile_dir / "cache"))

        self._view = QWebEngineView(self._host)
        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.loadStarted.connect(self._on_web_load_started)
        self._view.loadFinished.connect(self._on_web_loaded)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setFontFamily(QWebEngineSettings.FontFamily.StandardFont, "Microsoft YaHei UI")
        settings.setFontFamily(QWebEngineSettings.FontFamily.SansSerifFont, "Microsoft YaHei UI")
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, 14)
        settings.setFontSize(QWebEngineSettings.FontSize.MinimumFontSize, 10)

        lay = self._host.layout()
        if lay is not None:
            self._placeholder.hide()
            lay.addWidget(self._view, 1)

        self._apply_web_zoom()

    def _apply_web_zoom(self) -> None:
        if self._view is None:
            return
        cfg = load_harness_config()
        try:
            zoom = float(cfg.get("web_zoom") or 1.0)
        except (TypeError, ValueError):
            zoom = 1.0
        zoom = max(0.5, min(2.0, zoom))
        self._view.setZoomFactor(zoom)

    def _on_web_load_started(self) -> None:
        if self._web_load_ok or self._load_status_reported:
            return
        self.report_status("Harness 加载中…", level=StatusLevel.INFO)

    def _load_web(self, *, force: bool = False) -> None:
        if self._view is None:
            return
        target = web_url().rstrip("/")
        current = (self._view.url().toString() or "").rstrip("/")
        if not force and self._web_load_ok and current.startswith(target):
            self._ensure_view_visible()
            return
        self._ensure_view_visible()
        self._view.setUrl(QUrl(web_url()))

    def _on_web_loaded(self, ok: bool) -> None:
        if not ok:
            self._web_load_ok = False
            if not self._load_status_reported:
                self.report_status("加载失败，可重启服务或改用浏览器", level=StatusLevel.WARNING)
            return
        was_loaded = self._web_load_ok
        self._web_load_ok = True
        self._apply_web_zoom()
        if not was_loaded and not self._load_status_reported:
            self.report_status("Harness 已就绪", level=StatusLevel.SUCCESS)
            self._load_status_reported = True
        if self._pending_feed_inject and self._view is not None:
            feed = peek_feed()
            text = format_feed_message(feed) if feed.get("text") else ""
            if text:
                inject_prompt(self._view, text, self._on_inject_result)

    def _open_dsh_home(self) -> None:
        open_in_file_manager(open_config_dir())

    def _export_recent(self) -> None:
        out_dir = module_output_dir("harness_agent", create=True)

        def _run() -> None:
            path, title = export_most_recent_session(out_dir)
            if path is None or not path.is_file():
                show_warning(self, "暂无可导出的会话。")
                return
            show_saved(self, f"已导出：{title or path.name}", str(path.parent))

        self.run_safe(_run, title="导出会话")
