# -*- coding: utf-8 -*-
"""系统设置 · 授权与云服务联动。"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_error, show_info, show_warning
from services.license_client import license_service_summary
from services.license_manager import global_license_manager
from services.menu_registry import all_menu_items
from services.notify_bus import emit_license_changed
from widgets import FormSection, HintLabel, PrimaryButton, ReadOnlyPlainTextEdit, SecondaryButton, SemanticLabel
from widgets.list_edit import FormEditDialog, ListPanel, confirm_delete


class LicenseSection(FormSection):
    """授权状态 + 授权用户名单（List+Edit）。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__("授权与云服务")
        self._page = parent
        self._lm = global_license_manager

        self._status = SemanticLabel("", kind="info")
        self._refresh_status()
        self.add_widget(self._status)
        hint_lines = [
            f"云服务：{license_service_summary()} · 机器 ID：{self._lm.get_machine_id()}",
        ]
        if self._lm.is_standalone_mode() and not self._lm.is_licensed():
            hint_lines.append(
                "当前为单机基础版（离线可用）。升级完整版：切到「订阅购买」页下单，或使用「授权码登录」。"
            )
        elif not self._lm.is_licensed():
            hint_lines.append("未激活完整版：切到「订阅购买」页订阅功能包，或在登录窗使用授权码。")
        else:
            hint_lines.append("授权用户维护后请点「同步到云服务」；到期后收费功能自动关闭，可在此页续订。")
        self.add_widget(HintLabel("\n".join(hint_lines)))

        self._list_panel = ListPanel(
            hint="双击或点「编辑」修改授权用户；固定管理员不可删除。",
            add_label="新增用户",
            edit_label="编辑",
            delete_label="删除",
            refresh_label="刷新名单",
        )
        self._list_panel.list_widget.itemDoubleClicked.connect(self._on_edit)
        self._list_panel.bind_add(self._on_add)
        self._list_panel.bind_edit(self._on_edit)
        self._list_panel.bind_delete(self._on_delete)
        self._list_panel.bind_refresh(self._reload_list)
        self.add_widget(self._list_panel)

        row = QHBoxLayout()
        btn_sync = PrimaryButton("同步到云服务")
        btn_sync.clicked.connect(self._on_sync_dms)
        row.addWidget(btn_sync)
        btn_check = SecondaryButton("联网校验")
        btn_check.clicked.connect(self._on_check)
        row.addWidget(btn_check)
        row.addStretch(1)
        self.add_layout(row)

        self.add_widget(HintLabel("功能清单（菜单 feature / 是否需授权）"))
        self._features = ReadOnlyPlainTextEdit()
        self._features.setMinimumHeight(100)
        self.add_widget(self._features)
        self._reload_features()

        self.add_widget(HintLabel("可售功能包（SKU）— 发卡时可写 pack_id"))
        self._packs = ReadOnlyPlainTextEdit()
        self._packs.setMinimumHeight(90)
        self.add_widget(self._packs)
        try:
            from services.feature_packs import pack_summary_lines

            self._packs.setPlainText("\n".join(pack_summary_lines()) or "（无功能包配置）")
        except Exception as e:
            self._packs.setPlainText(f"加载失败：{e}")

        self._reload_list()

    def _reload_features(self) -> None:
        lines = []
        for it in all_menu_items():
            mid = it.get("id")
            name = it.get("name")
            req = it.get("requires_license", True)
            feat = it.get("feature_id") or it.get("requires_feature") or mid
            lines.append(f"{mid}\t{name}\tfeature={feat}\trequires_license={req}")
        self._features.setPlainText("\n".join(lines))

    def _emit_nav(self) -> None:
        emit_license_changed()
        self._refresh_status()


    def _refresh_status(self) -> None:
        text = self._lm.get_validity_text()
        licensed = self._lm.is_licensed()
        kind = "success" if licensed else "danger"
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.setText(f"授权状态：{text}")

    def _reload_list(self) -> None:
        users = self._lm.search_authorized_users("")
        lines = []
        for u in users:
            lines.append(self._lm.format_authorized_user(u))
        self._list_panel.set_items(lines)
        self._refresh_status()
        self._page.report_status(f"授权用户 {len(lines)} 人")

    def _user_at_row(self) -> dict | None:
        row = self._list_panel.current_row()
        users = self._lm.search_authorized_users("")
        if 0 <= row < len(users):
            return users[row]
        return None

    def _on_add(self) -> None:
        dlg = FormEditDialog(
            self._page,
            title="新增授权用户",
            fields=[
                ("姓名", "name"),
                ("手机", "phone"),
                ("角色 user/admin", "role"),
                ("有效天数", "days"),
            ],
        )
        dlg.set_values({"role": "user", "days": "365"})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.values()
        name = data.get("name") or ""
        phone = data.get("phone") or ""
        if not name:
            show_warning(self._page, "姓名不能为空。")
            return
        try:
            days = int(data.get("days") or "365")
        except ValueError:
            days = 365
        ok, msg, _code = self._lm.issue_license_code(
            name,
            phone,
            days=days,
            role=str(data.get("role") or "user"),
            bind_machine=True,
        )
        if not ok:
            show_error(self._page, msg or "发卡失败")
            return
        show_info(self._page, msg or "已新增授权用户")
        self._reload_list()
        self._emit_nav()

    def _on_edit(self) -> None:
        user = self._user_at_row()
        if not user:
            show_warning(self._page, "请先选择一名用户。")
            return
        dlg = FormEditDialog(
            self._page,
            title="编辑授权用户",
            fields=[
                ("姓名", "name"),
                ("手机", "phone"),
                ("角色", "role"),
            ],
        )
        dlg.set_values(user)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.values()
        ok, msg, _ = self._lm.update_authorized_user(
            str(user.get("name") or ""),
            str(user.get("phone") or ""),
            name=data.get("name"),
            phone=data.get("phone"),
            role=data.get("role"),
        )
        if not ok:
            show_error(self._page, msg or "更新失败")
            return
        show_info(self._page, "已更新")
        self._reload_list()
        self._emit_nav()

    def _on_delete(self) -> None:
        user = self._user_at_row()
        if not user:
            show_warning(self._page, "请先选择要删除的用户。")
            return
        if self._lm.is_protected_admin(user):
            show_warning(self._page, "固定管理员不可删除。")
            return
        name = str(user.get("name") or "")
        phone = str(user.get("phone") or "")
        if not confirm_delete(self._page, f"用户 {name}"):
            return
        if not self._lm.remove_authorized_user(name, phone):
            show_error(self._page, "删除失败（可能为受保护账号）。")
            return
        self._reload_list()
        self._page.report_status("已删除授权用户", level=StatusLevel.SUCCESS)
        self._emit_nav()

    def _on_sync_dms(self) -> None:
        def _run() -> None:
            ok_n, fail_n, summary = self._lm.sync_all_authorized_users_to_dms()
            show_info(self._page, f"同步完成：成功 {ok_n}，失败 {fail_n}\n{summary}")
            self._emit_nav()

        self._page.run_safe(_run, success_status="云服务同步完成")

    def _on_check(self) -> None:
        self._lm.reload_from_disk()
        licensed = self._lm.is_licensed()
        self._refresh_status()
        self._emit_nav()
        show_info(self._page, self._lm.get_validity_text() if licensed else "当前未授权或已失效")
