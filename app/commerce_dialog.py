# -*- coding: utf-8 -*-
"""终端商业弹窗：录入授权 · 购买套餐 · 我的账号（全局唯一实例）。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.app_state import AppState
from app.dialog_chrome import add_dialog_hero, apply_dialog_root, make_info_form, value_label
from core.base_dialog import BaseDialog
from core.user_messages import ask_confirm, show_error, show_success, show_warning
from services.config_service import get_auth_config
from services.icon_registry import icon_pixmap
from services.license_manager import global_license_manager
from services.notify_bus import emit_license_changed
from services.upgrade_flow import classify_intent, intent_headline
from services.user_plan_presentation import (
    user_account_subtitle,
    user_plan_tier,
    user_product_pack_label,
    user_validity_line,
)
from widgets.commerce_purchase_panel import CommercePurchasePanel
from widgets import (
    DialogButtonRow,
    FormSection,
    HintLabel,
    LineEdit,
    PageTitle,
    PasswordLineEdit,
    SecondaryButton,
    SemanticLabel,
)


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


class _AccountSummarySection(FormSection):
    """账号/授权摘要：档位 · 套餐 · 有效期。"""

    def __init__(self, parent=None) -> None:
        super().__init__("当前状态", parent)
        form = QFormLayout()
        self._tier = value_label("")
        self._pack = value_label("")
        self._validity = value_label("", selectable=True)
        form.addRow("当前档位", self._tier)
        form.addRow("当前套餐", self._pack)
        form.addRow("有效期", self._validity)
        wrap = QWidget()
        wrap.setLayout(form)
        self.add_widget(wrap)
        self.refresh()

    def refresh(self) -> None:
        self._tier.setText(user_plan_tier())
        self._pack.setText(user_product_pack_label())
        self._validity.setText(user_validity_line(date_only=True))


def _shell_parent(widget: QWidget | None):
    w = widget
    while w is not None and not hasattr(w, "navigate"):
        w = w.parent() if hasattr(w, "parent") else None
    return w


def _hero_color() -> str:
    pal = AppState.get().palette or {}
    return str(pal.get("primary") or pal.get("nav_fg") or "#2563EB")


class _CommerceWindowHub:
    """全局唯一商业弹窗：同类型再次调用时聚焦，不同类型先关闭再打开。"""

    _dialog: BaseDialog | None = None
    _kind: str = ""

    @classmethod
    def _alive(cls, dlg: BaseDialog | None) -> bool:
        if dlg is None:
            return False
        try:
            dlg.objectName()
            return True
        except RuntimeError:
            return False

    @classmethod
    def _clear(cls, dlg: BaseDialog) -> None:
        if cls._dialog is dlg:
            cls._dialog = None
            cls._kind = ""

    @classmethod
    def _dismiss(cls) -> None:
        dlg = cls._dialog
        if not cls._alive(dlg):
            cls._dialog = None
            cls._kind = ""
            return
        try:
            if dlg.isVisible():
                dlg.done(QDialog.DialogCode.Rejected)
            dlg.close()
        except RuntimeError:
            pass
        cls._dialog = None
        cls._kind = ""

    @classmethod
    def present(
        cls,
        kind: str,
        parent,
        factory: Callable[[], BaseDialog],
        *,
        apply_context: Callable[[BaseDialog], None] | None = None,
    ) -> bool:
        kind = str(kind or "").strip().lower()
        if cls._alive(cls._dialog) and cls._dialog.isVisible():
            if cls._kind == kind:
                if apply_context is not None:
                    apply_context(cls._dialog)
                if hasattr(cls._dialog, "refresh_view"):
                    cls._dialog.refresh_view()
                cls._dialog.raise_()
                cls._dialog.activateWindow()
                return False
            cls._dismiss()

        dlg = factory()
        cls._dialog = dlg
        cls._kind = kind
        dlg.finished.connect(lambda _=None: cls._clear(dlg))

        code = dlg.exec()
        completed = bool(getattr(dlg, "completed", False))
        return completed or code == QDialog.DialogCode.Accepted


class LicenseActivateDialog(BaseDialog):
    """录入授权：粘贴授权码联网激活。"""

    dialog_kind = "account"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._completed = False
        self._busy = False
        self._thread: QThread | None = None
        self._worker: _ActivateWorker | None = None

        self.setWindowTitle("录入授权")
        root = QVBoxLayout(self)
        apply_dialog_root(root)

        fg = _hero_color()
        root.addWidget(SemanticLabel("粘贴 TOA 运营台签发的完整授权码，联网激活后绑定本机。", kind="info"))
        add_dialog_hero(
            root,
            pixmap=icon_pixmap("settings", color=fg, size=48, parent=self),
            title="录入授权",
            subtitle=user_account_subtitle(),
            icon_size=48,
        )

        self._summary = _AccountSummarySection(self)
        root.addWidget(self._summary)

        sec = FormSection("授权信息")
        form = make_info_form()
        self._user = LineEdit()
        self._user.setPlaceholderText("可选，默认以授权码登记为准")
        self._key = PasswordLineEdit()
        self._key.setPlaceholderText("TOA 授权码")
        self._prefill_fields()
        form.addRow("显示名", self._user)
        form.addRow("授权码", self._key)
        wrap = QWidget()
        wrap.setLayout(form)
        sec.add_widget(wrap)
        sec.add_widget(HintLabel("购买成功后一般会自动激活；仅更换授权码或线下签发时使用本页。"))
        root.addWidget(sec)

        self._status = SemanticLabel("", kind="info")
        self._status.hide()
        root.addWidget(self._status)

        actions = DialogButtonRow()
        actions.add_secondary("取消", self.reject)
        actions.add_secondary("没有授权码？去购买", self._on_go_purchase)
        self._btn_activate = actions.add_primary("确认激活", self._on_activate)
        root.addWidget(actions)

        self._key.setFocus()

    @property
    def completed(self) -> bool:
        return self._completed

    def refresh_view(self) -> None:
        self._summary.refresh()

    def _prefill_fields(self) -> None:
        auth = get_auth_config()
        preset_key = str(auth.get("prefill_license_key") or "").strip()
        if preset_key:
            self._key.setText(preset_key)
        st = AppState.get()
        name = str(st.display_name or st.username or "").strip()
        if name:
            self._user.setText(name)

    def _set_status(self, text: str, *, visible: bool = True) -> None:
        self._status.setText(text)
        self._status.setVisible(visible and bool(text.strip()))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._btn_activate.setEnabled(not busy)
        self._key.setEnabled(not busy)
        self._user.setEnabled(not busy)
        self._btn_activate.setText("激活中…" if busy else "确认激活")
        if busy:
            self._set_status("正在联网激活，请稍候…")
        else:
            self._set_status("", visible=False)

    def _on_go_purchase(self) -> None:
        shell = _shell_parent(self)
        self.reject()

        def _open() -> None:
            open_purchase_dialog(shell or self, forced=False)

        QTimer.singleShot(0, _open)

    def _on_activate(self) -> None:
        if self._busy:
            return
        key = self._key.text().strip().replace(" ", "")
        if not key or key.startswith("[") or "粘贴" in key:
            show_warning(self, "请粘贴完整授权码。")
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
            show_error(self, msg or "激活失败")
            return
        name = str((payload or {}).get("name") or self._user.text().strip() or "用户")
        role = str((payload or {}).get("role") or "user")
        AppState.get().set_user(name, name, role=role)
        emit_license_changed()
        self._summary.refresh()
        show_success(self, msg or "授权已更新")
        self._completed = True
        self.accept()

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None


class PurchasePlanDialog(BaseDialog):
    """购买产品套餐：选方案 · 手机号 · 一键开通。"""

    dialog_kind = "large"

    def __init__(
        self,
        parent=None,
        *,
        reason: str = "",
        module_id: str = "",
        forced: bool = False,
    ) -> None:
        super().__init__(parent)
        self._reason = str(reason or "")
        self._module_id = str(module_id or "")
        self._forced = bool(forced)
        self._completed = False
        self._lm = global_license_manager

        self._headline = intent_headline(
            intent=classify_intent(reason=self._reason, module_id=self._module_id),
            module_id=self._module_id,
            reason=self._reason,
        )

        self.setWindowTitle("购买产品套餐" if not self._forced else "续费升级")
        root = QVBoxLayout(self)
        apply_dialog_root(root)

        fg = _hero_color()
        warn = self._forced or self._lm.is_expired_standalone() or self._lm.is_expired_trial()
        self._banner = SemanticLabel(self._headline, kind="warning" if warn else "info")
        root.addWidget(self._banner)

        add_dialog_hero(
            root,
            pixmap=icon_pixmap("package", color=fg, size=48, parent=self),
            title="购买产品套餐",
            subtitle=self._headline,
            icon_size=48,
        )

        self._summary = _AccountSummarySection(self)
        root.addWidget(self._summary)

        from services.user_plan_presentation import AUTH_TIER_LABEL, OFFICIAL_TIER_LABEL, user_plan_tier

        tier = user_plan_tier()
        if tier in (AUTH_TIER_LABEL, OFFICIAL_TIER_LABEL) and not self._forced:
            root.addWidget(
                SemanticLabel(
                    f"当前已是「{tier}」。此处用于续费/升级套餐；日常功能无需再购买。",
                    kind="info",
                )
            )

        purchase_sec = FormSection("选择套餐")
        self._purchase = CommercePurchasePanel(self, show_portal=False)
        self._purchase.completed.connect(self._on_purchase_done)
        purchase_sec.add_widget(self._purchase)
        root.addWidget(purchase_sec)

        actions = DialogButtonRow()
        if self._forced:
            actions.add_secondary("稍后再说", self.reject)
        else:
            actions.add_secondary("关闭", self.accept)
        actions.add_secondary("我有授权码", self._on_go_license)
        root.addWidget(actions)

    @property
    def completed(self) -> bool:
        return self._completed

    def apply_context(self, *, reason: str = "", module_id: str = "", forced: bool | None = None) -> None:
        if reason:
            self._reason = str(reason)
        if module_id:
            self._module_id = str(module_id)
        if forced is not None:
            self._forced = bool(forced)
        self._headline = intent_headline(
            intent=classify_intent(reason=self._reason, module_id=self._module_id),
            module_id=self._module_id,
            reason=self._reason,
        )
        self._banner.setText(self._headline)
        warn = self._forced or self._lm.is_expired_standalone() or self._lm.is_expired_trial()
        self._banner.setProperty("class", f"semantic-{'warning' if warn else 'info'}")
        self._banner.style().unpolish(self._banner)
        self._banner.style().polish(self._banner)
        self._summary.refresh()

    def refresh_view(self) -> None:
        self._summary.refresh()
        if hasattr(self, "_purchase") and hasattr(self._purchase, "refresh"):
            self._purchase.refresh()

    def _on_purchase_done(self) -> None:
        self._completed = True
        emit_license_changed()
        self._summary.refresh()
        if self._forced:
            self.accept()

    def _on_go_license(self) -> None:
        shell = _shell_parent(self)
        self.reject()

        def _open() -> None:
            open_license_dialog(shell or self)

        QTimer.singleShot(0, _open)


class AccountOverviewDialog(BaseDialog):
    """我的账号：查看状态，进入录入授权或购买套餐。"""

    dialog_kind = "account"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._completed = False

        st = AppState.get()
        display = str(st.display_name or st.username or "用户").strip() or "用户"

        self.setWindowTitle("我的账号")
        root = QVBoxLayout(self)
        apply_dialog_root(root)

        fg = _hero_color()
        root.addWidget(SemanticLabel("安装即用，到期后在此续费升级。", kind="info"))
        hero_row = QHBoxLayout()
        hero_row.setSpacing(14)
        mark = QLabel()
        mark.setFixedSize(48, 48)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icon_pixmap("user", color=fg, size=48, parent=self))
        hero_row.addWidget(mark)
        hero_col = QVBoxLayout()
        hero_col.setSpacing(4)
        self._hero_title = PageTitle(display)
        self._hero_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hero_col.addWidget(self._hero_title)
        self._hero_subtitle = HintLabel(user_account_subtitle())
        hero_col.addWidget(self._hero_subtitle)
        hero_row.addLayout(hero_col, 1)
        root.addLayout(hero_row)

        self._summary = _AccountSummarySection(self)
        root.addWidget(self._summary)

        actions = DialogButtonRow()
        actions.add_secondary("关闭", self.accept)
        actions.add_secondary("录入授权", self._on_license)
        actions.add_primary("购买套餐", self._on_purchase)
        actions.add_secondary("退出登录", self._on_sign_out)
        root.addWidget(actions)

    @property
    def completed(self) -> bool:
        return self._completed

    def refresh_view(self) -> None:
        self._hero_subtitle.setText(user_account_subtitle())
        self._summary.refresh()

    def _on_license(self) -> None:
        shell = _shell_parent(self)
        self.accept()

        def _open() -> None:
            open_license_dialog(shell or self)

        QTimer.singleShot(0, _open)

    def _on_purchase(self) -> None:
        shell = _shell_parent(self)
        self.accept()

        def _open() -> None:
            open_purchase_dialog(shell or self, forced=False)

        QTimer.singleShot(0, _open)

    def _on_sign_out(self) -> None:
        if not ask_confirm(self, "退出当前账号？将返回登录界面。"):
            return
        shell = _shell_parent(self)
        self.accept()
        if shell is not None and hasattr(shell, "_sign_out_user"):
            shell._sign_out_user(confirmed=True)


def open_license_dialog(parent) -> bool:
    """打开录入授权弹窗（全局唯一）。"""

    def _factory() -> LicenseActivateDialog:
        dlg = LicenseActivateDialog(parent)
        dlg.refresh_view()
        return dlg

    return _CommerceWindowHub.present("license", parent, _factory)


def open_purchase_dialog(
    parent,
    *,
    reason: str = "",
    module_id: str = "",
    forced: bool = True,
) -> bool:
    """打开购买产品套餐弹窗（全局唯一）。"""

    ctx = {"reason": reason, "module_id": module_id, "forced": forced}

    def _factory() -> PurchasePlanDialog:
        dlg = PurchasePlanDialog(parent, reason=reason, module_id=module_id, forced=forced)
        dlg.refresh_view()
        return dlg

    def _apply(dlg: BaseDialog) -> None:
        if isinstance(dlg, PurchasePlanDialog):
            dlg.apply_context(**ctx)

    return _CommerceWindowHub.present("purchase", parent, _factory, apply_context=_apply)


def open_account_dialog(parent) -> bool:
    """打开我的账号弹窗（全局唯一）。"""

    def _factory() -> AccountOverviewDialog:
        dlg = AccountOverviewDialog(parent)
        dlg.refresh_view()
        return dlg

    return _CommerceWindowHub.present("account", parent, _factory)


def open_commerce_dialog(
    parent,
    *,
    mode: str = "account",
    reason: str = "",
    module_id: str = "",
    forced: bool = False,
) -> bool:
    """兼容旧入口：按 mode 路由到唯一弹窗。"""
    mode = str(mode or "account").strip().lower()
    if mode == "purchase":
        return open_purchase_dialog(parent, reason=reason, module_id=module_id, forced=forced)
    if mode in ("license", "activate", "code"):
        return open_license_dialog(parent)
    return open_account_dialog(parent)
