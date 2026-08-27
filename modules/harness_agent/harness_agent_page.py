# -*- coding: utf-8 -*-
"""编码智能体：DeepSeek Harness 三栏指挥台。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSplitter, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_info, show_saved, show_warning
from modules.harness_agent.session_panel import SessionPanel
from modules.harness_agent.status_panel import StatusPanel
from services.harness_config import load_harness_config, web_url
from services.harness_feed import copy_to_clipboard, peek_feed, pop_feed
from services.harness_sidecar import (
    health_status,
    is_running,
    open_config_dir,
    restart,
    start,
    stop,
    validate_setup,
)
from services.harness_store import export_session_markdown
from services.os_open import open_in_file_manager
from services.storage_paths import module_output_dir
from widgets import HintLabel, PrimaryButton, SecondaryButton


def _webengine_available() -> bool:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except ImportError:
        return False


class HarnessAgentPage(BasePage):
    page_id = "harness_agent"
    page_title = "编码智能体"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        self._profile = None
        self._web_ready = _webengine_available()

        m = page_content_margins()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*m)
        outer.setSpacing(8)

        outer.addWidget(
            HintLabel(
                "DeepSeek Harness · 与 Codex / WorkBuddy 并肩。"
                "左栏会话 · 中栏 Agent · 右栏用量。密钥在 DSH 配置目录。"
            )
        )

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._btn_start = PrimaryButton("启动 Harness")
        self._btn_start.clicked.connect(lambda: self._on_start(silent=False))
        toolbar.addWidget(self._btn_start)
        self._btn_stop = SecondaryButton("停止")
        self._btn_stop.clicked.connect(self._on_stop)
        toolbar.addWidget(self._btn_stop)
        self._btn_restart = SecondaryButton("重启")
        self._btn_restart.clicked.connect(self._on_restart)
        toolbar.addWidget(self._btn_restart)
        self._btn_browser = SecondaryButton("浏览器打开")
        self._btn_browser.clicked.connect(self._open_external)
        toolbar.addWidget(self._btn_browser)
        self._btn_cfg = SecondaryButton("DSH 配置")
        self._btn_cfg.clicked.connect(self._open_dsh_home)
        toolbar.addWidget(self._btn_cfg)
        self._btn_export = SecondaryButton("导出会话")
        self._btn_export.clicked.connect(self._export_current)
        toolbar.addWidget(self._btn_export)
        self._btn_feed = SecondaryButton("粘贴投喂区")
        self._btn_feed.clicked.connect(self._apply_feed_clipboard)
        toolbar.addWidget(self._btn_feed)
        self._btn_new = SecondaryButton("新会话")
        self._btn_new.setToolTip("刷新 Harness Web（新建对话请在 Web 内操作）")
        self._btn_new.clicked.connect(self._reload_web)
        toolbar.addWidget(self._btn_new)
        toolbar.addStretch(1)
        self._status_label = HintLabel("")
        toolbar.addWidget(self._status_label)
        outer.addLayout(toolbar)

        self._feed_banner = HintLabel("")
        self._feed_banner.hide()
        outer.addWidget(self._feed_banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._session_panel = SessionPanel()
        self._session_panel.setMinimumWidth(200)
        self._session_panel.setMaximumWidth(320)
        splitter.addWidget(self._session_panel)

        self._center = QWidget()
        center_lay = QVBoxLayout(self._center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        self._web_host = QWidget()
        host_lay = QVBoxLayout(self._web_host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel(
            "Harness Web 将在此加载…" if self._web_ready else "未安装 Qt WebEngine，请用「浏览器打开」。"
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        host_lay.addWidget(self._placeholder, 1)
        center_lay.addWidget(self._web_host, 1)
        splitter.addWidget(self._center)

        self._status_panel = StatusPanel()
        self._status_panel.setMinimumWidth(200)
        self._status_panel.setMaximumWidth(300)
        splitter.addWidget(self._status_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        outer.addWidget(splitter, 1)

        self._session_panel.session_selected.connect(self._on_session_selected)
        self._current_session_id = ""

    def primary_focus_widget(self):
        return self._session_panel._search

    def on_enter(self) -> None:
        self._refresh_status_label()
        ok, hint = validate_setup()
        if hint:
            self.report_status(hint, level=StatusLevel.WARNING)
        if not ok:
            show_warning(self, hint)
        self._session_panel.start_auto_refresh()
        self._session_panel.refresh()
        self._status_panel.refresh_overview()
        self._apply_pending_feed()
        cfg = load_harness_config()
        if bool(cfg.get("auto_start", True)) and not is_running():
            self._on_start(silent=True)
        elif is_running():
            self._ensure_view()
            self._load_web()
        self.report_status("编码智能体 · Alt+Shift+H 唤起", level=StatusLevel.INFO)

    def on_leave(self) -> None:
        self._session_panel.stop_auto_refresh()

    def apply_pending_feed_from_stash(self) -> None:
        self._apply_pending_feed()

    def _apply_pending_feed(self) -> None:
        feed = peek_feed()
        text = str(feed.get("text") or "").strip()
        if not text:
            self._feed_banner.hide()
            return
        title = str(feed.get("title") or feed.get("source") or "办公链投喂")
        preview = text if len(text) <= 200 else text[:200] + "…"
        self._feed_banner.setText(f"待投喂 · {title}：{preview}")
        self._feed_banner.show()
        if copy_to_clipboard(text):
            self.report_status("投喂内容已复制到剪贴板，在 Harness 中粘贴为首条", level=StatusLevel.SUCCESS)

    def _apply_feed_clipboard(self) -> None:
        feed = peek_feed()
        text = str(feed.get("text") or "").strip()
        if not text:
            clip = QGuiApplication.clipboard()
            text = (clip.text() if clip is not None else "") or ""
        if not text.strip():
            show_warning(self, "没有可投喂的内容。")
            return
        copy_to_clipboard(text)
        pop_feed()
        show_info(self, "已复制到剪贴板，在 Harness 输入框粘贴即可。")

    def _refresh_status_label(self) -> None:
        st = health_status()
        if st.get("running"):
            owned = "TOA3 托管" if st.get("owned") else "外部实例"
            extra = ""
            if st.get("port_conflict"):
                extra = " · 端口占用未响应"
            self._status_label.setText(f"运行中 · {owned} · {st.get('url')}{extra}")
        else:
            if st.get("port_busy"):
                self._status_label.setText(f"端口 {st.get('port')} 占用 · 可重启或改端口")
            else:
                self._status_label.setText("未运行")

    def _on_start(self, silent: bool = False) -> None:
        def _run() -> None:
            ok, msg = start()
            self._refresh_status_label()
            if ok:
                self._ensure_view()
                self._load_web()
                if not silent:
                    self.report_status(msg, level=StatusLevel.SUCCESS)
            else:
                show_warning(self, msg)

        self.run_safe(_run, title="启动 Harness 失败")

    def _on_stop(self) -> None:
        def _run() -> None:
            ok, msg = stop()
            self._refresh_status_label()
            if ok:
                self.report_status(msg, level=StatusLevel.INFO)
            else:
                show_warning(self, msg)

        self.run_safe(_run, title="停止 Harness 失败")

    def _on_restart(self) -> None:
        def _run() -> None:
            ok, msg = restart()
            self._refresh_status_label()
            if ok:
                self._ensure_view()
                self._load_web()
                self.report_status(msg, level=StatusLevel.SUCCESS)
            else:
                show_warning(self, msg)

        self.run_safe(_run, title="重启 Harness 失败")

    def _ensure_view(self) -> None:
        if not self._web_ready or self._view is not None:
            return
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from services.storage_paths import module_data_dir

        profile_dir = module_data_dir("harness_agent", create=True) / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile("toa3_harness_agent", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(profile_dir / "cache"))

        self._view = QWebEngineView(self._web_host)
        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.loadStarted.connect(
            lambda: self.report_status("Harness 加载中…", level=StatusLevel.INFO)
        )
        self._view.loadFinished.connect(self._on_web_loaded)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setFontFamily(QWebEngineSettings.FontFamily.StandardFont, "Microsoft YaHei UI")
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, 14)

        lay = self._web_host.layout()
        if lay is not None:
            self._placeholder.hide()
            lay.addWidget(self._view, 1)

    def _load_web(self) -> None:
        if self._view is None:
            return
        self._view.setUrl(QUrl(web_url()))

    def _reload_web(self) -> None:
        if not is_running():
            show_warning(self, "请先启动 Harness。")
            return
        self._ensure_view()
        self._load_web()
        self.report_status("已刷新 Harness Web", level=StatusLevel.INFO)

    def _on_web_loaded(self, ok: bool) -> None:
        if ok:
            self.report_status("Harness Web 就绪", level=StatusLevel.SUCCESS)
        else:
            self.report_status("Harness 加载失败，可点重启", level=StatusLevel.WARNING)

    def _open_external(self) -> None:
        import webbrowser

        webbrowser.open(web_url())

    def _open_dsh_home(self) -> None:
        open_in_file_manager(open_config_dir())

    def _on_session_selected(self, session_id: str) -> None:
        self._current_session_id = session_id
        self._status_panel.show_session(session_id)

    def _export_current(self) -> None:
        sid = self._current_session_id or self._session_panel._current_id()
        if not sid:
            show_warning(self, "请先选择要导出的会话。")
            return
        out_dir = module_output_dir("harness_agent", create=True)

        def _run() -> None:
            path = export_session_markdown(sid, out_dir)
            if path is None or not path.is_file():
                show_warning(self, "导出失败，请确认 dshm 与 DSH_HOME 配置。")
                return
            show_saved(self, f"会话已导出：{path.name}", str(path.parent))

        self.run_safe(_run, title="导出会话失败")
