# -*- coding: utf-8 -*-
"""系统 · 通知：通道说明、试发、提示（会话）与留档（持久）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
from services.notify_archive import (
    email_config_summary,
    format_record_line,
    list_records,
)
from services.notify_bus import (
    NotifyLevel,
    get_bus,
    notify,
    recent_notifications,
)
from widgets import (
    FormSection,
    HintLabel,
    ListWidget,
    PageHeader,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
)


class NotificationsPage(BasePage):
    page_id = "notifications"
    page_title = "通知"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "通知",
                "提示类看过即过；留档类与邮件、任务执行写入本机记录。",
            )
        )

        email = email_config_summary()
        scroll.add_widget(
            HintLabel(
                "闭环：系统 → 任务 → 新增/试跑 → 回到本页查留档。\n"
                f"邮件收件人：{email.get('recipient') or '未配置'}"
                f"（系统设置 → 能力接入 → integrations.email · recipient_email）"
            )
        )

        channels = FormSection("通道与性质")
        channels.add_widget(
            HintLabel(
                "· 提示 — 状态栏/托盘/对话框，仅「本会话提示」列表，重启清空\n"
                "· 留档 — 写入下方「留档记录」，含定时任务执行与留档通知\n"
                "· 邮件 — 纯文本：主题=标题，正文=正文，收件=能力接入里配置的邮箱\n"
                f"· 当前邮件：{email.get('hint') or '未启用'}"
            )
        )
        scroll.add_widget(channels)

        test = FormSection("试发")
        row = QHBoxLayout()
        self._btn_prompt = PrimaryButton("试发·提示")
        self._btn_prompt.clicked.connect(lambda: self._send_test("status", "prompt"))
        row.addWidget(self._btn_prompt)
        btn_record = SecondaryButton("试发·留档")
        btn_record.clicked.connect(lambda: self._send_test("status", "record"))
        row.addWidget(btn_record)
        btn_tray = SecondaryButton("托盘")
        btn_tray.clicked.connect(lambda: self._send_test("tray", "prompt"))
        row.addWidget(btn_tray)
        btn_email = SecondaryButton("邮件")
        btn_email.clicked.connect(lambda: self._send_test("email", "record"))
        row.addWidget(btn_email)
        row.addStretch(1)
        test.add_layout(row)
        scroll.add_widget(test)

        prompt_sec = FormSection("本会话提示")
        prompt_sec.add_widget(HintLabel("提示类通知，关闭应用后不可查。"))
        self._prompt_list = ListWidget()
        self._prompt_list.setMinimumHeight(140)
        prompt_sec.add_widget(self._prompt_list, 1)
        scroll.add_widget(prompt_sec)

        archive_sec = FormSection("留档记录")
        archive_sec.add_widget(
            HintLabel("信息类通知、邮件发送、定时任务每次执行 — 落盘可追溯（最多 500 条）。")
        )
        self._archive_list = ListWidget()
        self._archive_list.setMinimumHeight(220)
        archive_sec.add_widget(self._archive_list, 1)
        row2 = QHBoxLayout()
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(lambda: self._reload_all(report=True))
        row2.addWidget(btn_refresh)
        row2.addStretch(1)
        archive_sec.add_layout(row2)
        scroll.add_widget(archive_sec)
        scroll.add_stretch(1)

        bus = get_bus()
        bus.status.connect(lambda *_: self._reload_all(report=False))
        bus.toast.connect(lambda *_: self._reload_all(report=False))
        bus.job_progress.connect(lambda *_: self._reload_all(report=False))

        self._reload_all(report=False)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._btn_prompt

    def focus_tab_widgets(self) -> list[QWidget]:
        return [self._btn_prompt]

    def _send_test(self, channel: str, notice_kind: str) -> None:
        notify(
            NotifyLevel.INFO,
            title="通知试发",
            body=f"通道 {channel} · 性质 {notice_kind} · 来自「通知」页",
            channel=channel,
            notice_kind=notice_kind,
            source="test:notifications",
            parent=self,
        )
        self._reload_all(report=False)
        self.report_status(f"已试发 · {channel}/{notice_kind}", level=StatusLevel.SUCCESS)

    def _reload_prompt_list(self) -> None:
        items = recent_notifications(40)
        self._prompt_list.clear()
        prompt_items = [x for x in items if "|record" not in str(x.get("channel") or "")]
        if not prompt_items:
            self._prompt_list.addItem("（暂无提示类通知）")
            return
        for item in prompt_items:
            ts = item.get("ts") or "—"
            ch = str(item.get("channel") or "?").split("|")[0]
            title = item.get("title") or ""
            body = item.get("body") or ""
            text = f"{ts} · [{ch}] {title}"
            if body and body != title:
                text = f"{text} — {body}"
            self._prompt_list.addItem(text)

    def _reload_archive_list(self) -> None:
        rows = list_records(limit=80)
        self._archive_list.clear()
        if not rows:
            self._archive_list.addItem("（暂无留档；任务试跑或选「留档」通知后会出现）")
            return
        for row in rows:
            self._archive_list.addItem(format_record_line(row))

    def _reload_all(self, *, report: bool = False) -> None:
        self._reload_prompt_list()
        self._reload_archive_list()
        if report:
            self.report_status("通知列表已刷新")

    def on_enter(self) -> None:
        self._reload_all(report=False)
        self.report_status("通知")
