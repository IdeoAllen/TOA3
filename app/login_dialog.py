# -*- coding: utf-8 -*-
"""登录对话框。"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QVBoxLayout

from app.app_state import AppState
from core.base_dialog import BaseDialog
from core.error_handler import report_error
from services.auth_service import authenticate, authenticate_standalone
from services.config_service import get_auth_config
from widgets import DialogButtonRow, HintLabel, LineEdit, PageTitle, PasswordLineEdit, SemanticLabel

logger = logging.getLogger(__name__)


class LoginDialog(BaseDialog):
    dialog_kind = "login"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        st = AppState.get()
        self.setWindowTitle(f"登录 · {st.brand_name()}")

        layout = QVBoxLayout(self)
        layout.addWidget(PageTitle("欢迎使用运营宝"))

        auth = get_auth_config()
        self._skip = bool(auth.get("skip_login"))
        self._allow_standalone = bool(auth.get("allow_standalone_login", True))
        if self._skip:
            hint_text = "开发模式：auth.skip_login 已开启，输入任意用户名即可。"
            hint_kind = "warning"
        elif self._allow_standalone:
            hint_text = (
                "单机体验：免授权码、可离线，开放基础办公工具。"
                "完整版请粘贴 TOA2- 授权码（需联网激活）。"
            )
            hint_kind = "info"
        else:
            hint_text = "请粘贴 TOA 运营台签发的完整 TOA2-… 授权码；用户名可留空。"
            hint_kind = "info"
        layout.addWidget(SemanticLabel(hint_text, kind=hint_kind))

        form = QFormLayout()
        self._user = LineEdit()
        self._user.setPlaceholderText("可选：台账姓名")
        self._prefill_username()
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("完整版：TOA2- 授权码")
        if not self._skip:
            form.addRow("用户名", self._user)
            form.addRow("授权码", self._key)
        layout.addLayout(form)

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        if self._allow_standalone and not self._skip:
            self._btn_standalone = buttons.add_secondary("单机体验", self._on_standalone)
        self._btn_login = buttons.add_primary("授权码登录", self._on_accept)
        layout.addWidget(buttons)

        self._authenticated = False
        self._login_busy = False
        if not self._skip and hasattr(self, "_key"):
            if self._allow_standalone:
                self._btn_standalone.setFocus()
            else:
                self._key.setFocus()

    def _prefill_username(self) -> None:
        ok, name = _local_restorable_session()
        if ok and name:
            self._user.setText(name)

    def _set_login_busy(self, busy: bool) -> None:
        self._login_busy = busy
        self._btn_login.setEnabled(not busy)
        self._btn_login.setText("登录中…" if busy else "授权码登录")
        if hasattr(self, "_btn_standalone"):
            self._btn_standalone.setEnabled(not busy)

    def _on_standalone(self) -> None:
        if self._login_busy:
            return
        self._set_login_busy(True)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        try:
            session = authenticate_standalone()
            AppState.get().set_user(
                session["username"],
                session["display_name"],
                role=str(session.get("role") or "user"),
            )
            self._authenticated = True
            self.accept()
        except Exception as e:
            report_error(self, e, title="进入单机版失败", context="LoginDialog")
        finally:
            self._set_login_busy(False)

    def _on_accept(self) -> None:
        if self._login_busy:
            return
        self._set_login_busy(True)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        try:
            key = self._key.text().strip() if hasattr(self, "_key") else ""
            if not key and not self._skip:
                from core.exceptions import AuthError

                raise AuthError("请粘贴 TOA 运营台签发的完整 TOA2 授权码")
            session = authenticate(self._user.text(), key)
            AppState.get().set_user(
                session["username"],
                session["display_name"],
                role=str(session.get("role") or ""),
            )
            self._authenticated = True
            self.accept()
        except Exception as e:
            report_error(self, e, title="登录失败", context="LoginDialog")
        finally:
            self._set_login_busy(False)

    @property
    def authenticated(self) -> bool:
        return self._authenticated


def _license_file_candidates() -> list:
    paths: list = []
    seen: set[str] = set()
    try:
        from services.config_service import resolve_path

        p = resolve_path("license_file")
        k = str(p.resolve())
        if k not in seen:
            seen.add(k)
            paths.append(p)
    except Exception:
        pass
    try:
        import os

        from services.runtime_paths import get_user_data_root, is_frozen

        if is_frozen() or os.environ.get("TOA_ENV", "").strip().lower() == "release":
            p = get_user_data_root() / "config" / "license.json"
            k = str(p.resolve())
            if k not in seen:
                seen.add(k)
                paths.append(p)
    except Exception:
        pass
    return paths


def _read_license_snapshot() -> dict | None:
    import json

    for path in _license_file_candidates():
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def _local_restorable_session() -> tuple[bool, str]:
    """读本机 license.json：完整授权或单机模式均可恢复。"""
    try:
        import datetime

        from services.runtime_mode import is_standalone_record

        info = _read_license_snapshot()
        if not info:
            return False, ""

        if is_standalone_record(info) and not info.get("is_licensed"):
            name = str(info.get("user_name") or "").strip()
            return True, name or "单机用户"

        if not info.get("is_licensed"):
            return False, ""
        name = str(info.get("user_name") or "").strip()
        if not name:
            return False, ""
        exp_raw = str(info.get("expire_date") or "")[:10]
        if exp_raw:
            try:
                exp = datetime.datetime.strptime(exp_raw, "%Y-%m-%d").date()
                if exp < datetime.date.today():
                    return False, ""
            except ValueError:
                pass
        return True, name
    except Exception:
        logger.debug("读取本机授权失败", exc_info=True)
        return False, ""


def try_restore_licensed_session() -> bool:
    """本机已激活 / 单机模式 → 直接进主界面（启动不联网）。"""
    ok, name = _local_restorable_session()
    if not ok:
        return False
    try:
        from services.license_manager import global_license_manager
        from services.runtime_mode import is_standalone_record

        for path in _license_file_candidates():
            if not path.is_file():
                continue
            global_license_manager.license_file = str(path)
            global_license_manager.reload_from_disk()
            break
        info = global_license_manager.get_license_info()
        if is_standalone_record(info) and not info.get("is_licensed"):
            logger.info("已恢复单机模式会话")
        else:
            logger.info("已恢复本机授权会话: %s", name)
    except Exception:
        logger.debug("同步本机授权到内存失败", exc_info=True)
    AppState.get().set_user(name, name, role=str(info.get("role") or ""))
    return True


def ensure_authenticated(parent=None) -> bool:
    auth = get_auth_config()
    if auth.get("skip_login"):
        try:
            session = authenticate("", "")
            AppState.get().set_user(
                session["username"],
                session["display_name"],
                role=str(session.get("role") or "admin"),
            )
            logger.info("跳过登录 (auth.skip_login)，用户: %s", session["username"])
            return True
        except Exception:
            pass

    if try_restore_licensed_session():
        return True

    st = AppState.get()
    if st.is_authenticated:
        return True

    dlg = LoginDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted and dlg.authenticated:
        return True
    return False
