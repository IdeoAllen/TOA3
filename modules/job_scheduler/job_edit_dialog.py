# -*- coding: utf-8 -*-
"""定时任务编辑：任务类型 · 通道 · 内容 · 间隔（用户可读）。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.base_dialog import BaseDialog
from core.user_messages import show_warning
from services.job_scheduler import JobSpec
from services.job_task_catalog import (
    CUSTOM_INTERVAL,
    INTERVAL_PRESETS,
    NOTICE_KINDS,
    NOTIFY_CHANNELS,
    NOTIFY_LEVELS,
    TASK_TYPES,
    build_job_payload,
    job_to_form,
    navigable_modules,
)
from services.notify_archive import email_config_summary, email_delivery_preview
from widgets import (
    CheckBox,
    ComboBox,
    DialogButtonRow,
    FormRow,
    HintLabel,
    LineEdit,
    PlainTextEdit,
    SpinBox,
)
from widgets.containers import PathRow


class JobEditDialog(BaseDialog):
    dialog_kind = "medium"

    def __init__(self, parent=None, *, job: JobSpec | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._result: dict | None = None
        self.setWindowTitle("编辑定时任务" if job else "新增定时任务")

        root = QVBoxLayout(self)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self._name = LineEdit()
        self._name.setPlaceholderText("例如：每日提醒、打开报表页")
        form.addRow("名称", self._name)

        self._type_combo = ComboBox()
        for action, label in TASK_TYPES:
            self._type_combo.addItem(label, action)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("任务类型", self._type_combo)

        self._detail_stack = QStackedWidget()
        self._detail_pages: dict[str, QWidget] = {}
        self._build_notify_page()
        self._build_web_page()
        self._build_app_page()
        self._build_module_page()
        self._build_scan_page()
        self._build_log_page()
        form.addRow("内容", self._detail_stack)

        self._interval_combo = ComboBox()
        for sec, label in INTERVAL_PRESETS:
            self._interval_combo.addItem(label, sec)
        self._interval_combo.addItem("自定义…", CUSTOM_INTERVAL)
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        interval_row = QWidget()
        interval_lay = QHBoxLayout(interval_row)
        interval_lay.setContentsMargins(0, 0, 0, 0)
        interval_lay.setSpacing(8)
        interval_lay.addWidget(self._interval_combo, 1)
        self._interval_custom = SpinBox()
        self._interval_custom.setMinimum(30)
        self._interval_custom.setMaximum(86400 * 30)
        self._interval_custom.setSingleStep(60)
        self._interval_custom.setValue(3600)
        self._interval_custom.setSuffix(" 秒")
        self._interval_custom.hide()
        interval_lay.addWidget(self._interval_custom)
        form.addRow("时间规则", interval_row)

        self._enabled = CheckBox("启用此任务")
        self._enabled.setChecked(True)
        if job is not None:
            form.addRow("状态", self._enabled)

        wrap = QWidget()
        wrap.setLayout(form)
        root.addWidget(wrap)
        self._guide = HintLabel(
            "① 选类型与内容 → ② 保存后点「立即执行」试跑 → ③ 到侧栏「通知」查看留档/邮件结果"
        )
        root.addWidget(self._guide)
        self._footer_hint = HintLabel("")
        root.addWidget(self._footer_hint)

        actions = DialogButtonRow()
        actions.add_secondary("取消", self.reject)
        actions.add_primary("保存", self._on_save)
        root.addWidget(actions)

        if job is not None:
            self._load_job(job)
        else:
            self._on_type_changed()
            self._on_interval_changed()

        self._name.setFocus()

    @property
    def payload(self) -> dict | None:
        return self._result

    def _build_notify_page(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._notify_channel = ComboBox()
        for cid, label in NOTIFY_CHANNELS:
            self._notify_channel.addItem(label, cid)
        self._notify_channel.currentIndexChanged.connect(self._refresh_notify_hints)
        lay.addWidget(FormRow("通道", self._notify_channel, label_width=56))
        self._notify_kind = ComboBox()
        for kid, label in NOTICE_KINDS:
            self._notify_kind.addItem(label, kid)
        self._notify_kind.currentIndexChanged.connect(self._refresh_notify_hints)
        lay.addWidget(FormRow("性质", self._notify_kind, label_width=56))
        self._notify_level = ComboBox()
        for lid, label in NOTIFY_LEVELS:
            self._notify_level.addItem(label, lid)
        lay.addWidget(FormRow("级别", self._notify_level, label_width=56))
        self._notify_title = LineEdit()
        self._notify_title.setPlaceholderText("邮件主题 / 对话框标题")
        self._notify_title.textChanged.connect(self._refresh_notify_hints)
        lay.addWidget(FormRow("标题", self._notify_title, label_width=56))
        self._notify_body = PlainTextEdit()
        self._notify_body.setPlaceholderText("正文（必填其一：标题或正文）")
        self._notify_body.setMinimumHeight(72)
        self._notify_body.setMaximumHeight(96)
        self._notify_body.textChanged.connect(self._refresh_notify_hints)
        lay.addWidget(FormRow("正文", self._notify_body, label_width=56))
        self._notify_channel_hint = HintLabel("")
        self._notify_channel_hint.setWordWrap(True)
        lay.addWidget(self._notify_channel_hint)
        self._notify_preview = HintLabel("")
        self._notify_preview.setWordWrap(True)
        lay.addWidget(self._notify_preview)
        self._detail_pages["send_notify"] = page
        self._detail_stack.addWidget(page)

    def _build_web_page(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self._web_url = LineEdit()
        self._web_url.setPlaceholderText("https://example.com 或 example.com")
        lay.addWidget(FormRow("网页地址", self._web_url, label_width=72))
        lay.addWidget(HintLabel("将用系统默认浏览器打开。"))
        self._detail_pages["open_web"] = page
        self._detail_stack.addWidget(page)

    def _build_app_page(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self._app_path = PathRow(placeholder="选择 .exe 或可执行文件…", directory=False)
        lay.addWidget(FormRow("应用路径", self._app_path, label_width=72))
        lay.addWidget(HintLabel("可用系统默认程序打开的文件或快捷方式。"))
        self._detail_pages["open_app"] = page
        self._detail_stack.addWidget(page)

    def _build_module_page(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self._module_combo = ComboBox()
        for mid, title in navigable_modules():
            self._module_combo.addItem(title, mid)
        lay.addWidget(FormRow("功能模块", self._module_combo, label_width=72))
        lay.addWidget(HintLabel("到点自动切换到该模块（需主窗口在运行）。"))
        self._detail_pages["open_module"] = page
        self._detail_stack.addWidget(page)

    def _build_scan_page(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(HintLabel("按间隔扫描「日程提醒」中到期项，并通过状态栏通知。"))
        self._detail_pages["schedule_reminder_scan"] = page
        self._detail_stack.addWidget(page)

    def _build_log_page(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self._log_days = SpinBox()
        self._log_days.setMinimum(1)
        self._log_days.setMaximum(365)
        self._log_days.setValue(7)
        lay.addWidget(FormRow("保留天数", self._log_days, label_width=72))
        lay.addWidget(HintLabel("删除更早的应用日志文件（*.log*）。"))
        self._detail_pages["log_cleanup"] = page
        self._detail_stack.addWidget(page)

    def _on_type_changed(self) -> None:
        action = str(self._type_combo.currentData() or "send_notify")
        page = self._detail_pages.get(action)
        if page is not None:
            self._detail_stack.setCurrentWidget(page)
        if action == "send_notify":
            self._refresh_notify_hints()
        else:
            self._footer_hint.setText("非通知类任务：执行结果写入「通知 → 留档记录」。")

    def _refresh_notify_hints(self) -> None:
        if str(self._type_combo.currentData() or "") != "send_notify":
            return
        channel = str(self._notify_channel.currentData() or "status")
        kind = str(self._notify_kind.currentData() or "prompt")
        email = email_config_summary()
        lines = []
        if channel == "status":
            lines.append("状态栏：底部一闪而过，仅本会话可见。")
        elif channel == "dialog":
            lines.append("对话框：弹出提示框，需手动关闭。")
        elif channel == "tray":
            lines.append("托盘：系统气泡，几秒后消失。")
        elif channel == "email":
            lines.append(f"邮件：{email.get('hint') or '未配置'}")
            kind = "record"
            idx = self._notify_kind.findData("record")
            if idx >= 0:
                self._notify_kind.setCurrentIndex(idx)
        elif channel == "all":
            lines.append("全部：状态栏+对话框+托盘；warning/error 才发邮件。")
        if kind == "prompt" and channel not in ("email",):
            lines.append("性质=提示：不写留档，重启后不可查。")
        else:
            lines.append("性质=留档：写入「通知 → 留档记录」，可回溯。")
        self._notify_channel_hint.setText("\n".join(lines))
        title = self._notify_title.text().strip() or "定时任务"
        body = self._notify_body.toPlainText().strip()
        if channel == "email":
            self._notify_preview.setText("对方收到：\n" + email_delivery_preview(title, body))
        else:
            self._notify_preview.setText(f"本机展示：标题「{title}」· 正文「{body or title}」")
        self._footer_hint.setText(email.get("hint", "") if channel == "email" else "")

    def _on_interval_changed(self) -> None:
        preset = self._interval_combo.currentData()
        custom = preset == CUSTOM_INTERVAL
        self._interval_custom.setVisible(custom)

    def _load_job(self, job: JobSpec) -> None:
        form = job_to_form(job)
        self._name.setText(str(form.get("name") or ""))
        action = str(form.get("action") or "send_notify")
        idx = self._type_combo.findData(action)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        params = dict(form.get("params") or {})
        if action == "send_notify":
            ch = str(params.get("channel") or "status")
            li = self._notify_channel.findData(ch)
            if li >= 0:
                self._notify_channel.setCurrentIndex(li)
            nk = str(params.get("notice_kind") or "prompt")
            li = self._notify_kind.findData(nk)
            if li >= 0:
                self._notify_kind.setCurrentIndex(li)
            lv = str(params.get("level") or "info")
            li = self._notify_level.findData(lv)
            if li >= 0:
                self._notify_level.setCurrentIndex(li)
            self._notify_title.setText(str(params.get("title") or ""))
            self._notify_body.setPlainText(str(params.get("body") or params.get("message") or ""))
        elif action == "open_web":
            self._web_url.setText(str(params.get("url") or ""))
        elif action == "open_app":
            self._app_path.set_text(str(params.get("path") or ""))
        elif action == "open_module":
            mid = str(params.get("module_id") or "")
            li = self._module_combo.findData(mid)
            if li >= 0:
                self._module_combo.setCurrentIndex(li)
        elif action == "log_cleanup":
            self._log_days.setValue(int(params.get("keep_days") or 7))
        preset = int(form.get("interval_preset") or 3600)
        pi = self._interval_combo.findData(preset)
        if pi >= 0:
            self._interval_combo.setCurrentIndex(pi)
        self._interval_custom.setValue(int(form.get("interval_custom") or job.interval_seconds))
        self._enabled.setChecked(bool(job.enabled))
        self._on_type_changed()
        self._on_interval_changed()
        self._refresh_notify_hints()

    def _collect_form(self) -> dict:
        action = str(self._type_combo.currentData() or "send_notify")
        params: dict = {}
        if action == "send_notify":
            channel = str(self._notify_channel.currentData() or "status")
            notice_kind = str(self._notify_kind.currentData() or "prompt")
            if channel == "email":
                notice_kind = "record"
            params = {
                "channel": channel,
                "notice_kind": notice_kind,
                "level": str(self._notify_level.currentData() or "info"),
                "title": self._notify_title.text().strip(),
                "body": self._notify_body.toPlainText().strip(),
            }
        elif action == "open_web":
            url = self._web_url.text().strip()
            if url and "://" not in url:
                url = f"https://{url}"
            params = {"url": url}
        elif action == "open_app":
            params = {"path": self._app_path.text()}
        elif action == "open_module":
            params = {"module_id": str(self._module_combo.currentData() or "")}
        elif action == "log_cleanup":
            params = {"keep_days": int(self._log_days.value())}
        return {
            "name": self._name.text().strip(),
            "action": action,
            "interval_preset": self._interval_combo.currentData(),
            "interval_custom": int(self._interval_custom.value()),
            "params": params,
            "enabled": self._enabled.isChecked(),
        }

    def _on_save(self) -> None:
        form = self._collect_form()
        ok, err, data = build_job_payload(form)
        if not ok or data is None:
            show_warning(self, err or "请检查表单。")
            return
        self._result = {
            "name": data.name,
            "action": data.action,
            "interval_seconds": data.interval_seconds,
            "params": data.params,
            "enabled": bool(form.get("enabled", True)),
        }
        self.accept()
