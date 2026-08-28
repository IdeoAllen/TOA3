# -*- coding: utf-8 -*-
"""顶栏用户：换授权码与退出。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFormLayout, QVBoxLayout

from app.app_state import AppState
from app.dialog_chrome import add_dialog_hero, apply_dialog_root
from core.base_dialog import BaseDialog
from core.user_messages import ask_confirm, show_error, show_success, show_warning
from services.icon_registry import icon_pixmap
from services.license_manager import global_license_manager
from services.notify_bus import emit_license_changed
from widgets import DialogButtonRow, HintLabel, PasswordLineEdit, PrimaryButton


class _ActivateWorker(QObject):
    finished = Signal(bool, str, object)

    def __init__(self, license_key: str) -> None:
        super().__init__()
        self._key = license_key

    def run(self) -> None:
        try:
            ok, msg, payload = global_license_manager.activate_with_code(self._key)
            self.finished.emit(bool(ok), str(msg or ""), payload)
        except Exception as exc:
            self.finished.emit(False, str(exc), None)


class UserProfileDialog(BaseDialog):
    """粘贴授权码联网激活 / 换码。"""

    dialog_kind = "account"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("换授权码")
        self._lm = global_license_manager
        self._thread: QThread | None = None
        self._worker: _ActivateWorker | None = None
        self._busy = False

        st = AppState.get()
        licensed = bool(self._lm.is_licensed())
        display = str(st.display_name or st.username or "用户").strip() or "用户"
        role = str(st.role or "").strip()
        role_txt = {"admin": "管理员", "user": "用户"}.get(role, role or "—")
        validity = self._lm.get_validity_text() or ("已授权" if licensed else "未授权")
        scope = self._lm.format_features_summary()

        root = QVBoxLayout(self)
        apply_dialog_root(root)

        pal = st.palette or {}
        fg = str(pal.get("primary") or pal.get("nav_fg") or "#2563EB")
        avatar_pm = icon_pixmap("user", color=fg, size=48, parent=self)
        add_dialog_hero(
            root,
            pixmap=avatar_pm,
            title=display,
            subtitle=f"{role_txt} · {validity} · {scope}",
            icon_size=48,
        )

        code_form = QFormLayout()
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("粘贴 TOA 运营台签发的完整授权码")
        code_form.addRow("授权码", self._key)
        root.addLayout(code_form)
        root.addWidget(HintLabel("联网激活后切换为对应账号与权限。"))

        self._btn_activate = PrimaryButton("联网激活" if not licensed else "确认换码")
        self._btn_activate.clicked.connect(self._on_activate)
        root.addWidget(self._btn_activate)

        actions = DialogButtonRow()
        actions.add_secondary("退出登录", self._on_sign_out)
        actions.add_primary("关闭", self.accept)
        root.addWidget(actions)

    def _shell(self):
        w = self.parent()
        while w is not None and not hasattr(w, "navigate"):
            w = w.parent() if hasattr(w, "parent") else None
        return w

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_activate.setEnabled(not busy)
        self._key.setEnabled(not busy)

    def _on_activate(self) -> None:
        if self._busy:
            return
        key = self._key.text().strip().replace(" ", "")
        if not key:
            show_warning(self, "请粘贴 TOA 运营台签发的完整授权码。")
            return
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在联网激活，请稍候。")
            return

        self._set_busy(True)

        self._thread = QThread(self)
        self._worker = _ActivateWorker(key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_activate_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_activate_done(self, ok: bool, msg: str, payload: object) -> None:
        self._set_busy(False)
        if not ok:
            show_error(self, msg or "激活失败", title="联网激活失败")
            return
        name = str((payload or {}).get("name") or "用户")
        role = str((payload or {}).get("role") or "user")
        AppState.get().set_user(name, name, role=role)
        emit_license_changed()
        self._key.clear()
        show_success(self, msg or "授权激活成功", title="激活完成")
        self.accept()

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _on_sign_out(self) -> None:
        if not ask_confirm(self, "退出当前账号？将返回登录界面。"):
            return
        shell = self._shell()
        self.accept()
        if shell is not None and hasattr(shell, "_sign_out_user"):
            shell._sign_out_user(confirmed=True)
