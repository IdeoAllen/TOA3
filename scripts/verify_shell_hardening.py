#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壳层固若金汤自动化验收（Agent 自跑，不依赖主理人手测）。

覆盖方案 32 / Wave A–C 可机器验证项：
  - 源码铁律（500ms enter、即刻 purge、already-deleted、Harness _qt_alive、工具条 32）
  - ComfyUI 侧栏隐藏
  - error_handler 降级
  - 离屏壳：Loading、系统域进设置、狂切不崩、web-heavy 异步 enter_delay

用法：
  python scripts/verify_shell_hardening.py
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 无显示环境也能跑 Qt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)
    print(f"  FAIL  {msg}")


def _pass(msg: str) -> None:
    print(f"  PASS  {msg}")


def check_static_source() -> list[str]:
    print("\n[1] 源码铁律")
    errors: list[str] = []
    shell = (ROOT / "app" / "shell.py").read_text(encoding="utf-8")
    err = (ROOT / "core" / "error_handler.py").read_text(encoding="utf-8")
    harness = (ROOT / "modules" / "harness_agent" / "harness_agent_page.py").read_text(
        encoding="utf-8"
    )
    local_web = (ROOT / "modules" / "local_web_host" / "local_web_host_page.py").read_text(
        encoding="utf-8"
    )
    app_yml = (ROOT / "config" / "app.yml").read_text(encoding="utf-8")

    if "class _LoadingGuestPage" not in shell:
        _fail(errors, "缺少 _LoadingGuestPage")
    else:
        _pass("_LoadingGuestPage")

    if "ScrollBarAsNeeded" not in shell:
        _fail(errors, "侧栏未使用 ScrollBarAsNeeded")
    else:
        _pass("ScrollBarAsNeeded")

    # 缓存路径与异步路径都要能延迟 enter（引擎→业务用 1200）
    if (
        "enter_delay = 1200" not in shell
        and "enter_delay = 900" not in shell
        and "enter_delay = 500" not in shell
        and "500 if web_heavy" not in shell
    ):
        _fail(errors, "web-heavy enter_delay 未配置")
    else:
        _pass("enter_delay web-heavy（含引擎→业务加长）")

    async_sig = shell.split("def _async_ensure_page", 1)
    if len(async_sig) < 2 or "enter_delay" not in async_sig[1][:500]:
        _fail(errors, "首次异步建页未接收 enter_delay")
    else:
        _pass("异步建页携带 enter_delay")

    if "already deleted" not in err:
        _fail(errors, "error_handler 未处理 already deleted")
    else:
        _pass("error_handler already deleted")

    if "def _qt_alive" not in harness:
        _fail(errors, "Harness 缺少 _qt_alive")
    else:
        _pass("Harness _qt_alive")

    if "setMinimumHeight(32)" not in local_web:
        _fail(errors, "local_web 工具条未设 MinimumHeight(32)")
    else:
        _pass("local_web toolbar minH=32")

    if "shared_local_webengine" not in local_web or "acquire(" not in local_web:
        _fail(errors, "LocalWebHost 未改用 shared_local_webengine.acquire")
    else:
        _pass("LocalWebHost 共用 WebEngine")

    shared = ROOT / "services" / "shared_local_webengine.py"
    if not shared.is_file():
        _fail(errors, "缺少 services/shared_local_webengine.py")
    else:
        _pass("shared_local_webengine 存在")
        shared_txt = shared.read_text(encoding="utf-8")
        if "park: bool" not in shared_txt and "park=False" not in shared_txt:
            _fail(errors, "shared_local_webengine 缺少 handoff park 参数")
        else:
            _pass("shared_webengine handoff（park）")
        if "_park_view_quiet" not in shared_txt or "LifecycleState.Active" not in shared_txt:
            _fail(errors, "shared_local_webengine 缺少安静停靠 / Lifecycle Active 回嵌")
        else:
            _pass("shared_webengine 安静停靠 + 回嵌唤醒")
        if "_park_view_awake" in shared_txt:
            _fail(errors, "shared_local_webengine 仍含离屏清醒停靠（会抢合成闪烁）")
        prewarm = (ROOT / "services" / "webengine_prewarm.py").read_text(encoding="utf-8")
        if "QWebEngineView(holder)" in prewarm and "已禁用" not in prewarm:
            _fail(errors, "webengine_prewarm 仍创建第二份 View")
        else:
            _pass("webengine_prewarm 已禁用双 View")

    if "_handoff_engine_embed" not in shell or "enter_delay = 80" not in shell:
        _fail(errors, "shell 缺少引擎↔引擎 soft handoff（80ms）")
    else:
        _pass("shell 引擎↔引擎 soft handoff")

    if "_handoff_web_embed" not in harness or "_handoff_web_embed" not in local_web:
        _fail(errors, "Harness/LocalWebHost 缺少 _handoff_web_embed")
    else:
        _pass("引擎页 handoff_web_embed")

    host_py = (ROOT / "services" / "webengine_host.py").read_text(encoding="utf-8")
    if "begin_forced_navigation" not in host_py or "javaScriptConfirm" not in host_py:
        _fail(errors, "webengine_host 缺少强制导航/离开确认放行")
    else:
        _pass("强制导航放行 beforeunload")
    if "painted_url" not in (ROOT / "services" / "shared_local_webengine.py").read_text(
        encoding="utf-8"
    ):
        _fail(errors, "shared_local_webengine 缺少 painted_url")
    else:
        _pass("painted_url 可断言串引擎")

    engines_yml = (ROOT / "config" / "local_web_engines.yml").read_text(encoding="utf-8")
    for eid, want in (("open_pencil:", True), ("drawio_web:", True)):
        # 粗检：该引擎块内 prefer_embed: true
        if eid not in engines_yml:
            _fail(errors, f"engines.yml 缺 {eid}")
            continue
        chunk = engines_yml.split(eid, 1)[1][:800]
        if "prefer_embed: true" not in chunk:
            _fail(errors, f"{eid} 默认应为 prefer_embed: true（共用内嵌）")
        else:
            _pass(f"{eid} prefer_embed true")

    # comfyui_web 块 show: false
    block = ""
    if "id: comfyui_web" in app_yml:
        idx = app_yml.index("id: comfyui_web")
        block = app_yml[idx : idx + 280]
    if "show: false" not in block:
        _fail(errors, "comfyui_web 侧栏未隐藏 (show: false)")
    else:
        _pass("comfyui_web show: false")

    if "processEvents" in shell and "禁止" not in "".join(
        line for line in shell.splitlines() if "processEvents" in line
    ):
        # 允许注释里出现；不允许 navigate 路径调用
        for line in shell.splitlines():
            s = line.strip()
            if "processEvents" in s and not s.startswith("#") and "禁止" not in s:
                if "QApplication.processEvents" in s or ".processEvents(" in s:
                    _fail(errors, f"shell 切页路径疑似 processEvents: {s}")
                    break
        else:
            _pass("shell 无切页 processEvents 调用")
    else:
        _pass("shell 无切页 processEvents 调用")

    return errors


