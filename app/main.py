# -*- coding: utf-8 -*-
"""TOA3 应用入口。"""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.app_state import AppState
from app.bootstrap import bootstrap_runtime
from app.logging_setup import setup_logging
from app.login_dialog import ensure_authenticated
from app.shell import MainShell
from app.theme_loader import apply_theme, ensure_official_qss, resolve_default_theme
from app.version import APP_VERSION
from core.error_handler import install_qt_exception_hook
from services.config_service import load_config, project_root

logger = logging.getLogger("TOA3")


def _configure_webengine_env() -> None:
    """内嵌 Chromium：保留 GPU（跟手），用 Angle/D3D11 稳一点，去掉会卡死交互的 disable-gpu。"""
    import os
    import sys

    from services.qt_webengine_bootstrap import configure_qt_webengine

    # 须在 QApplication 前：含 dsh-resource 协议注册（Harness 侧栏文件预览）
    configure_qt_webengine()

    key = "QTWEBENGINE_CHROMIUM_FLAGS"
    extras = [
        "--disable-lcd-text",
        "--font-render-hinting=full",
        "--enable-font-antialiasing",
        # Windows 嵌入：父窗重绘 / 遮挡误判 → 白闪、假死、回来糊一帧
        "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
    ]
    if sys.platform == "win32":
        # D3D11 路径比默认更容易稳，减轻悬停闪烁；仍走 GPU，不回软件光栅
        extras.append("--use-angle=d3d11")
    # 历史版本为减闪退曾写入 disable-gpu*，会让引擎页点哪都卡
    strip = {
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-rasterization",
    }
    # 旧版只写了 CalculateNativeWinOcclusion，统一换成带 IntensiveWakeUp 的合并项
    cur = (os.environ.get(key) or "").strip()
    parts = [p for p in cur.split() if p and p not in strip]
    parts = [
        p
        for p in parts
        if not p.startswith("--disable-features=CalculateNativeWinOcclusion")
    ]
    for flag in extras:
        if flag not in parts:
            parts.append(flag)
    os.environ[key] = " ".join(parts)


def _set_app_icon(app: QApplication) -> None:
    from services.icon_registry import app_window_icon

    icon = app_window_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)


def _cli_license_activation() -> int | None:
    """安装器静默激活：TOA3.exe --activate-license \"TOA2-...\""""
    if len(sys.argv) < 3 or sys.argv[1] not in ("--activate-license", "--verify-license"):
        return None
    key = (sys.argv[2] or "").strip()
    if not key:
        print("FAIL: empty license key")
        return 2
    setup_logging()
    bootstrap_runtime()
    try:
        from services.license_manager import global_license_manager

        if sys.argv[1] == "--verify-license":
            ok, msg, _ = global_license_manager.verify_license_code(key)
        else:
            ok, msg = global_license_manager.validate_license_key(key)
        print(("OK: " if ok else "FAIL: ") + str(msg))
        return 0 if ok else 2
    except Exception as e:
        print("FAIL: " + str(e))
        return 3


