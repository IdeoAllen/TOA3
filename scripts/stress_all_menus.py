#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全菜单反复压测：任意侧栏页不得闪退/退出/崩溃；可见文字不得明显裁切。

Agent 自跑，不依赖主理人手测。

用法：
  python scripts/stress_all_menus.py
  python scripts/stress_all_menus.py --rounds 5 --dwell-ms 120
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 默认走真实 Windows 插件，更接近主理人环境；可用 --offscreen 强制离屏
if "--offscreen" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # 离屏 + WebEngine GPU 易 context lost → 原生闪退；强制软件渲染
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    extra = "--disable-gpu --disable-gpu-compositing"
    if "--disable-gpu" not in flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} {extra}".strip()

WEB_HEAVY = frozenset(
    {
        "harness_agent",
        "open_pencil",
        "drawio_web",
        "comfyui_web",
        "web_workspace",
    }
)


class _HookCapture:
    def __init__(self) -> None:
        self.criticals: list[str] = []
        self.system_exits = 0
        self.already_deleted = 0

    def install(self) -> None:
        from core.error_handler import install_qt_exception_hook

        install_qt_exception_hook()
        # 包一层统计
        prev = sys.excepthook

        def _wrap(exc_type, exc, tb) -> None:  # noqa: ANN001
            msg = str(exc or "")
            if issubclass(exc_type, SystemExit):
                self.system_exits += 1
            elif issubclass(exc_type, RuntimeError) and (
                "already deleted" in msg.lower() or "Internal C++ object" in msg
            ):
                self.already_deleted += 1
            elif not issubclass(exc_type, KeyboardInterrupt):
                self.criticals.append(f"{exc_type.__name__}: {msg}")
            return prev(exc_type, exc, tb)

        sys.excepthook = _wrap


def _visible_sidebar_ids() -> list[str]:
    from services.access_control import can_open
    from services.menu_registry import grouped_menu_items, show_in_sidebar

    out: list[str] = []
    seen: set[str] = set()
    for _gid, _gl, items in grouped_menu_items(licensed_only=False, migrated_only=True):
        for it in items:
            mid = str(it.get("id") or "").strip()
            if not mid or mid in seen:
                continue
            if not show_in_sidebar(it):
                continue
            if not bool(it.get("show", True)):
                continue
            ok, _ = can_open(mid)
            if not ok:
                continue
            seen.add(mid)
            out.append(mid)
    # 系统设置必须覆盖（顶栏可达）
    if "system_settings" not in seen:
        out.append("system_settings")
    return out


def _pump(app, ms: int) -> None:
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.008)


