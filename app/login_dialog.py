# -*- coding: utf-8 -*-
"""登录对话框。"""
from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from app.app_state import AppState
from app.version import version_caption
from core.base_dialog import BaseDialog
from core.error_handler import report_error
from core.exceptions import AuthError
from services.auth_service import authenticate, authenticate_standalone
from services.config_service import get_auth_config, project_root
from services.dms_license_client import cloud_origin, license_service_label
from widgets import DialogButtonRow, HintLabel, LineEdit, PageTitle, PasswordLineEdit, SemanticLabel

logger = logging.getLogger(__name__)

_LOGIN_TIMEOUT_S = 20


class LoginDialog(BaseDialog):
    dialog_kind = "login"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        st = AppState.get()
        brand = st.brand_name()
        self.setWindowTitle(f"登录 · {brand}")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self._build_header(brand))

        auth = get_auth_config()
        self._skip = bool(auth.get("skip_login"))
        self._allow_standalone = bool(auth.get("allow_standalone_login", True))

        if self._skip:
            hint_text = "开发模式：auth.skip_login 已开启，输入任意用户名即可。"
            hint_kind = "warning"
        elif self._allow_standalone:
            hint_text = (
                "单机体验：免授权码、可离线，开放基础办公工具。"
                "完整版请粘贴 TOA 运营台签发的 TOA2- 授权码（需联网激活）。"
            )
            hint_kind = "info"
        else:
            hint_text = "请粘贴 TOA 运营台签发的完整 TOA2-… 授权码；显示名可留空。"
            hint_kind = "info"
        layout.addWidget(SemanticLabel(hint_text, kind=hint_kind))

        service_hint = f"授权服务：{license_service_label()} · {cloud_origin() or '未配置'}"
        layout.addWidget(HintLabel(service_hint))

        form = QFormLayout()
        self._user = LineEdit()
        self._user.setPlaceholderText("可选：台账姓名（以授权码为准）")
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("完整版：TOA2- 授权码")
        self._prefill_username()
        self._prefill_license_key()
        if not self._skip:
            form.addRow("显示名", self._user)
            form.addRow("授权码", self._key)
        layout.addLayout(form)

        self._status = SemanticLabel("", kind="info")
        self._status.hide()
        layout.addWidget(self._status)

        buttons = DialogButtonRow()
        buttons.add_secondary("取消", self.reject)
        if self._allow_standalone and not self._skip:
            self._btn_standalone = buttons.add_secondary("单机体验", self._on_standalone)
        self._btn_login = buttons.add_primary("授权码登录", self._on_accept)
        layout.addWidget(buttons)

        layout.addWidget(
            HintLabel("获取授权码：TOA 运营台 https://toa-service.yczh.tech/admin/")
        )

        self._authenticated = False
        self._login_busy = False
        self._login_poll: QTimer | None = None
        self._login_deadline = 0.0
        self._login_result: tuple[bool, dict, str] | None = None
        if not self._skip and hasattr(self, "_key"):
            if self._allow_standalone:
                self._btn_standalone.setFocus()
            else:
                self._key.setFocus()

    def _build_header(self, brand: str) -> QWidget:
        row = QWidget(self)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        logo = QLabelLogo(self)
        h.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.addWidget(PageTitle(brand))
        text_col.addWidget(HintLabel(version_caption()))
        wrap = QWidget(row)
        wrap.setLayout(text_col)
        h.addWidget(wrap, 1)
        return row

    def _prefill_username(self) -> None:
        auth = get_auth_config()
        preset = str(auth.get("prefill_username") or "").strip()
        if preset:
            self._user.setText(preset)
            return
        ok, name = _local_restorable_session()
        if ok and name:
            self._user.setText(name)

    def _prefill_license_key(self) -> None:
        auth = get_auth_config()
        preset = str(auth.get("prefill_license_key") or "").strip()
        if preset and hasattr(self, "_key"):
            self._key.setText(preset)

    def _set_status(self, text: str, *, kind: str = "info", visible: bool = True) -> None:
        self._status.setText(text)
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.setVisible(visible and bool(text.strip()))

    def _set_login_busy(self, busy: bool, *, status: str = "") -> None:
        self._login_busy = busy
        self._btn_login.setEnabled(not busy)
        self._btn_login.setText("登录中…" if busy else "授权码登录")
        if hasattr(self, "_btn_standalone"):
            self._btn_standalone.setEnabled(not busy)
        self._user.setEnabled(not busy)
        self._key.setEnabled(not busy)
        if busy:
            self._set_status(status or "正在联网激活，请稍候…", kind="info")
        elif not status:
            self._set_status("", visible=False)

    def _try_accept_local_license(self, license_key: str) -> bool:
        """本机已激活且授权码一致 → 免再次联网，直接进主界面。"""
        key = str(license_key or "").strip()
        if not key:
            return False
        try:
            from services.license_manager import global_license_manager as lm

            ok, _msg, payload = lm.verify_license_code(key)
            if not ok or not payload or not lm.is_licensed():
                return False
            info = lm.get_license_info()
            code_id = str(payload.get("_code_id") or lm._code_id(key))
            if str(info.get("activated_code_id") or "") != code_id:
                return False
            name = str(info.get("user_name") or payload.get("name") or "").strip()
            if not name:
                return False
            AppState.get().set_user(name, name, role=str(info.get("role") or ""))
            self._authenticated = True
            self.accept()
            return True
        except Exception:
            logger.debug("本机快速登录失败", exc_info=True)
            return False

    def _run_login_task(self, *, username: str, license_key: str, standalone: bool) -> tuple[bool, dict, str]:
        try:
            if standalone:
                session = authenticate_standalone()
            else:
                session = authenticate(username, license_key)
            return True, session, ""
        except AuthError as e:
            return False, {}, str(e)
        except Exception as e:
            logger.exception("登录线程异常")
            return False, {}, str(e)

    def _start_worker(self, *, username: str, license_key: str, standalone: bool) -> None:
        if self._login_busy:
            return
        if not standalone and self._try_accept_local_license(license_key):
            return
        self._set_login_busy(
            True,
            status="正在校验授权码…" if not standalone else "正在进入单机体验…",
        )
        self._login_result = None
        self._login_deadline = time.monotonic() + _LOGIN_TIMEOUT_S

        def _worker() -> None:
            result = self._run_login_task(
                username=username,
                license_key=license_key,
                standalone=standalone,
            )
            self._login_result = result
            logger.info(
                "登录线程完成 ok=%s err=%s",
                result[0],
                (result[2][:80] if result[2] else ""),
            )

        threading.Thread(target=_worker, name="toa3-login", daemon=True).start()

        poll = QTimer(self)
        poll.timeout.connect(self._poll_login_worker)
        poll.start(120)
        self._login_poll = poll

    def _poll_login_worker(self) -> None:
        if self._login_result is not None:
            if self._login_poll is not None:
                self._login_poll.stop()
                self._login_poll = None
            ok, session, err = self._login_result
            self._login_result = None
            self._on_worker_finished(ok, session, err)
            return
        if self._login_busy and time.monotonic() >= self._login_deadline:
            if self._login_poll is not None:
                self._login_poll.stop()
                self._login_poll = None
            self._on_login_timeout()

    def _on_login_timeout(self) -> None:
        if not self._login_busy:
            return
        self._set_login_busy(False)
        msg = f"登录超时（{_LOGIN_TIMEOUT_S} 秒），请检查网络或稍后重试"
        self._set_status(msg, kind="danger")
        report_error(self, AuthError(msg), title="登录超时", context="LoginDialog")

    def _on_worker_finished(self, ok: bool, session: dict, err: str) -> None:
        if self._login_poll is not None:
            self._login_poll.stop()
            self._login_poll = None
        if not self._login_busy:
            return
        if ok:
            AppState.get().set_user(
                session["username"],
                session["display_name"],
                role=str(session.get("role") or ("user" if session.get("runtime_mode") == "standalone" else "")),
            )
            self._authenticated = True
            self._set_login_busy(False)
            self.accept()
            return
        self._set_login_busy(False)
        detail = err or "登录失败"
        self._set_status(detail, kind="danger")
        report_error(self, AuthError(detail), title="登录失败", context="LoginDialog")

    def _on_standalone(self) -> None:
        self._start_worker(username="", license_key="", standalone=True)

    def _on_accept(self) -> None:
        key = self._key.text().strip() if hasattr(self, "_key") else ""
        if not key and not self._skip:
            self._set_status("请粘贴 TOA 运营台签发的完整 TOA2 授权码", kind="warning")
            report_error(
                self,
                AuthError("请粘贴 TOA 运营台签发的完整 TOA2 授权码"),
                title="登录失败",
                context="LoginDialog",
            )
            return
        self._start_worker(username=self._user.text(), license_key=key, standalone=False)

    @property
    def authenticated(self) -> bool:
        return self._authenticated


class QLabelLogo(QWidget):
    """登录页品牌图标（HiDPI PNG，不走模糊缩放）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self._pix = QPixmap()
        path = project_root() / "resources" / "icons" / "app_logo.png"
        if path.is_file():
            self._pix = QPixmap(str(path))

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter

        if self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        scaled = self._pix.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)


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
    info: dict = {}
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
    # 优先恢复本机已激活会话（赵成全功能 / 关佳伟单机等）
    if not auth.get("force_login_dialog") and try_restore_licensed_session():
        return True
    if auth.get("skip_login"):
        try:
            session = authenticate("", "")
            AppState.get().set_user(
                session["username"],
                session["display_name"],
                role=str(session.get("role") or "user"),
            )
            logger.info("跳过登录 (auth.skip_login)，用户: %s", session["username"])
            return True
        except Exception:
            pass

    st = AppState.get()
    if st.is_authenticated:
        return True

    dlg = LoginDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted and dlg.authenticated:
        return True
    return False
