# -*- coding: utf-8 -*-
"""系统设置 · 授权与云服务联动。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_error, show_info, show_warning
from services.license_client import license_service_summary
from services.license_manager import global_license_manager
from services.notify_bus import emit_license_changed
from services.user_plan_presentation import (
    dev_build_tag,
    is_dev_build,
    user_account_subtitle,
)
from widgets import (
    DataTable,
    DangerButton,
    FormSection,
    HintLabel,
    LineEdit,
    PrimaryButton,
    SecondaryButton,
    SemanticLabel,
)
from widgets.list_edit import FormEditDialog, confirm_delete


class _CloudCheckWorker(QObject):
    finished = Signal(bool, str)

    def run(self) -> None:
        try:
            ok, msg = global_license_manager.force_cloud_license_check()
            self.finished.emit(bool(ok), str(msg or ""))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class _CloudSyncWorker(QObject):
    finished = Signal(object)

    def run(self) -> None:
        try:
            self.finished.emit(global_license_manager.sync_all_authorized_users_to_dms())
        except Exception as exc:
            self.finished.emit(exc)


_USER_COLS = ("姓名", "手机", "角色", "有效期", "状态", "功能权限")

_CLOUD_HINT = (
    "云服务地址与机器 ID 只读；产品方案与订单见「运营台与商业 → 运营台」。"
)


def _join_dev_status(tag: str, detail: str) -> str:
    detail = str(detail or "").strip()
    if not detail:
        return tag
    if detail.startswith(tag):
        return detail
    return f"{tag} · {detail}"


class LicenseSection(QWidget):
    """本机授权用户 + 云服务连接（SKU/定价见运营台）。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        self._lm = global_license_manager
        self._users: list[dict] = []
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._cloud_busy = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._status = SemanticLabel("", kind="info")
        root.addWidget(self._status)

        users = FormSection("授权用户")
        users.add_widget(HintLabel("本机名单维护；同步推云、联网校验拉回。"))

        tool_crud = QHBoxLayout()
        tool_crud.setSpacing(8)
        btn_add = PrimaryButton("新增用户")
        btn_add.clicked.connect(self._on_add)
        tool_crud.addWidget(btn_add)
        btn_edit = SecondaryButton("编辑")
        btn_edit.clicked.connect(self._on_edit)
        tool_crud.addWidget(btn_edit)
        btn_del = DangerButton("删除")
        btn_del.clicked.connect(self._on_delete)
        tool_crud.addWidget(btn_del)
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(self._reload_list)
        tool_crud.addWidget(btn_refresh)
        tool_crud.addStretch(1)
        users.add_layout(tool_crud)

        tool_cloud = QHBoxLayout()
        tool_cloud.addStretch(1)
        btn_sync = PrimaryButton("同步到云服务")
        btn_sync.clicked.connect(self._on_sync_dms)
        tool_cloud.addWidget(btn_sync)
        self._btn_sync = btn_sync
        btn_check = SecondaryButton("联网校验")
        btn_check.clicked.connect(self._on_check)
        tool_cloud.addWidget(btn_check)
        self._btn_check = btn_check
        users.add_layout(tool_cloud)

        self._user_table = DataTable()
        self._user_table.set_headers(list(_USER_COLS))
        self._user_table.setMinimumHeight(280)
        self._user_table.itemDoubleClicked.connect(self._on_edit)
        users.add_widget(self._user_table, 1)
        root.addWidget(users, 1)

        cloud = FormSection("云服务连接")
        cloud.add_widget(HintLabel(_CLOUD_HINT))
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
        cloud.add_layout(env)
        root.addWidget(cloud)

        self._refresh_status()
        self._reload_list()

    def _copy_machine_id(self) -> None:
        QGuiApplication.clipboard().setText(self._machine_id.text().strip())
        self._page.report_status("机器 ID 已复制", level=StatusLevel.SUCCESS)

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
        # 正式版不在授权页重复顶栏/账号档位摘要；开发构建保留便于联调
        if not is_dev_build():
            self._status.setVisible(False)
            self._status.clear()
            return
        self._status.setVisible(True)
        text = user_account_subtitle()
        tag = dev_build_tag()
        if tag:
            text = _join_dev_status(tag, text)
        licensed = self._lm.is_licensed()
        kind = "success" if licensed else "danger"
        self._status.setProperty("class", f"semantic-{kind}")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.setText(text)

    def _reload_list(self, *, report_count: bool = True) -> None:
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
        if report_count:
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

    def _emit_nav_deferred(self) -> None:
        """授权变更通知延后到事件循环下一拍，避免与云操作回调同栈重建壳层。"""
        QTimer.singleShot(0, emit_license_changed)

    def _set_cloud_busy(self, busy: bool, label: str = "") -> None:
        self._cloud_busy = busy
        for btn in (getattr(self, "_btn_sync", None), getattr(self, "_btn_check", None)):
            if btn is not None:
                btn.setEnabled(not busy)
        if busy:
            self._page.report_status(label or "云服务操作中…", level=StatusLevel.INFO)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _start_worker(self, worker: QObject, *, busy_label: str, on_done) -> None:
        if self._cloud_busy or (self._thread is not None and self._thread.isRunning()):
            show_warning(self._page, "云服务操作进行中，请稍候。")
            return
        self._set_cloud_busy(True, busy_label)
        self._thread = QThread(self)
        self._worker = worker
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        def _finished(*args) -> None:
            try:
                on_done(*args)
            finally:
                self._set_cloud_busy(False)
                if self._thread is not None:
                    self._thread.quit()

        worker.finished.connect(_finished, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _on_sync_dms(self) -> None:
        worker = _CloudSyncWorker()

        def _done(result) -> None:
            if isinstance(result, Exception):
                self._page.report_status(f"同步失败：{result}", level=StatusLevel.ERROR)
                return
            ok_n, fail_n, summary = result
            self._reload_list(report_count=False)
            if fail_n:
                detail = summary.replace("\n", " · ") if summary else ""
                self._page.report_status(
                    f"同步完成：成功 {ok_n}，失败 {fail_n} · {detail}",
                    level=StatusLevel.WARNING,
                )
            else:
                self._page.report_status(
                    f"同步完成：成功 {ok_n} 条",
                    level=StatusLevel.SUCCESS,
                )
            self._emit_nav_deferred()

        self._start_worker(worker, busy_label="正在同步到云服务…", on_done=_done)

    def _on_check(self) -> None:
        worker = _CloudCheckWorker()

        def _done(ok: bool, msg: str) -> None:
            self._refresh_status()
            if ok:
                self._page.report_status(msg or "联网校验完成", level=StatusLevel.SUCCESS)
            else:
                self._page.report_status(msg or "联网校验未通过", level=StatusLevel.WARNING)
            self._emit_nav_deferred()

        self._start_worker(worker, busy_label="正在联网校验…", on_done=_done)
