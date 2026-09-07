# -*- coding: utf-8 -*-
"""本地 Web 引擎宿主页：未装一键装（进度）→ 已装判启停 → 启动并内嵌。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

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
from widgets import (
    HintLabel,
    MenuButton,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    SectionTitle,
)


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

    def clear_view_ref(self) -> None:
        self._view = None
        self._view_index = -1

    def detach_view(self, *, hide: bool = True) -> None:
        """从 stack 卸下 View（不 delete），供共享池归还 / 引擎 handoff。

        hide=False：引擎互切时保持最后一帧，交给下一页 reparent，避免白闪。
        """
        view = self._view
        self._view = None
        self._view_index = -1
        if not _qt_alive(view):
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

    def set_placeholder(self, text: str, *, hide_view: bool = True) -> None:
        """hide_view=False：已嵌入时只改文案，不切走 WebView（避免打断交互）。"""
        try:
            same = text == self._placeholder.text()
            on_ph = self._stack.currentWidget() is self._placeholder
            view_ok = _qt_alive(self._view)
            if not view_ok:
                self._view = None
            if same and (on_ph or not hide_view):
                return
            if not same:
                self._placeholder.setText(text)
            if hide_view or self._view is None:
                if not on_ph:
                    self._stack.setCurrentWidget(self._placeholder)
                if view_ok and hide_view:
                    try:
                        if self._view.isVisible():
                            self._view.hide()
                    except RuntimeError:
                        self._view = None
                return
            if hide_view:
                try:
                    if not self._view.isVisible():
                        if not on_ph:
                            self._stack.setCurrentWidget(self._placeholder)
                except RuntimeError:
                    self._view = None
                    self._stack.setCurrentWidget(self._placeholder)
            # hide_view=False：保持 WebView，勿抢焦点
        except RuntimeError:
            self._view = None
            try:
                self._placeholder.setText(text)
                self._stack.setCurrentWidget(self._placeholder)
            except Exception:
                pass

    def attach_view(self, view: QWidget) -> None:
        """把 View 挂进栈，但仍显示占位（等 loadFinished 再露出，避免白闪）。"""
        if not _qt_alive(view):
            return
        self._view = view
        if self._stack.indexOf(view) < 0:
            self._view_index = self._stack.addWidget(view)
        try:
            view.hide()
        except RuntimeError:
            self._view = None
            return
        self._stack.setCurrentWidget(self._placeholder)

    def embed_view(self, view: QWidget, *, take_focus: bool = False) -> None:
        """挂载/显示 WebView。take_focus 默认 False，避免抢点击。"""
        if not _qt_alive(view):
            return
        self._view = view
        if self._stack.indexOf(view) < 0:
            self._view_index = self._stack.addWidget(view)
        try:
            view.show()
            self._stack.setCurrentWidget(view)
        except RuntimeError:
            self._view = None
            self._stack.setCurrentWidget(self._placeholder)
            return
        if take_focus:
            try:
                view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                view.setFocus(Qt.FocusReason.MouseFocusReason)
            except Exception:
                pass

    def has_live_view(self) -> bool:
        if not _qt_alive(self._view):
            self._view = None
            return False
        try:
            return self._stack.currentWidget() is self._view and self._view.isVisible()
        except RuntimeError:
            self._view = None
            return False

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
        self._embedded_url = ""
        self._load_fail_retries = 0
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
        self._status_known = False  # 检测完成前不露出操作按钮
        self._last_status_sig: tuple | None = None
        self._last_placeholder_key = ""

        outer = QVBoxLayout(self)
        m = page_content_margins()
        # 压缩页边与标题：工具条最小化，把高度留给引擎画布
        outer.setContentsMargins(max(4, m[0] // 2), 4, max(4, m[2] // 2), 4)
        outer.setSpacing(2)

        spec = get_spec(self.engine_id)
        title = (spec.title if spec else self.page_title) or self.page_title
        # 单行标题，不占副标题行
        self._header = SectionTitle(title)
        self._header.setMaximumHeight(22)
        outer.addWidget(self._header)

        # —— 紧凑工具条：状态 + 主操作 + 刷新 + 更多 ——
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._status = HintLabel("① 检测安装…")
        bar.addWidget(self._status, 1)

        self._action_stack = QStackedWidget()
        self._action_stack.setFixedHeight(32)
        self._btn_start = PrimaryButton("启动")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_start.setMinimumWidth(72)
        self._btn_start.setMinimumHeight(32)
        self._btn_stop = SecondaryButton("停止")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setMinimumWidth(72)
        self._btn_stop.setMinimumHeight(32)
        self._action_stack.addWidget(self._btn_start)
        self._action_stack.addWidget(self._btn_stop)
        bar.addWidget(self._action_stack)

        self._btn_open_bench = PrimaryButton("打开工作台")
        self._btn_open_bench.setMinimumWidth(96)
        self._btn_open_bench.setMinimumHeight(32)
        self._btn_open_bench.setToolTip("在系统浏览器打开引擎工作台")
        self._btn_open_bench.clicked.connect(self._on_open_workbench)
        self._btn_open_bench.hide()
        bar.addWidget(self._btn_open_bench)

        self._btn_reload = SecondaryButton("刷新")
        self._btn_reload.clicked.connect(self._on_reload)
        self._btn_reload.setMinimumWidth(64)
        self._btn_reload.setMinimumHeight(32)
        bar.addWidget(self._btn_reload)

        self._btn_more = MenuButton("更多")
        self._more_menu = QMenu(self)
        self._act_browser = self._more_menu.addAction("浏览器打开", self._on_browser)
        self._act_surface = self._more_menu.addAction("改用内嵌", self._on_toggle_surface)
        self._more_menu.addSeparator()
        self._act_root = self._more_menu.addAction("指定目录", self._on_pick_root)
        self._act_open_root = self._more_menu.addAction("打开目录", self._on_open_root)
        self._btn_more.setMenu(self._more_menu)
        self._btn_more.setMinimumWidth(64)
        self._btn_more.setMinimumHeight(32)
        bar.addWidget(self._btn_more)

        self._toolbar = QWidget()
        self._toolbar.setMinimumHeight(32)
        self._toolbar.setMaximumHeight(40)
        self._toolbar.setLayout(bar)
        self._toolbar.hide()  # 检测完成前不显示
        outer.addWidget(self._toolbar)

        self._body = QStackedWidget()
        # 0 = 安装门；1 = 工作区
        gate = QWidget()
        gate_lay = QVBoxLayout(gate)
        gate_lay.setContentsMargins(24, 16, 24, 16)
        gate_lay.setSpacing(12)
        gate_lay.addStretch(1)
        self._gate_title = HintLabel("① 正在检测安装…")
        self._gate_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gate_lay.addWidget(self._gate_title)
        self._gate_body = HintLabel("请稍候，确认状态后再给出下一步操作。")
        self._gate_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gate_body.setWordWrap(True)
        gate_lay.addWidget(self._gate_body)

        prog_wrap = QWidget()
        prog_wrap.setMaximumWidth(420)
        prog_lay = QVBoxLayout(prog_wrap)
        prog_lay.setContentsMargins(0, 8, 0, 8)
        prog_lay.setSpacing(6)
        self._progress = ProgressBar()
        self._progress.setRange(0, 0)  # 不确定进度（检测中）
        self._progress.setTextVisible(False)
        self._progress.setMinimumHeight(10)
        self._progress.setMaximumHeight(10)
        prog_lay.addWidget(self._progress)
        self._progress_label = HintLabel("检测安装与端口…")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_lay.addWidget(self._progress_label)
        gate_lay.addWidget(prog_wrap, 0, Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self._btn_install = PrimaryButton("一键安装")
        self._btn_install.clicked.connect(self._on_one_click_install)
        self._btn_install.hide()
        row.addWidget(self._btn_install)
        self._btn_gate_pick = SecondaryButton("指定目录")
        self._btn_gate_pick.clicked.connect(self._on_pick_root)
        self._btn_gate_pick.hide()
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
        self._set_detecting_ui(True)
    def uses_webengine_embed(self) -> bool:
        """壳层切页：本页租用了共享 WebEngine，即 web-heavy。"""
        if self._view is not None:
            return True
        try:
            from services.shared_local_webengine import current_owner_id

            return current_owner_id() == (self.page_id or self.engine_id)
        except Exception:
            return False

    def _uses_embed(self) -> bool:
        """以 prefer_embed（含用户「更多」写入）为准，保证内嵌/浏览器可来回切换。"""
        return prefer_embed(self.engine_id)

    def _set_detecting_ui(self, detecting: bool) -> None:
        self._status_known = not detecting
        if detecting:
            self._toolbar.hide()
            self._body.setCurrentIndex(0)
            self._gate_title.setText("① 正在检测安装…")
            self._gate_body.setText("请稍候，确认状态后再给出下一步操作。")
            self._progress.show()
            self._progress.setRange(0, 0)
            self._progress_label.setText("检测安装与端口…")
            self._progress_label.show()
            self._btn_install.hide()
            self._btn_gate_pick.hide()
            self._status.setText("① 检测安装…")
        else:
            self._toolbar.show()

    def _sync_surface_button(self) -> None:
        if self._uses_embed():
            self._act_surface.setText(
                "改用浏览器（推荐）" if self.engine_id == "comfyui_web" else "改用浏览器"
            )
        else:
            self._act_surface.setText(
                "改用内嵌（不推荐）" if self.engine_id == "comfyui_web" else "改用内嵌"
            )
        # 浏览器表面：露出大号「打开工作台」，避免只会藏在更多菜单里
        bench = getattr(self, "_btn_open_bench", None)
        if bench is not None:
            show_bench = (not self._uses_embed()) and self._status_known
            bench.setVisible(show_bench)

    def _set_action_running(self, running: bool) -> None:
        self._action_stack.setCurrentIndex(1 if running else 0)
        self._btn_start.setEnabled(not running and self._status_known)
        self._btn_stop.setEnabled(running and self._status_known)

    def keep_web_embed_on_leave(self) -> bool:
        """壳层已改为跨模块强制拆 View；此标志仅作文档/兼容，不再阻止 purge。"""
        return False

    def soft_leave(self) -> None:
        """壳层切走：只停轮询。共享 View 由壳层在切走主栈后再 purge/归还。

        禁止在此归还：此时本页仍可能是当前可见 Guest， rip View 会 GPU 闪退。
        """
        self._visit_gen += 1
        self._poll.stop()
        self._auto_start_tried = False

    def on_enter(self) -> None:
        self.report_status(self.page_title, level=StatusLevel.INFO)
        self._visit_gen += 1
        visit = self._visit_gen
        self._sync_surface_button()

        # 热回进：已有内嵌 / 已知状态 → 不走「检测门」整页闪
        sticky = self._uses_embed() and self._host.has_live_view()
        if sticky or (self._status_known and self._body.currentIndex() == 1):
            self._toolbar.show()
            self._body.setCurrentIndex(1)
            delay = 0 if sticky else 40
            QTimer.singleShot(delay, lambda v=visit: self._on_enter_deferred(v, soft=True))
            return

        # 冷进：先轻量读状态，已运行则直接工作区，避免门页→工作区大闪
        self._auto_start_tried = False
        try:
            st0 = read_status(self.engine_id, probe_http=False)
        except Exception:
            st0 = None
        if st0 is not None and st0.installed:
            self._status_known = True
            self._toolbar.show()
            self._body.setCurrentIndex(1)
            if st0.running:
                hint = (
                    "正在连接已运行的服务…"
                    if self._uses_embed()
                    else "服务已在运行 · 准备控制台…"
                )
                self._host.set_placeholder(hint, hide_view=False)
            else:
                self._host.set_placeholder("已安装 · 正在确认…", hide_view=True)
            delay = 40 if not self._uses_embed() else 80
            QTimer.singleShot(delay, lambda v=visit: self._on_enter_deferred(v, soft=False))
            return

        self._set_detecting_ui(True)
        delay = 40 if not self._uses_embed() else 120
        QTimer.singleShot(delay, lambda v=visit: self._on_enter_deferred(v, soft=False))

    def _on_enter_deferred(self, visit: int | None = None, *, soft: bool = False) -> None:
        if visit is not None and visit != self._visit_gen:
            return
        if self.window() is not None and getattr(self.window(), "_current_id", None) != self.page_id:
            return
        st = self._refresh_status(force=not soft)
        self._poll.start()
        if st is None:
            return
        if soft and st.running:
            # 热回进：浏览器表面不重复弹窗；内嵌已在则只稳状态
            if not self._uses_embed():
                self._apply_browser_surface(st, open_browser=False)
            elif self._host.has_live_view():
                return
            else:
                self._drive_lifecycle(st)
            return
        self._drive_lifecycle(st)

    def on_leave(self) -> None:
        self._visit_gen += 1
        self._poll.stop()
        self._auto_start_tried = False
        # 完整离开仍可拆 View（非 soft 路径）；浏览器表面无 View
        if self.uses_webengine_embed() and not self.keep_web_embed_on_leave():
            self._schedule_destroy_web_embed()
        spec = get_spec(self.engine_id)
        if spec and spec.stop_on_leave:
            stop_engine(self.engine_id)

    def _handoff_web_embed(self) -> None:
        """引擎↔引擎：只清本页引用，共享 View 留给下一页 acquire（不 hide/Stop）。"""
        self._view = None
        self._embedded_url = ""
        self._load_fail_retries = 0
        try:
            self._host.detach_view(hide=False)
        except Exception:
            try:
                self._host.clear_view_ref()
            except Exception:
                pass

    def _schedule_destroy_web_embed(self) -> None:
        """归还共享 WebEngine（park 到 holder；离引擎域由壳层 shutdown destroy）。"""
        owner = self.page_id or self.engine_id
        self._view = None
        self._embedded_url = ""
        self._load_fail_retries = 0
        try:
            self._host.detach_view(hide=True)
        except Exception:
            try:
                self._host.clear_view_ref()
            except Exception:
                pass
        try:
            from services.shared_local_webengine import release

            release(owner, destroy=False, park=True)
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
        if self._body.currentIndex() != 1:
            self._body.setCurrentIndex(1)
        if st.running:
            if self._uses_embed():
                if not self._host.has_live_view():
                    self.report_status(f"{self.page_title} · 加载中", level=StatusLevel.INFO)
                # 已有 View 时 _ensure_embed 由 _refresh_status 触发
                if self._view is None or self._embedded_url.rstrip("/") != (st.url or "").rstrip("/"):
                    self._ensure_embed(st.url)
            else:
                # 已运行：控制台稳态；不自动弹浏览器（避免每次进页「跳出」）
                self._apply_browser_surface(st, open_browser=False)
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
        """浏览器表面：主窗只做启停控制台；默认不反复弹系统浏览器。"""
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
        key = f"browser|{url}|{int(self._browser_surface_opened)}"
        if key == self._last_placeholder_key and self._body.currentIndex() == 1:
            return
        self._last_placeholder_key = key
        opened = (
            "已打开系统浏览器 · 也可再点「打开工作台」"
            if self._browser_surface_opened
            else "服务已就绪 · 点「打开工作台」进入（推荐，下拉可选）"
        )
        extra = ""
        if self.engine_id == "comfyui_web":
            extra = (
                "\n\nComfy 默认外置浏览器：套件内嵌时模型下拉常点不中。"
                "\n「更多」可改内嵌/改回浏览器，两边都能切。"
            )
        self._host.set_placeholder(
            f"{opened}\n{url}\n\n"
            "外壳负责启动 / 停止 / 指定目录；节点与模型在浏览器中操作。"
            f"{extra}",
            hide_view=True,
        )
        self._sync_surface_button()

    def _show_gate(self, *, installing: bool) -> None:
        self._body.setCurrentIndex(0)
        self._toolbar.hide()
        spec = get_spec(self.engine_id)
        title = (spec.title if spec else self.page_title) or self.page_title
        if installing:
            self._gate_title.setText(f"② 正在安装 {title}")
            self._status.setText("② 安装进行中…")
            self._btn_install.hide()
            self._btn_gate_pick.hide()
            self._progress.show()
            self._progress.setRange(0, 100)
            self._progress.setValue(max(1, self._progress.value()))
            self._progress_label.setText("下载与安装…")
            self._progress_label.show()
            return
        # 未安装：检测已结束，再给出下一步按钮
        self._set_detecting_ui(False)
        self._toolbar.hide()
        self._progress.hide()
        self._progress_label.hide()
        self._gate_title.setText(f"② 未检测到安装 · {title}")
        self._status.setText("② 未安装 · 请选择下一步")
        self._set_action_running(False)
        self._btn_start.setEnabled(False)
        if can_one_click_install(self.engine_id):
            target = ""
            if spec and spec.default_roots:
                target = str(spec.default_roots[0])
            self._gate_body.setText(
                f"下一步：一键安装到\n{target or '默认目录'}\n完成后将自动启动。"
            )
            self._btn_install.setEnabled(True)
            self._btn_install.setText("一键安装")
            self._btn_install.show()
            self._btn_gate_pick.show()
        else:
            hint = (spec.install_hint if spec else "") or "请指定已安装的引擎根目录。"
            self._gate_body.setText(f"下一步：{hint}")
            self._btn_install.hide()
            self._btn_gate_pick.show()

    def _begin_start(self, *, auto: bool = False) -> None:
        if self._start_thread is not None or self._install_busy:
            return
        self._start_pending = True
        self._start_was_auto = auto
        self._body.setCurrentIndex(1)
        self._toolbar.show()
        self._set_action_running(True)
        self._btn_stop.setToolTip("停止启动中的进程")
        self._btn_reload.setEnabled(True)
        has_live = self._host.has_live_view() if self._uses_embed() else False
        ready_hint = (
            "③ 正在启动服务…\n就绪后自动嵌入"
            if self._uses_embed()
            else "③ 正在启动服务…\n就绪后将在系统浏览器打开"
        )
        self._host.set_placeholder(
            ready_hint
            + ("\n（大模型引擎首次启动可能需数分钟）" if self.engine_id == "comfyui_web" else ""),
            hide_view=not has_live,
        )
        self._status.setText("③ 启动中…")
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
        QTimer.singleShot(200, self._after_start_ok)

    def _after_start_ok(self) -> None:
        st = self._refresh_status(force=True)
        if st is None:
            return
        if st.running and not self._uses_embed():
            # 刚启动成功：打开一次工作台；之后进页不再自动弹
            self._apply_browser_surface(st, open_browser=True)
        elif st.running and self._uses_embed():
            self._ensure_embed(st.url)

    def _destroy_web_embed(self) -> None:
        """兼容旧调用：改为延迟销毁。"""
        self._schedule_destroy_web_embed()

    def _refresh_status(self, *, force: bool = False):
        st = read_status(self.engine_id, probe_http=False)
        root_s = str(st.root) if st.root else "（未配置）"
        starting = owned_process(self.engine_id) is not None and not st.running
        busy = self._install_busy or self._start_thread is not None
        # 已嵌入时端口短抖 → 勿当成未运行去 hide View
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
                self._set_action_running(True)
                self._act_browser.setEnabled(True)
                return st
        else:
            self._port_miss_ticks = 0

        if not st.installed and not self._install_busy:
            self._show_gate(installing=False)
            self._last_status_sig = None
            return st

        sig = (
            st.installed,
            st.running,
            starting,
            self._start_pending,
            busy,
            root_s,
            st.detail,
            self._uses_embed(),
            bool(self._host.has_live_view()),
            self._embedded_url,
        )
        if not force and sig == self._last_status_sig:
            return st
        self._last_status_sig = sig

        # 已安装：检测结束，露出紧凑工具条
        self._status_known = True
        if not self._toolbar.isVisible():
            self._toolbar.show()
        if self._progress.isVisible():
            self._progress.hide()
        if self._progress_label.isVisible():
            self._progress_label.hide()
        phase = "④ 运行中" if st.running else ("③ 启动中" if (starting or self._start_pending) else "② 已安装")
        status_text = f"{phase} · {st.detail} · {root_s}"
        if self._status.text() != status_text:
            self._status.setText(status_text)
        run_like = bool(st.running or starting or self._start_pending)
        self._set_action_running(run_like)
        if not run_like:
            self._btn_start.setEnabled(st.installed and not busy)
        self._btn_reload.setEnabled(not self._install_busy)
        self._btn_more.setEnabled(not self._install_busy)
        self._act_browser.setEnabled(bool(st.running and st.url))
        self._act_root.setEnabled(not busy)
        self._act_open_root.setEnabled(bool(st.root))
        self._sync_surface_button()

        if st.installed and self._body.currentIndex() != 1:
            self._body.setCurrentIndex(1)

        if st.running:
            self._start_pending = False
            self._port_miss_ticks = 0
            self._poll.setInterval(4000)
            if not self._uses_embed():
                # 轮询只稳控制台，不反复弹浏览器、不反复刷占位
                self._apply_browser_surface(st, open_browser=False)
                return st
            if self._view is None or self._embedded_url.rstrip("/") != st.url.rstrip("/"):
                self._ensure_embed(st.url)
            elif not self._host.has_live_view():
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
                    self._set_action_running(False)
                    return st
            else:
                self._start_fail_ticks = 0
            has_live = self._host.has_live_view()
            self._host.set_placeholder(
                "③ 正在启动…\n等待端口打开后自动加载"
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
                    "② 已安装 · 启动未就绪，可点「启动」重试", hide_view=True
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
        self._progress.setRange(0, 100)
        self._progress.setValue(max(0, min(100, int(pct))))
        self._progress_label.show()
        self._progress_label.setText(f"{pct}% · {msg}")
        self._gate_body.setText(msg)
        self._status.setText(f"② 安装中 {pct}%")

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
        """停服平稳降落：先占位进度 → 停进程 → 收 WebView → 再刷新状态。"""
        self._start_pending = False
        self._auto_start_tried = True
        self._last_placeholder_key = ""
        self._last_status_sig = None
        self._status.setText("⑤ 正在停止…")
        self._set_action_running(True)
        self._btn_stop.setEnabled(False)
        self._host.set_placeholder("⑤ 正在停止服务…\n请稍候", hide_view=True)
        self.report_status("正在停止服务…", level=StatusLevel.INFO)
        QTimer.singleShot(0, self._finish_stop)

    def _finish_stop(self) -> None:
        ok, msg = stop_engine(self.engine_id)
        self._browser_surface_opened = False
        self._embedded_url = ""
        # 优雅收起内嵌：不 about:blank 硬切（易闪），直接延后销毁
        if _qt_alive(self._view):
            self._schedule_destroy_web_embed()
        self._host.set_placeholder(
            "⑥ 服务已停止\n可点「启动」再次运行"
            if ok
            else f"停止未完成\n{msg}",
            hide_view=True,
        )
        self.report_status(
            msg,
            level=StatusLevel.SUCCESS if ok else StatusLevel.WARNING,
        )
        self._refresh_status(force=True)

    def _on_reload(self) -> None:
        st = read_status(self.engine_id, probe_http=False)
        if self._uses_embed() and st.running and _qt_alive(self._view):
            try:
                self._view.reload()
                self.report_status("已刷新内嵌页", level=StatusLevel.INFO)
            except RuntimeError:
                self._view = None
                self._ensure_embed(st.url)
        elif not self._uses_embed() and st.running:
            self._last_placeholder_key = ""
            self._browser_surface_opened = False
            self._apply_browser_surface(st, open_browser=True)
            self.report_status("已再次打开系统浏览器", level=StatusLevel.INFO)
        self._refresh_status(force=True)

    def _on_browser(self) -> None:
        self._on_open_workbench()

    def _on_open_workbench(self) -> None:
        st = read_status(self.engine_id, probe_http=False)
        url = (st.url if st is not None else "") or ""
        if not url:
            spec = get_spec(self.engine_id)
            url = spec.web_url() if spec else ""
        if not url:
            show_warning(self, "服务尚未就绪，请先启动。")
            return
        QDesktopServices.openUrl(QUrl(url))
        self._browser_surface_opened = True
        self._last_placeholder_key = ""
        self._apply_browser_surface(st, open_browser=False)
        self.report_status(f"已打开工作台 · {self.page_title}", level=StatusLevel.SUCCESS)

    def _on_toggle_surface(self) -> None:
        embed_now = self._uses_embed()
        want_embed = not embed_now
        if want_embed and self.engine_id == "comfyui_web":
            from core.user_messages import ask_confirm

            if not ask_confirm(
                self,
                "Comfy 内嵌时模型下拉常点不动，并可能拖垮外壳。\n"
                "推荐继续用系统浏览器。仍要改用内嵌吗？",
            ):
                return
        # 写入用户配置；下次/当次都以 prefer_embed 为准（可来回切换）
        set_prefer_embed(self.engine_id, want_embed)
        self._force_embed_session = False
        self._browser_surface_opened = False
        self._last_placeholder_key = ""
        self._last_status_sig = None
        self._sync_surface_button()
        if want_embed:
            self.report_status("已改为套件内嵌", level=StatusLevel.WARNING)
            if self._view is not None:
                self._schedule_destroy_web_embed()
        else:
            if self._view is not None:
                self._schedule_destroy_web_embed()
            self.report_status("已改为系统浏览器（外壳隔离）", level=StatusLevel.SUCCESS)
        # 下一拍再挂载（共享 View 归还后即可复用）
        QTimer.singleShot(50, lambda: self._after_surface_toggle(want_embed))

    def _after_surface_toggle(self, want_embed: bool) -> None:
        st = self._refresh_status(force=True)
        if st is None or not st.running:
            return
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
            self._apply_browser_surface(st, open_browser=False)
            return
        if not _webengine_available():
            self._host.set_placeholder(
                f"当前环境无 WebEngine\n请用「打开工作台」访问：\n{url}"
            )
            return
        from services.shared_local_webengine import acquire, current_owner_id, current_url

        owner = self.page_id or self.engine_id
        target = (url or "").rstrip("/")
        url_changed = self._embedded_url.rstrip("/") != target
        # 热稳态：已是本租户 + 同 URL + 正在显示 → 禁止再 acquire/占位（根治使用中闪烁）
        if (
            _qt_alive(self._view)
            and self._host.has_live_view()
            and current_owner_id() == owner
            and current_url().rstrip("/") == target
            and not url_changed
        ):
            return

        self._embedded_url = url or ""
        view = acquire(
            owner,
            url or "",
            host_ref=self,
            on_load_finished=self._on_load_finished,
            event_filter=self._f11,
        )
        if view is None:
            self._host.set_placeholder("无法创建共享 WebEngine")
            return
        self._view = view
        # 接手共享页时清掉 Harness 外链限制，避免 Draw/OpenPencil 导航被挡
        try:
            from services.webengine_host import ToaWebEnginePage

            page = view.page()
            if isinstance(page, ToaWebEnginePage):
                page.set_accept_nav(None)
        except Exception:
            pass
        # 以 View 实际 URL 为准：acquire 已改 _current_url，但画面可能仍卡在旧引擎
        painted = ""
        try:
            painted = (view.url().toString() or "").rstrip("/")
        except Exception:
            painted = ""
        still_foreign = bool(target) and painted and not painted.startswith(target)
        if url_changed or still_foreign or not self._host.has_live_view():
            # 换引擎：占位至 loadFinished，禁止新 Host 条下露出旧站
            self._host.set_placeholder("正在切换引擎界面…", hide_view=True)
            self._host.attach_view(view)
            return
        # 同 URL 热回进
        self._host.embed_view(view, take_focus=False)

    def _on_load_finished(self, ok: bool) -> None:
        try:
            from services.webengine_host import ToaWebEnginePage

            page = self._view.page() if _qt_alive(self._view) else None
            if isinstance(page, ToaWebEnginePage):
                page.end_forced_navigation()
        except Exception:
            pass
        if ok:
            self._load_fail_retries = 0
            if self._view is not None:
                self._host.embed_view(self._view, take_focus=False)
            self._status.setText(f"就绪 · 已嵌入 · {self._embedded_url}")
            self.report_status(f"{self.page_title} 已加载", level=StatusLevel.SUCCESS)
            return
        # SPA / 子资源失败也会打到这里：已在显示则勿重载（重载=整页闪）
        if self._host.has_live_view():
            return
        retries = int(getattr(self, "_load_fail_retries", 0) or 0)
        if retries >= 1 or not self._view or not self._embedded_url:
            self.report_status("页面加载未完成，可点「刷新」重试", level=StatusLevel.WARNING)
            return
        self._load_fail_retries = retries + 1
        QTimer.singleShot(
            1200,
            lambda: self._view.setUrl(QUrl(self._embedded_url.rstrip("/") + "/"))
            if _qt_alive(self._view)
            else None,
        )
        self.report_status("页面加载未完成，将自动重试…", level=StatusLevel.WARNING)