def check_error_hook() -> list[str]:
    print("\n[2] error_handler 降级")
    errors: list[str] = []
    from core import error_handler as eh

    class _Buf(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    buf = _Buf()
    eh.logger.addHandler(buf)
    try:
        eh.install_qt_exception_hook()
        hook = sys.excepthook

        # SystemExit 不得传播
        try:
            hook(SystemExit, SystemExit(1), None)
        except SystemExit:
            _fail(errors, "excepthook 未拦截 SystemExit")
        else:
            _pass("拦截 SystemExit")

        buf.records.clear()
        hook(
            RuntimeError,
            RuntimeError("Internal C++ object (PySide6.QtWebEngineWidgets.QWebEngineView) already deleted."),
            None,
        )
        warns = [r for r in buf.records if r.levelno == logging.WARNING]
        crits = [r for r in buf.records if r.levelno >= logging.CRITICAL]
        if not warns:
            _fail(errors, "already deleted 未记 warning")
        elif crits:
            _fail(errors, "already deleted 仍记 critical")
        else:
            _pass("already deleted → warning")

        buf.records.clear()
        hook(ValueError, ValueError("boom"), None)
        if not any(r.levelno >= logging.CRITICAL for r in buf.records):
            _fail(errors, "普通未捕获异常应 critical")
        else:
            _pass("普通异常仍 critical")
    except Exception as e:
        _fail(errors, f"error_hook 测试异常: {e}")
    finally:
        eh.logger.removeHandler(buf)
    return errors


def check_menu_visibility() -> list[str]:
    print("\n[3] 菜单可见性")
    errors: list[str] = []
    from services.config_service import load_config
    from services.menu_registry import all_menu_items, grouped_menu_items, show_in_sidebar

    load_config()
    items = {str(i.get("id")): i for i in all_menu_items()}
    comfy = items.get("comfyui_web")
    if comfy is None:
        _fail(errors, "菜单缺少 comfyui_web 登记（应保留代码入口）")
    elif show_in_sidebar(comfy):
        _fail(errors, "comfyui_web 仍出现在侧栏可见逻辑")
    else:
        _pass("comfyui_web 不进侧栏")

    visible_engines = []
    for gid, _gl, group_items in grouped_menu_items(licensed_only=False, migrated_only=True):
        if gid != "engines":
            continue
        for it in group_items:
            mid = str(it.get("id") or "")
            if mid and show_in_sidebar(it) and bool(it.get("show", True)):
                visible_engines.append(mid)
    if "comfyui_web" in visible_engines:
        _fail(errors, f"engines 可见列表仍含 comfyui_web: {visible_engines}")
    else:
        _pass(f"engines 可见={visible_engines}")

    for must in ("system_settings", "home", "media_studio"):
        if must not in items:
            _fail(errors, f"缺少必备菜单 {must}")
        else:
            _pass(f"必备菜单 {must}")
    return errors


def check_shell_runtime() -> list[str]:
    print("\n[4] 离屏壳导航")
    errors: list[str] = []
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app.app_state import AppState
    from app.bootstrap import bootstrap_runtime
    from app.logging_setup import setup_logging
    from app.shell import MainShell, _LoadingGuestPage
    from core.error_handler import install_qt_exception_hook
    from services.config_service import load_config

    setup_logging()
    bootstrap_runtime()
    cfg = load_config()
    AppState.get().config = cfg
    AppState.get().set_user("verify_shell", "壳层自测", role="admin")
    install_qt_exception_hook()

    app = QApplication.instance() or QApplication([])

    shell = None
    try:
        shell = MainShell(defer_startup=True)
        shell.show()
        app.processEvents()

        # G2：未缓存模块 navigate → LoadingGuest
        # 选一个通常未缓存的轻量页
        mid = "pomodoro"
        if mid in shell._pages:
            del shell._pages[mid]
        shell.navigate(mid)
        app.processEvents()
        cur = shell._stack.currentWidget()
        if isinstance(cur, _LoadingGuestPage) or mid in shell._loading_guests:
            _pass("首次打开出现 Loading")
        elif mid in shell._pages and shell._stack.currentWidget() is shell._pages.get(mid):
            # 同步极快建完也可接受
            _pass("首次打开当帧切真页（建页极快）")
        else:
            _fail(errors, f"首次打开未进 Loading/真页 mid={mid} cur={type(cur)}")

        # 等异步建页完成
        for _ in range(50):
            app.processEvents()
            if mid in shell._pages and not isinstance(
                shell._stack.currentWidget(), _LoadingGuestPage
            ):
                break
            QTimer.singleShot(20, lambda: None)
            app.processEvents()
            from time import sleep

            sleep(0.02)

        # G4：系统域 → system_settings
        shell.select_domain("system")
        for _ in range(30):
            app.processEvents()
            from time import sleep

            sleep(0.02)
            if shell._current_id == "system_settings":
                break
        if shell._current_id != "system_settings":
            _fail(errors, f"系统域未进设置，当前={shell._current_id!r}")
        else:
            _pass("select_domain(system) → system_settings")

        # G3：狂切不崩 + SystemExit 隔离
        targets = [
            "home",
            "clipboard_history",
            "drawio_web",
            "system_settings",
            "media_studio",
            "home",
            "system_settings",
        ]
        crashed = False
        for t in targets * 3:
            try:
                shell.navigate(t)
                app.processEvents()
            except SystemExit:
                crashed = True
                _fail(errors, "navigate 冒出 SystemExit")
                break
            except Exception as e:
                crashed = True
                _fail(errors, f"狂切异常: {e}")
                break
        if not crashed:
            _pass("狂切菜单进程仍在（无未捕获异常）")

        # 注入 web-heavy 离开 → 异步首次建页应带 360 delay
        class _FakeHeavy:
            page_id = "drawio_web"
            page_title = "fake"

            def uses_webengine_embed(self) -> bool:
                return True

            def keep_web_embed_on_leave(self) -> bool:
                return False

            def soft_leave(self) -> None:
                return None

            def on_leave(self) -> None:
                return None

            def _destroy_web_embed(self) -> None:
                return None

        # 清掉目标缓存，强制走 Loading 路径
        probe_mid = "quick_notepad"
        shell._pages.pop(probe_mid, None)
        shell._pages["drawio_web"] = _FakeHeavy()  # type: ignore[assignment]
        shell._current_id = "drawio_web"

        delays: list[int] = []
        orig = QTimer.singleShot

        def capturing_shot(ms, slot):  # noqa: ANN001
            delays.append(int(ms))
            # 窥探 lambda 默认参数里的 enter_delay
            defaults = getattr(slot, "__defaults__", None) or ()
            for d in defaults:
                if isinstance(d, int) and d in (0, 80, 360, 450, 500, 900, 1200):
                    delays.append(d)
            return orig(ms, slot)

        QTimer.singleShot = staticmethod(capturing_shot)  # type: ignore[assignment]
        try:
            shell.navigate(probe_mid)
            app.processEvents()
        finally:
            QTimer.singleShot = orig  # type: ignore[assignment]

        if any(d in delays for d in (1200, 900, 500, 450, 360, 80)):
            _pass("web-heavy → 首次建页路径含 enter_delay")
        else:
            _fail(errors, f"web-heavy 首次路径未见 enter_delay（recorded={delays[:20]}）")

        # 侧栏不应有 comfy 按钮
        if "comfyui_web" in shell._nav_buttons:
            # 可能其它域；切到 engines 再查
            shell.select_domain("engines")
            for _ in range(20):
                app.processEvents()
            if "comfyui_web" in shell._nav_buttons and shell._nav_buttons[
                "comfyui_web"
            ].isVisible():
                _fail(errors, "侧栏仍可见 comfyui_web 按钮")
            else:
                _pass("侧栏无可见 comfyui_web")
        else:
            _pass("侧栏无 comfyui_web 按钮")

    except Exception as e:
        _fail(errors, f"壳运行时异常: {e}\n{traceback.format_exc()}")
    finally:
        if shell is not None:
            try:
                shell.close()
                shell.deleteLater()
            except Exception:
                pass
        app.processEvents()
    return errors


def check_widget_heights() -> list[str]:
    print("\n[5] 引擎 Host 条高度")
    errors: list[str] = []
    from PySide6.QtWidgets import QApplication

    from app.module_loader import create_page
    from services.menu_registry import all_menu_items

    app = QApplication.instance() or QApplication([])
    items = {str(i.get("id")): i for i in all_menu_items()}
    for mid in ("drawio_web", "open_pencil"):
        item = items.get(mid)
        if not item:
            _fail(errors, f"无菜单项 {mid}")
            continue
        try:
            page = create_page(mid, item)
            btn = getattr(page, "_btn_reload", None) or getattr(page, "_btn_start", None)
            if btn is None:
                _fail(errors, f"{mid} 无工具条按钮")
                continue
            mh = int(btn.minimumHeight())
            if mh < 32:
                _fail(errors, f"{mid} 按钮 minH={mh} < 32")
            else:
                _pass(f"{mid} 按钮 minH={mh}")
        except Exception as e:
            _fail(errors, f"建页 {mid}: {e}")
    app.processEvents()
    return errors


def main() -> int:
    print("=" * 60)
    print("VERIFY shell hardening (方案 32 · Agent 自测)")
    print("=" * 60)
    all_errors: list[str] = []
    all_errors += check_static_source()
    all_errors += check_error_hook()
    all_errors += check_menu_visibility()
    all_errors += check_shell_runtime()
    all_errors += check_widget_heights()

    print("\n" + "=" * 60)
    if all_errors:
        print(f"VERIFY SHELL HARDENING FAILED ({len(all_errors)})")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print("VERIFY SHELL HARDENING OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
