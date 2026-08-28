# -*- coding: utf-8 -*-
"""顶栏用户：账号摘要 + 授权状态（与关于弹窗同骨架）。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from app.app_state import AppState
from app.dialog_chrome import (
    add_dialog_hero,
    add_form_section,
    apply_dialog_root,
    make_info_form,
    value_label,
)
from app.version import APP_VERSION
from core.base_dialog import BaseDialog
from services.icon_registry import icon_pixmap
from services.license_client import license_service_summary
from services.license_manager import global_license_manager
from services.upgrade_flow import should_offer_purchase
from widgets import DialogButtonRow, HintLabel, SemanticLabel


class UserProfileDialog(BaseDialog):
    """展示当前登录用户与本机授权摘要。"""

    dialog_kind = "medium"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("用户与授权")
        st = AppState.get()
        lm = global_license_manager
        info = lm.get_license_info()
        licensed = bool(lm.is_licensed())
        self._can_upgrade = not licensed and should_offer_purchase(reason=lm.get_validity_text())

        root = QVBoxLayout(self)
        apply_dialog_root(root)

        display = str(st.display_name or st.username or "用户").strip() or "用户"
        pal = st.palette or {}
        fg = str(pal.get("primary") or pal.get("nav_fg") or "#2563EB")
        avatar_pm = icon_pixmap("user", color=fg, size=56, parent=self)
        add_dialog_hero(
            root,
            pixmap=avatar_pm,
            title=display,
            subtitle=f"登录名 {st.username or '—'} · TOA3 {APP_VERSION}",
            icon_size=56,
        )

        kind = "success" if licensed else "danger"
        status_text = lm.get_validity_text() or (
            "已授权" if licensed else "未授权 · 可一键开通完整版"
        )
        root.addWidget(SemanticLabel(status_text, kind=kind))

        lic = make_info_form()
        lic.addRow("授权状态", value_label("已授权" if licensed else "未授权 / 已失效"))
        lic.addRow("授权用户", value_label(str(info.get("user_name") or "—") or "—"))
        lic.addRow("到期日", value_label(str(info.get("expire_date") or "—") or "—"))
        days = lm.get_remaining_days()
        days_txt = "永久" if days == float("inf") else (f"{int(days)} 天" if licensed else "—")
        lic.addRow("剩余天数", value_label(days_txt))
        lic.addRow("功能范围", value_label(lm.format_features_summary()))
        add_form_section(root, "授权信息", lic)

        host = make_info_form()
        host.addRow("机器 ID", value_label(lm.get_machine_id(), selectable=True))
        try:
            cloud = license_service_summary() or "—"
        except Exception:
            cloud = "—"
        host.addRow("云服务", value_label(cloud, selectable=True))
        add_form_section(root, "本机", host)

        if self._can_upgrade:
            root.addWidget(
                HintLabel("点击「一键开通」或顶栏授权 Chip，支付后立即生效，无需粘贴授权码。")
            )
        elif not licensed:
            root.addWidget(HintLabel("开通与续费见「系统设置 → 激活与订阅」。"))

        actions = DialogButtonRow()
        if self._can_upgrade:
            actions.add_primary("一键开通", self._on_one_click_upgrade)
            actions.add_secondary("更多设置", self._open_license_settings)
            actions.add_secondary("关闭", self.accept)
        else:
            actions.add_secondary("打开相关设置", self._open_license_settings)
            actions.add_primary("关闭", self.accept)
        root.addWidget(actions)

    def _on_one_click_upgrade(self) -> None:
        from app.upgrade_offer_dialog import offer_upgrade_for_module

        if offer_upgrade_for_module(self, reason=global_license_manager.get_validity_text()):
            self.accept()

    def _open_license_settings(self) -> None:
        parent = self.parent()
        self.accept()
        shell = parent
        while shell is not None and not hasattr(shell, "navigate"):
            shell = shell.parent() if hasattr(shell, "parent") else None
        if shell is None:
            return
        if hasattr(shell, "open_subscription_settings"):
            shell.open_subscription_settings()
            return
        shell.navigate("system_settings")
        page = getattr(shell, "_pages", {}).get("system_settings")
        if page is not None and hasattr(page, "open_license_or_subscription"):
            page.open_license_or_subscription()
