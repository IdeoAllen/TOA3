# -*- coding: utf-8 -*-
"""本地 Web 引擎宿主页：未装一键装（进度）→ 已装判启停 → 启动并内嵌。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.ui_spec import page_content_margins
from core.user_messages import show_warning
from services.local_web_engine import (
    discover_root,
    get_spec,
    owned_process,
    prefer_embed,
    read_status,
    save_user_root,
    set_prefer_embed,
    start_engine,
    stop_engine,
)
from services.local_web_engine.install import can_one_click_install, install_engine
from widgets import HintLabel, PageHeader, PrimaryButton, ProgressBar, SecondaryButton


def _webengine_available() -> bool:
    from services.qt_webengine_bootstrap import webengine_import_ok

    return webengine_import_ok()


class _F11Filter(QObject):
    def __init__(self, page: "LocalWebHostPage") -> None:
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


class _WebHost(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LocalWebHostCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        from PySide6.QtWidgets import QStackedLayout

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self._placeholder = QLabel()
        self._placeholder.setObjectName("LocalWebHostPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)
        self._view = None
        self._view_index = -1

    def set_placeholder(self, text: str, *, hide_view: bool = True) -> None:
        """hide_view=False：已嵌入时只改文案，不切走 WebView（避免打断 Comfy 下拉）。"""
        self._placeholder.setText(text)
        if hide_view or self._view is None or not self._view.isVisible():
            self._stack.setCurrentWidget(self._placeholder)
            if self._view is not None and hide_view:
                self._view.hide()
            return
        # 保持 WebView 当前页，勿抢焦点

    def embed_view(self, view: QWidget, *, take_focus: bool = False) -> None:
        """挂载/显示 WebView。take_focus 仅首次加载时为 True，轮询禁止抢焦点。"""
        self._view = view
        if self._stack.indexOf(view) < 0:
            self._view_index = self._stack.addWidget(view)
        view.show()
        self._stack.setCurrentWidget(view)
        if take_focus:
            try:
                view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                view.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

    def has_live_view(self) -> bool:
        return (
            self._view is not None
            and self._stack.currentWidget() is self._view
            and self._view.isVisible()
        )

class _InstallWorker(QObject):
    progress = Signal(str, int)
    finished = Signal(bool, str)

    def __init__(self, engine_id: str) -> None:
        super().__init__()
        self._engine_id = engine_id

    def run(self) -> None:
        def _prog(msg: str, pct: int) -> None:
            self.progress.emit(msg, pct)

        try:
            ok, msg = install_engine(self._engine_id, on_progress=_prog)
            self.finished.emit(ok, msg)
        except Exception as exc:
            self.finished.emit(False, str(exc))


class _StartWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, engine_id: str) -> None:
        super().__init__()
        self._engine_id = engine_id

    def run(self) -> None:
        try:
            ok, msg = start_engine(self._engine_id)
            self.finished.emit(ok, msg)
        except Exception as exc:
            self.finished.emit(False, str(exc))


class LocalWebHostPage(BasePage):
    """子类设置 page_id / engine_id / page_title。"""

    page_id = "local_web_host"
    page_title = "本地引擎"
    engine_id = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        self._profile = None
        self._embedded_url = ""
        self._poll = QTimer(self)
        self._poll.setInterval(2500)
        self._poll.timeout.connect(self._refresh_status)
        self._start_pending = False
        self._auto_start_tried = False
        self._install_busy = False
        self._install_thread: QThread | None = None
        self._install_worker: _InstallWorker | None = None
        self._start_thread: QThread | None = None
        self._start_worker: _StartWorker | None = None
        self._visit_gen = 0
        self._browser_surface_opened = False
        self._force_embed_session = False  # 本会话临时内嵌（未写盘前）

        outer = QVBoxLayout(self)
        m = page_content_margins()
        outer.setContentsMargins(m[0], m[1], m[2], m[3])
        outer.setSpacing(8)

        spec = get_spec(self.engine_id)
        title = (spec.title if spec else self.page_title) or self.page_title
        desc = (spec.description if spec else "") or "未安装一键装 · 已装自动启停并内嵌"
        outer.addWidget(PageHeader(title, desc))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._status = HintLabel("检测中…")
        bar.addWidget(self._status, 1)
        self._btn_start = PrimaryButton("启动")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_start.setEnabled(False)
        self._btn_start.setToolTip("正在检测安装状态…")
        bar.addWidget(self._btn_start)
        self._btn_stop = SecondaryButton("停止")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setToolTip("检测完成前不可停止")
        bar.addWidget(self._btn_stop)
        self._btn_reload = SecondaryButton("刷新")
        self._btn_reload.clicked.connect(self._on_reload)
        bar.addWidget(self._btn_reload)
        self._btn_browser = SecondaryButton("浏览器打开")
        self._btn_browser.clicked.connect(self._on_browser)
        bar.addWidget(self._btn_browser)
        self._btn_surface = SecondaryButton("改用内嵌")
        self._btn_surface.clicked.connect(self._on_toggle_surface)
        self._btn_surface.setToolTip("默认浏览器表面以保护外壳；仅在需要时改回套件内嵌")
        bar.addWidget(self._btn_surface)
        self._btn_root = SecondaryButton("指定目录")
        self._btn_root.clicked.connect(self._on_pick_root)
        bar.addWidget(self._btn_root)
        self._btn_open_root = SecondaryButton("打开目录")
        self._btn_open_root.clicked.connect(self._on_open_root)
        bar.addWidget(self._btn_open_root)
        outer.addLayout(bar)

        self._body = QStackedWidget()
        # 0 = 安装门；1 = 工作区
        gate = QWidget()
        gate_lay = QVBoxLayout(gate)
        gate_lay.setContentsMargins(0, 24, 0, 24)
        gate_lay.addStretch(1)
        self._gate_title = HintLabel("正在检测安装…")
        self._gate_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lay.addWidget(self._gate_title)
        self._gate_body = HintLabel("请稍候，完成后显示安装或工作区。")
        self._gate_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gate_body.setWordWrap(True)
        gate_lay.addWidget(self._gate_body)
        self._progress = ProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        gate_lay.addWidget(self._progress)
        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_install = PrimaryButton("一键安装")
        self._btn_install.clicked.connect(self._on_one_click_install)
        self._btn_install.setEnabled(False)
        row.addWidget(self._btn_install)
        self._btn_gate_pick = SecondaryButton("指定目录")
        self._btn_gate_pick.clicked.connect(self._on_pick_root)
        row.addWidget(self._btn_gate_pick)
        row.addStretch(1)
        gate_lay.addLayout(row)
        gate_lay.addStretch(2)
        self._body.addWidget(gate)

        self._host = _WebHost()
        self._body.addWidget(self._host)
        self._host.set_placeholder("正在准备…")
        outer.addWidget(self._body, 1)

        self._f11 = _F11Filter(self)
        self._sync_surface_button()

    def uses_webengine_embed(self) -> bool:
        """壳层切页：仅真正挂了 WebEngine 时才走 web-heavy 销毁路径。"""
        return self._view is not None and self._uses_embed()

    def _uses_embed(self) -> bool:
        if self._force_embed_session:
            return True
        return prefer_embed(self.engine_id)

    def _sync_surface_button(self) -> None:
        if self._uses_embed():
            self._btn_surface.setText("改用浏览器")
            self._btn_surface.setToolTip("改用系统浏览器显示 Guest，保护外壳不被 Chromium 拖垮")
        else:
            self._btn_surface.setText("改用内嵌")
            self._btn_surface.setToolTip("在套件内嵌显示（可能影响外壳流畅度，Comfy 默认不推荐）")

    def soft_leave(self) -> None:
        """壳层切走：停轮询；浏览器表面无 WebEngine 可即切。"""
        self._visit_gen += 1
        self._poll.stop()
        self._auto_start_tried = False
        if not self.uses_webengine_embed():
            return
        self._schedule_destroy_web_embed()

    def on_enter(self) -> None:
        self.report_status(self.page_title, level=StatusLevel.INFO)
        self._visit_gen += 1
        self._auto_start_tried = False
        self._browser_surface_opened = False
        self._sync_surface_button()
        visit = self._visit_gen
        # 浏览器表面无需等 Web；内嵌仍略延迟减轻闪
        delay = 40 if not self._uses_embed() else 120
        QTimer.singleShot(delay, lambda v=visit: self._on_enter_deferred(v))

    def _on_enter_deferred(self, visit: int | None = None) -> None:
        if visit is not None and visit != self._visit_gen:
            return
        if self.window() is not None and getattr(self.window(), "_current_id", None) != self.page_id:
            return
        st = self._refresh_status()
        self._poll.start()
        if st is None:
            return
        self._drive_lifecycle(st)

    def on_leave(self) -> None:
        self._visit_gen += 1
        self._poll.stop()
        self._auto_start_tried = False
        self._browser_surface_opened = False
        if self.uses_webengine_embed():
            self._schedule_destroy_web_embed()
        spec = get_spec(self.engine_id)
        if spec and spec.stop_on_leave:
            stop_engine(self.engine_id)

    def _schedule_destroy_web_embed(self) -> None:
        view = self._view
        self._view = None
        self._embedded_url = ""
        if view is None:
            return
        try:
            view.hide()
        except Exception:
            pass
        try:
            view.loadFinished.disconnect(self._on_load_finished)
        except Exception:
            pass
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage

            page = view.page()
            if page is not None:
                page.triggerAction(QWebEnginePage.WebAction.Stop)
            view.setPage(None)
        except Exception:
            pass
        try:
            view.setParent(None)
        except Exception:
            pass
        QTimer.singleShot(320, lambda v=view: self._delete_view_later(v))

    @staticmethod
    def _delete_view_later(view) -> None:
        try:
            view.deleteLater()
        except Exception:
            pass

    def _drive_lifecycle(self, st) -> None:
        """未装→安装门；已装未启→自动启动；已启→浏览器或内嵌。"""
        if self._install_busy:
            self._show_gate(installing=True)
            return
        if not st.installed:
            self._show_gate(installing=False)
            return
        self._body.setCurrentIndex(1)
        if st.running:
            if self._uses_embed():
                self.report_status(f"{self.page_title} · 加载中", level=StatusLevel.INFO)
            else:
                self._apply_browser_surface(st, open_browser=True)
            return
        spec = get_spec(self.engine_id)
        if spec is not None and not bool(getattr(spec, "auto_start", True)):
            hint = "已安装 · 点「启动」后打开" if not self._uses_embed() else "已安装 · 点「启动」后嵌入"
            self._host.set_placeholder(hint)
            return
        if self._auto_start_tried or self._start_pending:
            return
        self._auto_start_tried = True
        self._begin_start(auto=True)

    def _apply_browser_surface(self, st, *, open_browser: bool) -> None:
        """浏览器表面：主窗只做启停控制台，Guest 在系统浏览器。"""
        url = (st.url if st is not None else "") or ""
        if not url:
            spec = get_spec(self.engine_id)
            url = spec.web_url() if spec else ""
        first = open_browser and not self._browser_surface_opened
        if first and url:
            QDesktopServices.openUrl(QUrl(url))
            self._browser_surface_opened = True
            self.report_status(
                f"已在系统浏览器打开 · {self.page_title}",
                level=StatusLevel.SUCCESS,
            )
        # 确保不挂 WebEngine
        if self._view is not None:
            self._schedule_destroy_web_embed()
        self._host.set_placeholder(
            f"已在系统浏览器打开 · {url}\n\n"
            "外壳只负责启动 / 停止 / 指定目录。\n"
            "模型下拉等请在浏览器里操作（完整交互）。\n"
            "需要内嵌时点顶栏「改用内嵌」。",
            hide_view=True,
        )
    def _show_gate(self, *, installing: bool) -> None:
        self._body.setCurrentIndex(0)
        spec = get_spec(self.engine_id)
        title = (spec.title if spec else self.page_title) or self.page_title
        if installing:
            self._gate_title.setText(f"正在安装 {title}")
            self._status.setText("安装进行中…")
            self._btn_install.setEnabled(False)
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(False)
            self._btn_browser.setEnabled(False)
            self._progress.show()
            return
        self._progress.hide()
        self._progress.setValue(0)
        self._gate_title.setText(f"未安装 {title}")
        self._status.setText("未安装 · 请一键安装或指定含引擎文件的目录")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._btn_browser.setEnabled(False)
        self._btn_start.setToolTip("未安装，无法启动")
        if can_one_click_install(self.engine_id):
            target = ""
            if spec and spec.default_roots:
                target = str(spec.default_roots[0])
            self._gate_body.setText(
                f"将下载到：{target or '默认目录'}\n完成后自动启动并内嵌。"
            )
            self._btn_install.setEnabled(True)
            self._btn_install.setText("一键安装")
            self._btn_install.show()
        else:
            hint = (spec.install_hint if spec else "") or "请指定已安装的引擎根目录。"
            self._gate_body.setText(hint)
            self._btn_install.hide()

    def _begin_start(self, *, auto: bool = False) -> None:
        if self._start_thread is not None or self._install_busy:
            return
        self._start_pending = True
        self._start_was_auto = auto
        self._btn_start.setEnabled(False)
        self._btn_start.setToolTip("正在启动…")
        self._btn_stop.setEnabled(True)
        self._btn_stop.setToolTip("停止启动中的进程")
        self._btn_reload.setEnabled(True)
        has_live = self._host.has_live_view() if self._uses_embed() else False
        ready_hint = (
            "正在启动服务…\n就绪后自动嵌入"
            if self._uses_embed()
            else "正在启动服务…\n就绪后将在系统浏览器打开"
        )
        self._host.set_placeholder(
            ready_hint
            + ("\n（大模型引擎首次启动可能需数分钟）" if self.engine_id == "comfyui_web" else ""),
            hide_view=not has_live,
        )
        self.report_status("正在启动…" if auto else "正在启动服务…", level=StatusLevel.INFO)
        self._poll.setInterval(800)

        thread = QThread(self)
        worker = _StartWorker(self.engine_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_start_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._start_thread = thread
        self._start_worker = worker
        thread.start()

    def _on_start_finished(self, ok: bool, msg: str) -> None:
        self._start_thread = None
        self._start_worker = None
        was_auto = bool(getattr(self, "_start_was_auto", False))
        if not ok:
            self._start_pending = False
            if not was_auto:
                show_warning(self, msg)
            self.report_status(msg, level=StatusLevel.WARNING)
            self._host.set_placeholder(msg)
            self._refresh_status()
            return
        from services.local_web_engine import probe_port_host

        spec = get_spec(self.engine_id)
        if spec is not None:
            probe_port_host(int(spec.port), engine_id=self.engine_id, force=True)
        self.report_status(msg, level=StatusLevel.INFO)
        QTimer.singleShot(200, self._refresh_status)

    def _destroy_web_embed(self) -> None:
        """兼容旧调用：改为延迟销毁。"""
        self._schedule_destroy_web_embed()

    def _refresh_status(self):
        st = read_status(self.engine_id, probe_http=False)
        root_s = str(st.root) if st.root else "（未配置）"
        self._status.setText(f"{st.detail} · {root_s}")
        starting = owned_process(self.engine_id) is not None and not st.running
        busy = self._install_busy or self._start_thread is not None
        # 已嵌入时端口短抖 → 勿当成未运行去 hide View（Comfy 下拉会点不动）
        sticky_embed = bool(
            self._host.has_live_view()
            and self._embedded_url
            and not st.running
            and not starting
        )
        if sticky_embed:
            miss = int(getattr(self, "_port_miss_ticks", 0) or 0) + 1
            self._port_miss_ticks = miss
            if miss < 4:
                self._btn_start.setEnabled(False)
                self._btn_stop.setEnabled(True)
                self._btn_browser.setEnabled(True)
                return st
        else:
            self._port_miss_ticks = 0

        self._btn_start.setEnabled(
            st.installed and not st.running and not starting and not busy and not self._start_pending
        )
        self._btn_stop.setEnabled(
            (st.running or starting or self._start_pending) and not self._install_busy
        )
        self._btn_browser.setEnabled(bool(st.running and st.url))
        self._btn_reload.setEnabled(not self._install_busy)
        self._btn_root.setEnabled(not busy)
        if busy or starting or self._start_pending:
            self._btn_start.setToolTip("启动进行中…")
            self._btn_stop.setToolTip("停止服务")
        else:
            self._btn_start.setToolTip("启动引擎服务")
            self._btn_stop.setToolTip("停止引擎服务" if st.running else "当前未运行")

        if not st.installed and not self._install_busy:
            self._show_gate(installing=False)
            return st

        if st.installed:
            self._body.setCurrentIndex(1)

        if st.running:
            self._start_pending = False
            self._port_miss_ticks = 0
            self._poll.setInterval(4000)
            if not self._uses_embed():
                self._apply_browser_surface(st, open_browser=True)
                return st
            if self._view is None or self._embedded_url.rstrip("/") != st.url.rstrip("/"):
                self._ensure_embed(st.url)
            elif not self._host.has_live_view():
                # 仅当被占位盖住时才恢复，勿每次轮询 setFocus（会打断 Comfy 模型下拉）
                self._host.embed_view(self._view, take_focus=False)
            return st

        if self._start_pending or starting:
            self._poll.setInterval(800)
            if (
                self._start_pending
                and self._start_thread is None
                and not starting
                and not st.running
            ):
                ticks = int(getattr(self, "_start_fail_ticks", 0) or 0) + 1
                self._start_fail_ticks = ticks
                if ticks >= 10:
                    self._start_pending = False
                    self._start_fail_ticks = 0
                    self._host.set_placeholder("启动未就绪，可点「启动」重试", hide_view=True)
                    self.report_status(
                        "启动超时或进程已退出，请查看日志后重试",
                        level=StatusLevel.WARNING,
                    )
                    return st
            else:
                self._start_fail_ticks = 0
            has_live = self._host.has_live_view()
            self._host.set_placeholder(
                "正在启动…\n等待端口打开后自动加载"
                + (
                    "\n（大模型引擎首次启动可能需数分钟）"
                    if self.engine_id == "comfyui_web"
                    else ""
                ),
                hide_view=not has_live,
            )
        elif st.installed:
            self._poll.setInterval(2500)
            if not self._auto_start_tried:
                self._drive_lifecycle(st)
            else:
                self._host.set_placeholder(
                    "已安装 · 启动未就绪，可点「启动」重试", hide_view=True
                )
        return st

    def _on_one_click_install(self) -> None:
        if self._install_busy:
            return
        if not can_one_click_install(self.engine_id):
            self._on_pick_root()
            return
        self._install_busy = True
        self._show_gate(installing=True)
        self._progress.setValue(0)
        self._gate_body.setText("准备安装…")
        self.report_status("正在一键安装…", level=StatusLevel.INFO)

        thread = QThread(self)
        worker = _InstallWorker(self.engine_id)
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

    def _on_install_progress(self, msg: str, pct: int) -> None:
        self._progress.show()
        self._progress.setValue(pct)
        self._gate_body.setText(msg)
        self._status.setText(f"安装中 {pct}% · {msg}")

    def _on_install_finished(self, ok: bool, msg: str) -> None:
        self._install_busy = False
        self._install_thread = None
        self._install_worker = None
        self._progress.hide()
        if not ok:
            self._show_gate(installing=False)
            self._gate_body.setText(msg)
            show_warning(self, msg)
            self.report_status(msg, level=StatusLevel.WARNING)
            return
        self.report_status(msg, level=StatusLevel.SUCCESS)
        self._auto_start_tried = False
        self._body.setCurrentIndex(1)
        st = self._refresh_status()
        if st is not None:
            self._drive_lifecycle(st)

    def _on_start(self) -> None:
        self._begin_start(auto=False)

    def _on_stop(self) -> None:
        ok, msg = stop_engine(self.engine_id)
        self._start_pending = False
        self._auto_start_tried = True  # 用户主动停，勿立刻又自动启
        self._embedded_url = ""
        self.report_status(
            msg,
            level=StatusLevel.SUCCESS if ok else StatusLevel.WARNING,
        )
        if ok:
            if self._uses_embed():
                self._host.set_placeholder("服务已停止\n可再次点「启动」")
                if self._view is not None:
                    self._view.setUrl(QUrl("about:blank"))
            else:
                self._browser_surface_opened = False
                self._host.set_placeholder("服务已停止\n可再次点「启动」后打开浏览器")
        self._refresh_status()

    def _on_reload(self) -> None:
        st = read_status(self.engine_id, probe_http=False)
        if self._uses_embed() and st.running and self._view is not None:
            self._view.reload()
            self.report_status("已刷新内嵌页", level=StatusLevel.INFO)
        elif not self._uses_embed() and st.running:
            self._browser_surface_opened = False
            self._apply_browser_surface(st, open_browser=True)
            self.report_status("已再次打开系统浏览器", level=StatusLevel.INFO)
        self._refresh_status()

    def _on_browser(self) -> None:
        st = read_status(self.engine_id, probe_http=False)
        QDesktopServices.openUrl(QUrl(st.url))
        if not self._uses_embed():
            self._browser_surface_opened = True

    def _on_toggle_surface(self) -> None:
        embed_now = self._uses_embed()
        want_embed = not embed_now
        set_prefer_embed(self.engine_id, want_embed)
        self._force_embed_session = False
        self._browser_surface_opened = False
        self._sync_surface_button()
        if want_embed:
            self.report_status("已改为套件内嵌（可能影响外壳流畅度）", level=StatusLevel.INFO)
        else:
            self._schedule_destroy_web_embed()
            self.report_status("已改为系统浏览器表面（外壳隔离）", level=StatusLevel.SUCCESS)
        st = self._refresh_status()
        if st is not None and st.running:
            if want_embed:
                self._ensure_embed(st.url)
            else:
                self._apply_browser_surface(st, open_browser=True)

    def _on_pick_root(self) -> None:
        start = discover_root(self.engine_id)
        path = QFileDialog.getExistingDirectory(
            self,
            "选择引擎根目录",
            str(start or Path.home()),
        )
        if not path:
            return
        save_user_root(self.engine_id, path)
        self.report_status(f"已指定目录：{path}", level=StatusLevel.SUCCESS)
        self._auto_start_tried = False
        st = self._refresh_status()
        if st is not None:
            self._drive_lifecycle(st)

    def _on_open_root(self) -> None:
        root = discover_root(self.engine_id)
        if root is None:
            show_warning(self, "还没有有效安装目录。")
            return
        from services.os_open import open_in_file_manager

        open_in_file_manager(root)

    def _ensure_embed(self, url: str) -> None:
        if not self._uses_embed():
            st = read_status(self.engine_id, probe_http=False)
            self._apply_browser_surface(st, open_browser=True)
            return
        if not _webengine_available():
            self._host.set_placeholder(
                f"当前环境无 WebEngine\n请用「浏览器打开」访问：\n{url}"
            )
            return
        first = self._view is None
        url_changed = False
        if self._view is None:
            from PySide6.QtWebEngineCore import QWebEngineProfile
            from PySide6.QtWebEngineWidgets import QWebEngineView

            from services.storage_paths import module_data_dir
            from services.webengine_host import ToaWebEnginePage, apply_webengine_view_defaults

            if self._profile is None:
                profile_dir = module_data_dir(self.page_id or self.engine_id, create=True) / "browser_profile"
                profile_dir.mkdir(parents=True, exist_ok=True)
                self._profile = QWebEngineProfile(f"toa3_{self.engine_id}", self)
                self._profile.setPersistentStoragePath(str(profile_dir))
                self._profile.setCachePath(str(profile_dir / "cache"))
            self._view = QWebEngineView(self._host)
            page = ToaWebEnginePage(self._profile, self._view)
            self._view.setPage(page)
            apply_webengine_view_defaults(self._view)
            self._view.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._view.loadFinished.connect(self._on_load_finished)
            self._view.installEventFilter(self._f11)
        assert self._view is not None
        target = url.rstrip("/") + "/"
        if self._embedded_url.rstrip("/") != url.rstrip("/"):
            url_changed = True
            self._embedded_url = url
            # 已有 View 时不要 hide（会打断 Comfy 画布交互）
            self._host.set_placeholder("正在加载界面…", hide_view=False)
            self._view.setUrl(QUrl(target))
        self._host.embed_view(self._view, take_focus=first or url_changed)

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            self._status.setText(f"就绪 · 已嵌入 · {self._embedded_url}")
            self.report_status(f"{self.page_title} 已加载", level=StatusLevel.SUCCESS)
        else:
            if self._view is not None and self._embedded_url:
                QTimer.singleShot(
                    1500,
                    lambda: self._view.setUrl(QUrl(self._embedded_url.rstrip("/") + "/"))
                    if self._view is not None
                    else None,
                )
            self.report_status("页面加载未完成，将自动重试…", level=StatusLevel.WARNING)