def main() -> int:
    cli_code = _cli_license_activation()
    if cli_code is not None:
        return cli_code

    setup_logging()
    # 原生闪退时尽量留下栈（Windows ACCESS_VIOLATION 常见于 WebEngine）
    try:
        import faulthandler
        from pathlib import Path

        from services.config_service import resolve_path

        crash_path = resolve_path("log_dir") / "toa3_faulthandler.log"
        crash_path.parent.mkdir(parents=True, exist_ok=True)
        _crash_fp = open(crash_path, "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_crash_fp, all_threads=True)
        logger.info("faulthandler 已启用 → %s", crash_path)
    except Exception:
        logger.debug("faulthandler 启用失败", exc_info=True)

    install_qt_exception_hook()
    bootstrap_runtime()
    _configure_webengine_env()

    try:
        from services.harness_config import align_harness_runtime_config

        align_harness_runtime_config(persist=True)
    except Exception:
        pass

    # 须在 QApplication 之前：否则任务栏仍归到 python.exe「Python」
    from services.windows_app_identity import apply_windows_app_identity

    apply_windows_app_identity()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    # WebEngine 须共享 GL 上下文，否则首次嵌入易整窗闪白
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    try:
        from services.qt_webengine_bootstrap import apply_frozen_qt_library_paths

        apply_frozen_qt_library_paths(app)
    except Exception:
        logger.debug("apply_frozen_qt_library_paths failed", exc_info=True)
    app.setApplicationName("TOA3")
    try:
        from services.app_branding import is_development_profile

        app.setApplicationDisplayName(
            "运营宝 TOA3 (开发)" if is_development_profile() else "运营宝 TOA3"
        )
    except Exception:
        app.setApplicationDisplayName("运营宝 TOA3")
    app.setOrganizationName("YCZH")
    app.setApplicationVersion(APP_VERSION)
    _set_app_icon(app)

    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    try:
        cfg = load_config()
        AppState.get().config = cfg
    except Exception as e:
        logger.exception("配置加载失败: %s", e)
        return 1

    theme_id = resolve_default_theme()
    generated = ensure_official_qss()
    if generated:
        logger.info("首次启动已生成 %d 个主题 QSS", generated)
    apply_theme(app, theme_id)

    shell_holder: list = []
    from services.drop_handoff import collect_launch_paths

    launch_paths = collect_launch_paths()
    launch_path_strs = [str(p) for p in launch_paths]

    def _on_second_instance(paths: list[str]) -> None:
        if not shell_holder:
            return
        from services.win_foreground import force_widget_foreground

        shell = shell_holder[0]
        force_widget_foreground(shell)
        if paths:
            try:
                shell.open_drop_paths(paths)
            except Exception:
                logger.debug("open_drop_paths from second instance failed", exc_info=True)

    from services.single_instance import try_acquire_single_instance

    if not try_acquire_single_instance(
        app, on_second=_on_second_instance, launch_paths=launch_path_strs
    ):
        logger.info("已有实例运行，退出本进程")
        return 0

    if not ensure_authenticated():
        logger.info("用户取消登录")
        return 0

    try:
        shell = MainShell(defer_startup=True)
        shell_holder.append(shell)
        # 先亮主窗再接线：避免「喘气」——登录后长时间黑屏/无窗
        shell.show()
        try:
            from services.windows_app_identity import apply_window_taskbar_identity

            apply_window_taskbar_identity(shell)
        except Exception:
            pass
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, shell.complete_startup)
        # Chromium 预热已禁用（双 View 闪烁）；共享引擎首次 acquire 时再拉起
        # QTimer.singleShot(4500, ...) 勿恢复 prewarm_chromium_process
        if launch_path_strs:
            QTimer.singleShot(200, lambda: shell.open_drop_paths(launch_path_strs))
    except Exception:
        logger.exception("主壳启动失败")
        from services.single_instance import release_single_instance

        release_single_instance()
        return 1

    try:
        from services.access_control import requires_purchase_redirect
        from services.license_manager import global_license_manager
        from services.notify_bus import NotifyLevel, notify

        if requires_purchase_redirect():
            from services.user_plan_presentation import user_access_block_message

            notify(
                NotifyLevel.WARNING,
                title="续费提醒",
                body=f"{user_access_block_message()}。",
                channel="status",
            )
        elif not global_license_manager.is_licensed() and not global_license_manager.is_standalone_mode():
            pass
    except Exception:
        pass

    logger.info("TOA3 主壳已启动 v%s 主题=%s", APP_VERSION, theme_id)

    def _on_quit() -> None:
        try:
            from services.webengine_shutdown import prepare_app_exit

            prepare_app_exit()
        except Exception:
            pass
        try:
            from services.harness_sidecar import stop_on_app_exit_if_configured

            stop_on_app_exit_if_configured()
        except Exception:
            pass

    app.aboutToQuit.connect(_on_quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