def _scan_clipping(page, *, page_id: str) -> list[str]:
    """检测明显文字裁切：可见标签/按钮内容宽高显著大于控件几何。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QPlainTextEdit, QTextEdit

    issues: list[str] = []
    if page is None:
        return issues
    widgets = list(page.findChildren(QLabel)) + list(page.findChildren(QAbstractButton))
    for w in widgets:
        try:
            if not w.isVisible():
                continue
            text = ""
            if isinstance(w, QLabel):
                text = (w.text() or "").strip()
                if w.wordWrap():
                    continue
                if w.textFormat() == Qt.TextFormat.RichText and "<" in text:
                    continue
            elif isinstance(w, QAbstractButton):
                text = (w.text() or "").strip()
            if not text or text in ("…", "...", "·"):
                continue
            # 图标按钮可无文字
            if len(text) <= 1:
                continue
            geo = w.geometry()
            if geo.width() < 8 or geo.height() < 8:
                continue
            hint = w.sizeHint()
            # 允许轻微误差；侧栏折叠标题等用 elide 的跳过
            elide = getattr(w, "textElideMode", None)
            if callable(elide):
                mode = elide()
                if mode != Qt.TextElideMode.ElideNone:
                    continue
            # 过长提示用 tooltip 的不报
            if hint.width() > geo.width() + 12 and geo.width() > 0:
                # 若父级可滚动，可能是列表项故意窄
                parent_name = type(w.parent()).__name__ if w.parent() else ""
                if parent_name in ("QScrollArea", "QAbstractItemView"):
                    continue
                issues.append(
                    f"{page_id}:{type(w).__name__}「{text[:24]}」宽裁切 "
                    f"hint={hint.width()} geo={geo.width()}"
                )
            if hint.height() > geo.height() + 8 and geo.height() > 0:
                # 单行控件高度被压扁
                if isinstance(w, (QLineEdit, QPlainTextEdit, QTextEdit)):
                    continue
                issues.append(
                    f"{page_id}:{type(w).__name__}「{text[:24]}」高裁切 "
                    f"hint={hint.height()} geo={geo.height()}"
                )
        except RuntimeError:
            continue
        except Exception:
            continue
    return issues


def _assert_shell_alive(shell, app, errors: list[str], where: str) -> bool:
    try:
        if shell is None:
            errors.append(f"{where}: shell is None")
            return False
        if not shell.updatesEnabled():
            errors.append(f"{where}: updatesEnabled=False（疑似冻窗闪烁锁）")
            shell.setUpdatesEnabled(True)
        # 访问一次标题证明 C++ 对象仍在
        _ = shell.windowTitle()
        app.processEvents()
        return True
    except RuntimeError as e:
        errors.append(f"{where}: shell RuntimeError {e}")
        return False


def run_stress(*, rounds: int, dwell_ms: int, rapid: int) -> int:
    from PySide6.QtWidgets import QApplication

    from app.app_state import AppState
    from app.bootstrap import bootstrap_runtime
    from app.logging_setup import setup_logging
    from app.shell import MainShell
    from services.config_service import load_config

    print("=" * 64)
    print("STRESS all menus · Agent 自测")
    print("=" * 64)

    setup_logging()
    bootstrap_runtime()
    cfg = load_config()
    AppState.get().config = cfg
    AppState.get().set_user("stress_menus", "全菜单压测", role="admin")

    hook = _HookCapture()
    hook.install()

    app = QApplication.instance() or QApplication([])
    errors: list[str] = []
    clip_issues: list[str] = []
    visited: dict[str, int] = {}

    mids = _visible_sidebar_ids()
    print(f"可见可打开菜单 {len(mids)} 项: {', '.join(mids)}")

    shell = None
    try:
        shell = MainShell(defer_startup=True)
        shell.resize(1280, 800)
        shell.show()
        _pump(app, 200)
        if hasattr(shell, "complete_startup"):
            try:
                shell.complete_startup()
            except Exception:
                logging.getLogger("TOA3").debug("complete_startup skip", exc_info=True)
        _pump(app, 300)

        def visit(mid: str, *, settle: int | None = None) -> None:
            if not _assert_shell_alive(shell, app, errors, f"before:{mid}"):
                return
            try:
                shell.navigate(mid)
            except SystemExit as e:
                errors.append(f"navigate({mid}) SystemExit code={e.code}")
                return
            except Exception as e:
                errors.append(f"navigate({mid}) {type(e).__name__}: {e}")
                return
            wait = settle if settle is not None else dwell_ms
            if mid in WEB_HEAVY:
                wait = max(wait, max(dwell_ms * 4, 500))
            _pump(app, wait)
            if mid in WEB_HEAVY:
                # 等 purge+deleteLater；离页后台链须已因 soft_leave 取消
                _pump(app, 800)
            if not _assert_shell_alive(shell, app, errors, f"after:{mid}"):
                return
            # 当前页应能取到（Loading 也算存活）
            page = shell._pages.get(mid)
            cur = shell._stack.currentWidget()
            if page is not None and cur is page:
                clip_issues.extend(_scan_clipping(page, page_id=mid)[:8])
            visited[mid] = visited.get(mid, 0) + 1

        # —— 完整轮次：顺序走遍 ——
        for r in range(rounds):
            print(f"\n--- round {r + 1}/{rounds} 顺序全菜单 ---")
            for mid in mids:
                print(f"  → {mid}")
                visit(mid)
                # 引擎页后强制回系统，打断 WebEngine 粘连
                if mid in WEB_HEAVY:
                    visit("system_settings", settle=max(dwell_ms * 3, 500))
                    _pump(app, 400)
            visit("home", settle=dwell_ms)

        # —— 狂切：轻页快速来回 ——
        light = [m for m in mids if m not in WEB_HEAVY]
        print(f"\n--- rapid ×{rapid} 轻页狂切 ({len(light)} 项) ---")
        for i in range(rapid):
            for mid in light:
                visit(mid, settle=max(40, dwell_ms // 3))
            if i % 2 == 0:
                visit("system_settings", settle=max(80, dwell_ms // 2))

        # —— 引擎交错：引擎 ↔ 系统 ——
        engines = [m for m in mids if m in WEB_HEAVY]
        if engines:
            print(f"\n--- engines ↔ system ×3 ({engines}) ---")
            for _ in range(3):
                for mid in engines:
                    visit(mid, settle=max(dwell_ms * 2, 400))
                    visit("system_settings", settle=max(400, dwell_ms * 2))

        _pump(app, 200)
        _assert_shell_alive(shell, app, errors, "final")

    except SystemExit as e:
        errors.append(f"顶层 SystemExit code={e.code}")
    except Exception as e:
        errors.append(f"顶层异常 {type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        if shell is not None:
            try:
                # 先回轻页并拆 Web，再关窗（避免析构闪退被当成压测失败）
                try:
                    shell.navigate("home")
                except Exception:
                    pass
                _pump(app, 200)
                try:
                    shell._purge_stale_web_embeds(except_mid=None)
                except Exception:
                    pass
                try:
                    from services.shared_local_webengine import shutdown as shutdown_shared_web

                    shutdown_shared_web()
                except Exception:
                    pass
                _pump(app, 600)
                shell.close()
                shell.deleteLater()
            except Exception:
                pass
        _pump(app, 300)

    # 裁切去重，同类过多则汇总
    clip_unique = sorted(set(clip_issues))
    # 过滤已知可接受 elide / 状态栏短标签噪声：同页超过 12 条只报前 12
    if len(clip_unique) > 40:
        # 可能误报过多：只保留宽裁切更严重的
        clip_unique = [c for c in clip_unique if "宽裁切" in c][:40]

    print("\n" + "=" * 64)
    print(f"访问统计: {len(visited)}/{len(mids)} 模块，总进入 {sum(visited.values())} 次")
    missing = [m for m in mids if visited.get(m, 0) == 0]
    if missing:
        errors.append(f"未访问: {missing}")

    if hook.system_exits:
        errors.append(f"excepthook 见到 SystemExit ×{hook.system_exits}（已拦截仍计风险）")
    # already_deleted 降级为 warning 可接受，但过多说明销毁竞态
    if hook.already_deleted > 5:
        errors.append(f"already deleted 过多 ×{hook.already_deleted}")
    for c in hook.criticals[:20]:
        errors.append(f"未捕获: {c}")

    if clip_unique:
        print(f"文字裁切嫌疑 {len(clip_unique)}：")
        for c in clip_unique[:30]:
            print(f"  CLIP  {c}")
        # 裁切作为失败（主理人明确要求）
        errors.extend(f"裁切 {c}" for c in clip_unique[:20])

    if errors:
        print(f"\nSTRESS FAILED ({len(errors)})")
        for e in errors[:50]:
            print(f"  - {e}")
        return 1
    print("\nSTRESS ALL MENUS OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3, help="全菜单顺序轮数")
    ap.add_argument("--dwell-ms", type=int, default=120, help="每页停留毫秒")
    ap.add_argument("--rapid", type=int, default=2, help="轻页狂切轮数")
    ap.add_argument("--offscreen", action="store_true")
    args, _unknown = ap.parse_known_args()
    return run_stress(rounds=args.rounds, dwell_ms=args.dwell_ms, rapid=args.rapid)


if __name__ == "__main__":
    raise SystemExit(main())
