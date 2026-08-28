# -*- coding: utf-8 -*-
"""系统设置 · 授权与云服务联动。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_error, show_info, show_warning
from services.license_client import license_service_summary
from services.license_manager import global_license_manager
from services.menu_registry import all_menu_items
from services.notify_bus import emit_license_changed
from widgets import (
    DataTable,
    DangerButton,
    HintLabel,
    LineEdit,
    PrimaryButton,
    SecondaryButton,
    SemanticLabel,
    TabWidget,
)
from widgets.list_edit import FormEditDialog, confirm_delete

_USER_COLS = ("姓名", "手机", "角色", "有效期", "状态", "功能权限")
_MENU_COLS = ("模块", "显示名", "需完整版")
_PACK_COLS = ("包 ID", "名称", "功能数", "说明")

_CLOUD_HINT = (
    "【本机 ↔ TOA 云服务】\n"
    "· 本页「授权用户」= 本机发码/续期操作台；名单存在本机 license 数据里。\n"
    "· 「同步到云服务」= 把名单推到 TOA 云服务（下方地址），供激活校验、到期判定、"
    "试用/续订与运营台审计；不是 DMS 业务库。\n"
    "· 「联网校验」= 从云服务拉最新授权状态写回本机 license.json，侧栏权限随即刷新。\n"
    "· 单机基础版可不连云，仅用本机激活码；完整版/多用户发卡建议配置云服务。\n"
    "· 机器 ID 用于绑机发码；复制后可在运营台或发卡流程中登记。"
)


class LicenseSection(QWidget):
    """授权状态 + 用户名单（主表）+ 运营参考 / 云服务说明（子页签）。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._lm = global_license_manager
        self._users: list[dict] = []

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._status = SemanticLabel("", kind="info")
        root.addWidget(self._status)

        self._tabs = TabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tabs.addTab(self._build_users_tab(), "授权用户")
        self._tabs.addTab(self._build_reference_tab(), "运营参考")
        self._tabs.addTab(self._build_cloud_tab(), "云服务连接")
        root.addWidget(self._tabs, 1)

        self._refresh_status()
        self._reload_list()

    def _build_users_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)

        lay.addWidget(
            HintLabel(
                "维护本机授权名单；改完后点「同步到云服务」写入云端，或点「联网校验」从云端拉回。"
            )
        )

        tool = QHBoxLayout()
        tool.setSpacing(8)
        btn_add = PrimaryButton("新增用户")
        btn_add.clicked.connect(self._on_add)
        tool.addWidget(btn_add)
        btn_edit = SecondaryButton("编辑")
        btn_edit.clicked.connect(self._on_edit)
        tool.addWidget(btn_edit)
        btn_del = DangerButton("删除")
        btn_del.clicked.connect(self._on_delete)
        tool.addWidget(btn_del)
        tool.addStretch(1)
        btn_refresh = SecondaryButton("刷新名单")
        btn_refresh.clicked.connect(self._reload_list)
        tool.addWidget(btn_refresh)
        btn_sync = PrimaryButton("同步到云服务")
        btn_sync.clicked.connect(self._on_sync_dms)
        tool.addWidget(btn_sync)
        btn_check = SecondaryButton("联网校验")
        btn_check.clicked.connect(self._on_check)
        tool.addWidget(btn_check)
        lay.addLayout(tool)

        self._user_table = DataTable()
        self._user_table.set_headers(list(_USER_COLS))
        self._user_table.setMinimumHeight(320)
        self._user_table.itemDoubleClicked.connect(self._on_edit)
        lay.addWidget(self._user_table, 1)
        return w

    def _build_reference_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(
            HintLabel("发卡、订阅对照用：各模块是否要求完整版，以及可售功能包 SKU。")
        )

        inner = TabWidget()
        inner.setDocumentMode(True)
        inner.addTab(self._build_menu_tab(), "菜单授权对照")
        inner.addTab(self._build_pack_tab(), "功能包 SKU")
        lay.addWidget(inner, 1)
        return w

    def _build_cloud_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(HintLabel(_CLOUD_HINT))

        env = QFormLayout()
        env.setSpacing(6)
        self._service_url = LineEdit()
        self._service_url.setReadOnly(True)
        self._service_url.setText(license_service_summary())
        env.addRow("云服务 API", self._service_url)

        mid_row = QHBoxLayout()
        self._machine_id = LineEdit()
        self._machine_id.setReadOnly(True)
        self._machine_id.setText(self._lm.get_machine_id())
        mid_row.addWidget(self._machine_id, 1)
        btn_copy = SecondaryButton("复制机器 ID")
        btn_copy.clicked.connect(self._copy_machine_id)
        mid_row.addWidget(btn_copy)
        env.addRow("机器 ID", mid_row)
        lay.addLayout(env)
        lay.addStretch(1)
        return w

    def _build_menu_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)
        self._menu_table = DataTable()
        self._menu_table.set_headers(list(_MENU_COLS))
        lay.addWidget(self._menu_table, 1)
        self._reload_menu_table()
        return w

    def _build_pack_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)
        self._pack_table = DataTable()
        self._pack_table.set_headers(list(_PACK_COLS))
        lay.addWidget(self._pack_table, 1)
        self._reload_pack_table()
        return w

    def _copy_machine_id(self) -> None:
        QGuiApplication.clipboard().setText(self._machine_id.text().strip())
        self._page.report_status("机器 ID 已复制", level=StatusLevel.SUCCESS)

    def _reload_menu_table(self) -> None:
        rows: list[tuple[str, ...]] = []
        for it in all_menu_items():
            if not it.get("show", True):
                continue
            mid = str(it.get("id") or "")
            name = str(it.get("name") or mid)
            req = it.get("requires_license", True)
            rows.append((mid, name, "是" if req else "否"))
        self._menu_table.set_rows(rows)

    def _reload_pack_table(self) -> None:
        rows: list[tuple[str, ...]] = []
        try:
            from services.feature_packs import expand_features, list_packs

            for p in list_packs(sellable_only=True):
                feats = expand_features([p["id"]])
                n = "全部" if feats == ["all"] else str(len(feats))
                rows.append(
                    (
                        str(p.get("id") or ""),
                        str(p.get("name") or ""),
                        n,
                        str(p.get("desc") or ""),
                    )
                )
        except Exception as exc:
            rows.append(("—", "加载失败", "", str(exc)))
        self._pack_table.set_rows(rows)

    def _user_role_label(self, user: dict) -> str:
        role = str(user.get("role") or "").strip().lower()
        if role == "admin":
            if self._lm.is_protected_admin(user):
                return "管理员（固定）"
            return "管理员"
        return "用户"

    def _user_status_label(self, user: dict) -> str:
        if bool(user.get("revoked")):
            return "已吊销"
        if user.get("code_id"):
            return "已发卡"
        return "待发卡"

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
        cloud = "云服务已确认" if licensed and not self._lm.is_standalone_mode() else ""
        parts = [f"授权状态：{text}"]
        if cloud:
            parts.append(cloud)
        self._status.setText(" · ".join(parts))

    def _reload_list(self) -> None:
        self._users = self._lm.search_authorized_users("")
        table_rows: list[tuple[str, ...]] = []
        for user in self._users:
            feats = self._lm.format_features_summary(
                user.get("features") or user.get("menus")
            )
            table_rows.append(
                (
                    str(user.get("name") or "未命名"),
                    str(user.get("phone") or ""),
                    self._user_role_label(user),
                    str(user.get("expire_date") or "—"),
                    self._user_status_label(user),
                    feats,
                )
            )
        self._user_table.set_rows(table_rows)
        for r, user in enumerate(self._users):
            for c in range(self._user_table.columnCount()):
                item = self._user_table.item(r, c)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, user)
        if self._users:
            self._user_table.selectRow(0)
        self._refresh_status()
        self._page.report_status(f"授权用户 {len(self._users)} 人")

    def _user_at_row(self) -> dict | None:
        r = self._user_table.currentRow()
        if 0 <= r < len(self._users):
            return self._users[r]
        item = self._user_table.item(r, 0) if r >= 0 else None
        if item is not None:
            meta = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(meta, dict):
                return meta
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
        show_info(
            self._page,
            self._lm.get_validity_text() if licensed else "当前未授权或已失效",
        )
