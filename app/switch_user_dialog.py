# -*- coding: utf-8 -*-
"""快速切换本机已登记身份。"""
from __future__ import annotations

from PySide6.QtWidgets import QTableWidgetItem, QVBoxLayout

from app.app_state import AppState
from app.dialog_chrome import apply_dialog_root
from core.base_dialog import BaseDialog
from core.user_messages import show_error, show_info, show_warning
from services.license_manager import global_license_manager
from services.notify_bus import emit_license_changed
from widgets import DataTable, DialogButtonRow, HintLabel


class SwitchUserDialog(BaseDialog):
    dialog_kind = "account"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("切换身份")
        self._lm = global_license_manager
        self._users = self._lm.list_switchable_users()

        root = QVBoxLayout(self)
        apply_dialog_root(root)

        if not self._users:
            root.addWidget(
                HintLabel("暂无可切换账号。请先在「系统设置 → 授权」登记用户。")
            )
            actions = DialogButtonRow()
            actions.add_primary("关闭", self.reject)
            root.addWidget(actions)
            return

        root.addWidget(HintLabel("选择账号后切换；菜单与权限立即生效。"))

        self._table = DataTable()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["姓名", "角色", "有效期", "状态"])
        self._table.setSelectionBehavior(DataTable.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(DataTable.SelectionMode.SingleSelection)
        self._table.setEditTriggers(DataTable.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setRowCount(len(self._users))

        cur_name = str(self._lm.get_license_info().get("user_name") or "").strip()
        cur_phone = str(self._lm.get_license_info().get("phone") or "").strip()
        select_row = 0
        for row, user in enumerate(self._users):
            name = str(user.get("name") or "—")
            role = str(user.get("role") or "user")
            role_txt = "管理员" if role == "admin" else "用户"
            exp = str(user.get("expire_date") or "—")
            if self._lm.is_current_authorized_user(name, str(user.get("phone") or "")):
                status = "当前"
                select_row = row
            elif user.get("revoked"):
                status = "已吊销"
            else:
                status = "可切换"
            for col, text in enumerate((name, role_txt, exp, status)):
                self._table.setItem(row, col, QTableWidgetItem(text))
        self._table.selectRow(select_row)
        self._table.resizeColumnsToContents()
        root.addWidget(self._table, 1)

        actions = DialogButtonRow()
        actions.add_secondary("取消", self.reject)
        btn_switch = actions.add_primary("切换", self._on_switch)
        root.addWidget(actions)
        btn_switch.setDefault(True)

        self._table.itemDoubleClicked.connect(lambda *_: self._on_switch())

    def _selected_user(self) -> dict | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._users):
            return None
        return self._users[row]

    def _on_switch(self) -> None:
        user = self._selected_user()
        if not user:
            show_warning(self, "请先选择要切换的账号。")
            return
        name = str(user.get("name") or "").strip()
        phone = str(user.get("phone") or "").strip()
        if self._lm.is_current_authorized_user(name, phone):
            show_info(self, f"当前已是「{name}」。", title="切换身份")
            self.accept()
            return
        ok, msg, info = self._lm.switch_to_authorized_user(name, phone)
        if not ok or not info:
            show_error(self, msg or "切换失败", title="切换身份")
            return
        AppState.get().set_user(
            str(info.get("name") or name),
            str(info.get("name") or name),
            role=str(info.get("role") or "user"),
        )
        emit_license_changed()
        shell = self._shell()
        if shell is not None:
            if hasattr(shell, "refresh_brand_chrome"):
                shell.refresh_brand_chrome()
            if hasattr(shell, "show_status"):
                shell.show_status(msg or f"已切换为 {name}")
        self.accept()

    def _shell(self):
        w = self.parent()
        while w is not None and not hasattr(w, "navigate"):
            w = w.parent() if hasattr(w, "parent") else None
        return w
