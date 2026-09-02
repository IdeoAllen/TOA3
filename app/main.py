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
    """内嵌 Chromium 在 125%/150% 缩放下易发虚：提前设字体渲染标志。"""
    import os

    from services.qt_webengine_bootstrap import configure_frozen_qt_webengine

    configure_frozen_qt_webengine()

    key = "QTWEBENGINE_CHROMIUM_FLAGS"
    # 灰度抗锯齿 + 完整 hinting，减轻分数倍缩放下的发糊
    extras = (
        "--disable-lcd-text",
        "--font-render-hinting=full",
        "--enable-font-antialiasing",
        # Windows 嵌入 WebEngine 时父窗重绘易闪白；禁用原生遮挡计算
        "--disable-features=CalculateNativeWinOcclusion",
    )
    cur = (os.environ.get(key) or "").strip()
    parts = [p for p in cur.split() if p]
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
    install_qt_exception_hook()
    bootstrap_runtime()
    _configure_webengine_env()

    # 须在 QApplication 之前：否则任务栏仍归到 python.exe「Python」
    from services.windows_app_identity import apply_windows_app_identity

    apply_windows_app_identity()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
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

    def _activate_existing() -> None:
        if shell_holder:
            from services.win_foreground import force_widget_foreground

            force_widget_foreground(shell_holder[0])

    from services.single_instance import try_acquire_single_instance

    if not try_acquire_single_instance(app, on_second=_activate_existing):
        logger.info("已有实例运行，退出本进程")
        return 0

    if not ensure_authenticated():
        logger.info("用户取消登录")
        return 0

    try:
        shell = MainShell(defer_startup=True)
        shell_holder.append(shell)
        shell.complete_startup()
        shell.show()
        try:
            from services.windows_app_identity import apply_window_taskbar_identity

            apply_window_taskbar_identity(shell)
        except Exception:
            pass
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
