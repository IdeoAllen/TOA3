# -*- coding: utf-8 -*-
"""邮箱代理：本机 IMAP/SMTP 工作台（show:false · MVP）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.email_client import email_client_service as svc
from widgets import (
    CheckBox,
    ComboBox,
    FormRow,
    FormSection,
    HintLabel,
    LineEdit,
    ListWidget,
    PageHeader,
    PasswordLineEdit,
    PlainTextEdit,
    PrimaryButton,
    ProgressBar,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SoftActivityBar,
    SpinBox,
)

_LABEL_W = 88
_FOLDERS = (
    ("inbox", "收件箱"),
    ("sent", "已发送"),
    ("trash", "已删除"),
)


class _Worker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(bool, object)

    def __init__(self, kind: str, payload: dict | None = None) -> None:
        super().__init__()
        self._kind = kind
        self._payload = payload or {}

    def run(self) -> None:
        def _prog(msg: str, cur: int, total: int) -> None:
            self.progress.emit(msg, cur, total)

        try:
            if self._kind == "bind":
                ok, diag, acc = svc.bind_account(
                    self._payload.get("form") or {},
                    self._payload.get("password") or "",
                    verify=True,
                    progress=_prog,
                )
                self.finished.emit(ok, {"diagnosis": diag, "account": acc})
            elif self._kind == "sync":
                ok, status, meta = svc.sync_now(progress=_prog)
                self.finished.emit(ok, {"status": status, "meta": meta})
            elif self._kind == "send":
                ok, diag = svc.send_now(
                    to_addrs=self._payload.get("to_addrs") or [],
                    subject=self._payload.get("subject") or "",
                    body_text=self._payload.get("body_text") or "",
                    cc_addrs=self._payload.get("cc_addrs") or [],
                    attachment_paths=self._payload.get("attachments") or [],
                    progress=_prog,
                )
                self.finished.emit(ok, {"diagnosis": diag})
            else:
                self.finished.emit(False, {"diagnosis": {"human": f"未知任务 {self._kind}"}})
        except Exception as exc:
            self.finished.emit(False, {"diagnosis": {"human": str(exc), "title": "异常"}})


class EmailClientPage(BasePage):
    page_id = "email_client"
    page_title = "邮箱代理"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._busy = False
        self._folder_role = "inbox"
        self._msg_ids: list[str] = []
        self._html_view = None
        self._html_error = ""
        self._compose_files: list[str] = []

        svc.ensure_store()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._activity = SoftActivityBar()
        outer.addWidget(self._activity)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack, 1)

        self._build_wizard()
        self._build_main()
        self._build_compose()

        self._refresh_entry(sync=False)
        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        if self._stack.currentIndex() == 0:
            return self._wiz_email
        return self._btn_sync

    # —— 绑定向导 ——
    def _build_wizard(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        lay.addWidget(scroll)
        root = scroll.content_layout

        root.addWidget(
            PageHeader(
                "绑定邮箱",
                "在办公套件内完成本机收发；请使用授权码/应用密码，不是网页登录密码。",
            )
        )

        box = FormSection("账户")
        self._wiz_provider = ComboBox()
        for p in svc.presets():
            self._wiz_provider.addItem(str(p.get("name") or p["id"]), p["id"])
        self._wiz_provider.currentIndexChanged.connect(self._on_provider_changed)
        box.add_widget(FormRow("邮箱类型", self._wiz_provider, label_width=_LABEL_W))

        self._wiz_email = LineEdit()
        self._wiz_email.setPlaceholderText("name@example.com")
        box.add_widget(FormRow("邮箱地址", self._wiz_email, label_width=_LABEL_W))

        self._wiz_password = PasswordLineEdit()
        self._wiz_password.setPlaceholderText("授权码 / 应用密码")
        box.add_widget(FormRow("授权码", self._wiz_password, label_width=_LABEL_W))

        self._wiz_hint = HintLabel("")
        self._wiz_hint.setWordWrap(True)
        box.add_widget(self._wiz_hint)
        root.addWidget(box)

        adv = FormSection("服务器（可手改）")
        self._wiz_imap_host = LineEdit()
        self._wiz_imap_port = SpinBox()
        self._wiz_imap_port.setRange(1, 65535)
        self._wiz_imap_ssl = CheckBox("IMAP SSL")
        self._wiz_smtp_host = LineEdit()
        self._wiz_smtp_port = SpinBox()
        self._wiz_smtp_port.setRange(1, 65535)
        self._wiz_smtp_ssl = CheckBox("SMTP SSL")
        self._wiz_smtp_starttls = CheckBox("SMTP STARTTLS")
        adv.add_widget(FormRow("IMAP 主机", self._wiz_imap_host, label_width=_LABEL_W))
        adv.add_widget(FormRow("IMAP 端口", self._wiz_imap_port, label_width=_LABEL_W))
        adv.add_widget(self._wiz_imap_ssl)
        adv.add_widget(FormRow("SMTP 主机", self._wiz_smtp_host, label_width=_LABEL_W))
        adv.add_widget(FormRow("SMTP 端口", self._wiz_smtp_port, label_width=_LABEL_W))
        adv.add_widget(self._wiz_smtp_ssl)
        adv.add_widget(self._wiz_smtp_starttls)
        root.addWidget(adv)

        diag_box = FormSection("诊断")
        self._wiz_diag = ReadOnlyPlainTextEdit()
        self._wiz_diag.setPlaceholderText("绑定失败时，这里会给出可执行的下一步…")
        self._wiz_diag.setMinimumHeight(120)
        diag_box.add_widget(self._wiz_diag)
        root.addWidget(diag_box)

        row = QHBoxLayout()
        self._btn_bind = PrimaryButton("验证并绑定")
        self._btn_bind.clicked.connect(self._on_bind)
        row.addWidget(self._btn_bind)
        btn_retry = SecondaryButton("清空诊断")
        btn_retry.clicked.connect(lambda: self._wiz_diag.setPlainText(""))
        row.addWidget(btn_retry)
        row.addStretch(1)
        root.addLayout(row)

        self._on_provider_changed()
        self._stack.addWidget(page)

    def _on_provider_changed(self) -> None:
        pid = str(self._wiz_provider.currentData() or "custom")
        from services.mail.presets import apply_preset_to_account

        filled = apply_preset_to_account(pid, {})
        self._wiz_imap_host.setText(str(filled.get("imap_host") or ""))
        self._wiz_imap_port.setValue(int(filled.get("imap_port") or 993))
        self._wiz_imap_ssl.setChecked(bool(filled.get("imap_ssl", True)))
        self._wiz_smtp_host.setText(str(filled.get("smtp_host") or ""))
        self._wiz_smtp_port.setValue(int(filled.get("smtp_port") or 465))
        self._wiz_smtp_ssl.setChecked(bool(filled.get("smtp_ssl", True)))
        self._wiz_smtp_starttls.setChecked(bool(filled.get("smtp_starttls", False)))
        self._wiz_hint.setText(svc.provider_auth_hint(pid))

    def _wizard_form(self) -> dict:
        return {
            "provider_id": str(self._wiz_provider.currentData() or "custom"),
            "email": self._wiz_email.text().strip(),
            "imap_host": self._wiz_imap_host.text().strip(),
            "imap_port": int(self._wiz_imap_port.value()),
            "imap_ssl": self._wiz_imap_ssl.isChecked(),
            "smtp_host": self._wiz_smtp_host.text().strip(),
            "smtp_port": int(self._wiz_smtp_port.value()),
            "smtp_ssl": self._wiz_smtp_ssl.isChecked(),
            "smtp_starttls": self._wiz_smtp_starttls.isChecked(),
        }

    # —— 主三栏 ——
    def _build_main(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        lay.addWidget(scroll)
        root = scroll.content_layout

        root.addWidget(
            PageHeader(
                "邮箱代理",
                "本机收发 · 增量同步 · 凭证与通知通道分桶。",
            )
        )

        tools = QHBoxLayout()
        self._account_label = HintLabel("")
        tools.addWidget(self._account_label, 1)
        self._btn_sync = PrimaryButton("同步")
        self._btn_sync.clicked.connect(self._on_sync)
        tools.addWidget(self._btn_sync)
        btn_compose = SecondaryButton("写信")
        btn_compose.clicked.connect(lambda: self._stack.setCurrentIndex(2))
        tools.addWidget(btn_compose)
        btn_rebind = SecondaryButton("重新绑定")
        btn_rebind.clicked.connect(self._goto_wizard)
        tools.addWidget(btn_rebind)
        btn_unbind = SecondaryButton("解除绑定")
        btn_unbind.clicked.connect(self._on_unbind)
        tools.addWidget(btn_unbind)
        root.addLayout(tools)

        self._status_hint = HintLabel("进页不自动联网；点「同步」后台收取。")
        root.addWidget(self._status_hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = FormSection("文件夹")
        self._folder_list = ListWidget()
        for role, title in _FOLDERS:
            self._folder_list.addItem(title)
        self._folder_list.setCurrentRow(0)
        self._folder_list.currentRowChanged.connect(self._on_folder_changed)
        left.add_widget(self._folder_list)
        splitter.addWidget(left)

        mid = FormSection("邮件")
        self._msg_list = ListWidget()
        self._msg_list.setMinimumWidth(240)
        self._msg_list.currentRowChanged.connect(self._on_msg_selected)
        mid.add_widget(self._msg_list)
        splitter.addWidget(mid)

        right = FormSection("详情")
        self._detail_meta = HintLabel("")
        self._detail_meta.setWordWrap(True)
        right.add_widget(self._detail_meta)
        self._detail_text = ReadOnlyPlainTextEdit()
        self._detail_text.setMinimumHeight(160)
        right.add_widget(self._detail_text)

        self._html_host = QWidget()
        self._html_host.setMinimumHeight(180)
        html_lay = QVBoxLayout(self._html_host)
        html_lay.setContentsMargins(0, 0, 0, 0)
        self._html_fallback = HintLabel("纯文本正文；若有 HTML 将在页内私有预览中显示。")
        self._html_fallback.setWordWrap(True)
        html_lay.addWidget(self._html_fallback)
        right.add_widget(self._html_host)

        self._att_list = ListWidget()
        self._att_list.setMaximumHeight(90)
        right.add_widget(HintLabel("附件"))
        right.add_widget(self._att_list)
        att_row = QHBoxLayout()
        btn_save_att = SecondaryButton("导出附件")
        btn_save_att.clicked.connect(self._on_export_attachment)
        att_row.addWidget(btn_save_att)
        att_row.addStretch(1)
        right.add_layout(att_row)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 3)
        root.addWidget(splitter, 1)

        self._stack.addWidget(page)
        self._main_page = page

    def _build_compose(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        lay.addWidget(scroll)
        root = scroll.content_layout

        root.addWidget(PageHeader("写信", "纯文本正文优先；附件有大小上限与进度。"))

        box = FormSection("新邮件")
        self._cmp_to = LineEdit()
        self._cmp_to.setPlaceholderText("收件人，多个用逗号/分号分隔")
        box.add_widget(FormRow("收件人", self._cmp_to, label_width=_LABEL_W))
        self._cmp_cc = LineEdit()
        self._cmp_cc.setPlaceholderText("可选")
        box.add_widget(FormRow("抄送", self._cmp_cc, label_width=_LABEL_W))
        self._cmp_subject = LineEdit()
        box.add_widget(FormRow("主题", self._cmp_subject, label_width=_LABEL_W))
        self._cmp_body = PlainTextEdit()
        self._cmp_body.setPlaceholderText("正文（纯文本）")
        self._cmp_body.setMinimumHeight(200)
        box.add_widget(self._cmp_body)

        self._cmp_att_label = HintLabel("附件：无")
        box.add_widget(self._cmp_att_label)
        att_row = QHBoxLayout()
        btn_add = SecondaryButton("添加附件")
        btn_add.clicked.connect(self._on_add_attachment)
        att_row.addWidget(btn_add)
        btn_clear = SecondaryButton("清空附件")
        btn_clear.clicked.connect(self._clear_attachments)
        att_row.addWidget(btn_clear)
        att_row.addStretch(1)
        box.add_layout(att_row)

        self._send_progress = ProgressBar()
        self._send_progress.setRange(0, 100)
        self._send_progress.setValue(0)
        box.add_widget(self._send_progress)
        root.addWidget(box)

        row = QHBoxLayout()
        self._btn_send = PrimaryButton("发送")
        self._btn_send.clicked.connect(self._on_send)
        row.addWidget(self._btn_send)
        btn_back = SecondaryButton("返回收件箱")
        btn_back.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        row.addWidget(btn_back)
        row.addStretch(1)
        root.addLayout(row)

        limits = svc.attachment_limits()
        root.addWidget(
            HintLabel(f"单附件上限 {limits['max_single_mb']}MB；发送在后台线程，界面可继续操作。")
        )

        self._stack.addWidget(page)

    # —— 生命周期 ——
    def on_page_enter(self) -> None:
        # 进页不阻塞联网
        self._refresh_entry(sync=False)

    def _refresh_entry(self, *, sync: bool) -> None:
        acc = svc.current_account()
        if not acc:
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(1)
        self._account_label.setText(f"{acc.get('email')} · {acc.get('provider_id')}")
        self._reload_messages()
        if sync and not self._busy:
            self._on_sync()

    def _goto_wizard(self) -> None:
        acc = svc.current_account()
        if acc:
            # 预填
            idx = self._wiz_provider.findData(acc.get("provider_id"))
            if idx >= 0:
                self._wiz_provider.setCurrentIndex(idx)
            self._wiz_email.setText(str(acc.get("email") or ""))
            self._wiz_imap_host.setText(str(acc.get("imap_host") or ""))
            self._wiz_imap_port.setValue(int(acc.get("imap_port") or 993))
            self._wiz_imap_ssl.setChecked(bool(acc.get("imap_ssl", True)))
            self._wiz_smtp_host.setText(str(acc.get("smtp_host") or ""))
            self._wiz_smtp_port.setValue(int(acc.get("smtp_port") or 465))
            self._wiz_smtp_ssl.setChecked(bool(acc.get("smtp_ssl", True)))
            self._wiz_smtp_starttls.setChecked(bool(acc.get("smtp_starttls", False)))
        self._stack.setCurrentIndex(0)

    def _on_unbind(self) -> None:
        svc.unbind_account()
        self._msg_list.clear()
        self._msg_ids = []
        self._detail_meta.setText("")
        self._detail_text.setPlainText("")
        self._stack.setCurrentIndex(0)
        self.report_status("已解除绑定", StatusLevel.INFO)

    # —— 后台任务 ——
    def _start_job(self, kind: str, payload: dict | None = None) -> None:
        if self._busy:
            self.report_status("已有任务进行中", StatusLevel.WARNING)
            return
        self._busy = True
        self._activity.set_active(True)
        self._btn_bind.setEnabled(False)
        self._btn_sync.setEnabled(False)
        self._btn_send.setEnabled(False)

        thread = QThread(self)
        worker = _Worker(kind, payload)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_job_progress)
        worker.finished.connect(lambda ok, data: self._on_job_finished(kind, ok, data))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_done)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_thread_done(self) -> None:
        self._thread = None
        self._worker = None
        self._busy = False
        self._activity.set_active(False, immediate=True)
        self._btn_bind.setEnabled(True)
        self._btn_sync.setEnabled(True)
        self._btn_send.setEnabled(True)

    def _on_job_progress(self, msg: str, cur: int, total: int) -> None:
        self.report_status(msg, StatusLevel.INFO)
        self._status_hint.setText(msg)
        if total > 0:
            self._send_progress.setValue(max(0, min(100, int(100 * cur / total))))
        elif cur:
            self._send_progress.setValue(max(0, min(100, cur)))

    def _on_job_finished(self, kind: str, ok: bool, data: object) -> None:
        payload = data if isinstance(data, dict) else {}
        if kind == "bind":
            diag = payload.get("diagnosis") or {}
            if ok:
                self._wiz_diag.setPlainText(str(diag.get("human") or "绑定成功"))
                self.report_status("绑定成功", StatusLevel.SUCCESS)
                self._refresh_entry(sync=True)
            else:
                human = str(diag.get("human") or diag.get("title") or "绑定失败")
                self._wiz_diag.setPlainText(human)
                show_warning(self, human)
                self.report_status(diag.get("title") or "绑定失败", StatusLevel.ERROR)
        elif kind == "sync":
            status = str(payload.get("status") or "")
            meta = payload.get("meta") or {}
            if ok:
                self._status_hint.setText(status)
                self.report_status(status, StatusLevel.SUCCESS)
                self._reload_messages()
            else:
                diag = (meta.get("diagnosis") if isinstance(meta, dict) else None) or {}
                human = str(diag.get("human") or status or "同步失败")
                self._status_hint.setText(human)
                show_warning(self, human)
                self.report_status("同步失败（可重试）", StatusLevel.ERROR)
                self._reload_messages()
        elif kind == "send":
            diag = payload.get("diagnosis") or {}
            if ok:
                self._send_progress.setValue(100)
                self.report_status("已发送", StatusLevel.SUCCESS)
                self._cmp_body.setPlainText("")
                self._cmp_subject.setText("")
                self._clear_attachments()
                self._stack.setCurrentIndex(1)
                self._folder_role = "sent"
                self._folder_list.blockSignals(True)
                self._folder_list.setCurrentRow(1)
                self._folder_list.blockSignals(False)
                self._reload_messages()
            else:
                human = str(diag.get("human") or "发送失败")
                show_warning(self, human)
                self.report_status("发送失败", StatusLevel.ERROR)

    def _on_bind(self) -> None:
        self._start_job(
            "bind",
            {"form": self._wizard_form(), "password": self._wiz_password.text()},
        )

    def _on_sync(self) -> None:
        self._start_job("sync")

    def _on_send(self) -> None:
        to_raw = self._cmp_to.text().replace(";", ",")
        to_addrs = [x.strip() for x in to_raw.split(",") if x.strip()]
        cc_raw = self._cmp_cc.text().replace(";", ",")
        cc_addrs = [x.strip() for x in cc_raw.split(",") if x.strip()]
        self._start_job(
            "send",
            {
                "to_addrs": to_addrs,
                "cc_addrs": cc_addrs,
                "subject": self._cmp_subject.text().strip(),
                "body_text": self._cmp_body.toPlainText(),
                "attachments": list(self._compose_files),
            },
        )

    # —— 列表 / 详情 ——
    def _on_folder_changed(self, row: int) -> None:
        if row < 0 or row >= len(_FOLDERS):
            return
        self._folder_role = _FOLDERS[row][0]
        self._reload_messages()

    def _reload_messages(self) -> None:
        rows = svc.list_folder(self._folder_role)
        self._msg_list.clear()
        self._msg_ids = []
        for item in rows:
            mid = str(item.get("id") or "")
            subj = str(item.get("subject") or "(无主题)")
            unseen = "" if item.get("is_seen") else "● "
            attach = " [附]" if item.get("has_attach") else ""
            who = str(item.get("from_addr") or item.get("to_addrs") or "")
            self._msg_list.addItem(f"{unseen}{subj}{attach}\n{who}")
            self._msg_ids.append(mid)

    def _on_msg_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._msg_ids):
            return
        msg = svc.get_message(self._msg_ids[row])
        if not msg:
            return
        meta = (
            f"主题：{msg.get('subject') or '(无主题)'}\n"
            f"发件人：{msg.get('from_addr') or ''}\n"
            f"收件人：{msg.get('to_addrs') or ''}\n"
            f"时间：{msg.get('date_iso') or ''}"
        )
        self._detail_meta.setText(meta)
        body_text = str(msg.get("body_text") or "").strip()
        body_html = str(msg.get("body_html") or "").strip()
        self._detail_text.setPlainText(body_text or ("" if body_html else "(无正文)"))
        self._show_html(body_html)
        self._att_list.clear()
        for att in msg.get("attachments") or []:
            self._att_list.addItem(
                f"{att.get('filename')} ({int(att.get('size') or 0)} B)|{att.get('local_path')}"
            )
        # 就地刷新未读圆点，避免重置选中导致闪烁
        if row < self._msg_list.count():
            subj = str(msg.get("subject") or "(无主题)")
            attach = " [附]" if msg.get("attachments") else ""
            who = str(msg.get("from_addr") or msg.get("to_addrs") or "")
            self._msg_list.item(row).setText(f"{subj}{attach}\n{who}")

    def _ensure_html_view(self) -> bool:
        if self._html_view is not None:
            return True
        if self._html_error:
            return False
        try:
            from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
            from PySide6.QtWebEngineWidgets import QWebEngineView

            from services.storage_paths import module_data_dir
            from services.webengine_host import ToaWebEnginePage, theme_surface_color
        except Exception as exc:
            self._html_error = str(exc)
            return False
        try:
            profile_dir = module_data_dir("email_client", create=True) / "web_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile = QWebEngineProfile("email_client_private", self._html_host)
            profile.setCachePath(str(profile_dir / "cache"))
            profile.setPersistentStoragePath(str(profile_dir / "storage"))
            view = QWebEngineView(self._html_host)
            page = ToaWebEnginePage(profile, view)
            view.setPage(page)
            try:
                view.page().setBackgroundColor(theme_surface_color())
            except Exception:
                pass
            settings = view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
            )
            lay = self._html_host.layout()
            if lay is not None:
                self._html_fallback.setVisible(False)
                lay.insertWidget(0, view, 1)
            self._html_view = view
            return True
        except Exception as exc:
            self._html_error = str(exc)
            return False

    def _show_html(self, html: str) -> None:
        if not html:
            if self._html_view is not None:
                self._html_view.setHtml("")
            self._html_fallback.setVisible(self._html_view is None)
            return
        if not self._ensure_html_view():
            self._html_fallback.setText(f"HTML 预览不可用：{self._html_error}")
            self._html_fallback.setVisible(True)
            return
        # 简单沙箱包装：禁远程
        wrapped = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta http-equiv='Content-Security-Policy' "
            "content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline';\">"
            "</head><body>"
            f"{html}"
            "</body></html>"
        )
        self._html_view.setHtml(wrapped, QUrl("about:blank"))

    def _on_export_attachment(self) -> None:
        item = self._att_list.currentItem()
        if not item:
            show_warning(self, "请先选择附件")
            return
        text = item.text()
        path = text.split("|", 1)[-1].strip() if "|" in text else ""
        if not path:
            show_warning(self, "附件路径无效")
            return
        try:
            out = svc.export_attachment(path)
        except Exception as exc:
            show_warning(self, f"导出失败：{exc}")
            return
        show_saved(self, f"附件已导出：{out.name}", out)

    def _on_add_attachment(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择附件")
        if not paths:
            return
        merged = list(self._compose_files) + list(paths)
        ok, err = svc.check_attachments(merged)
        if not ok:
            show_warning(self, err)
            return
        self._compose_files = merged
        self._cmp_att_label.setText(
            "附件：" + "、".join(Path(p).name for p in self._compose_files)
        )

    def _clear_attachments(self) -> None:
        self._compose_files = []
        self._cmp_att_label.setText("附件：无")
        self._send_progress.setValue(0)
