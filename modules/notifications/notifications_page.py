# -*- coding: utf-8 -*-
"""系统 · 通知：通道说明、试发与本会话最近通知（复用 notify_bus）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.status_service import StatusLevel
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
                "统一走 notify_bus：状态栏 / 对话框 / 托盘 / 邮件（需启用 email 接入）。",
            )
        )
        scroll.add_widget(
            HintLabel(
                "本页展示通道能力与本会话最近通知。"
                "邮件收件人等在「系统设置 → 能力接入」配置；"
                "定时任务请到侧栏「任务」。"
            )
        )

        channels = FormSection("通道")
        email_hint = self._email_status_text()
        channels.add_widget(
            HintLabel(
                "· status — 状态栏\n"
                "· dialog — 应用内对话框\n"
                "· tray — 系统托盘气泡\n"
                "· email — SMTP 邮件（integrations.email）\n"
                "· all — 上述组合（邮件仅 warning/error）\n"
                f"· 当前邮件：{email_hint}"
            )
        )
        scroll.add_widget(channels)

        test = FormSection("试发")
        row = QHBoxLayout()
        self._btn_status = PrimaryButton("状态栏")
        self._btn_status.clicked.connect(lambda: self._send_test("status"))
        row.addWidget(self._btn_status)
        btn_tray = SecondaryButton("托盘")
        btn_tray.clicked.connect(lambda: self._send_test("tray"))
        row.addWidget(btn_tray)
        btn_dialog = SecondaryButton("对话框")
        btn_dialog.clicked.connect(lambda: self._send_test("dialog"))
        row.addWidget(btn_dialog)
        btn_all = SecondaryButton("全部通道")
        btn_all.clicked.connect(lambda: self._send_test("all"))
        row.addWidget(btn_all)
        row.addStretch(1)
        test.add_layout(row)
        scroll.add_widget(test)

        hist = FormSection("本会话最近通知")
        hist.add_widget(HintLabel("进程内环形缓冲，重启后清空；尚无持久化历史。"))
        self._list = ListWidget()
        self._list.setMinimumHeight(220)
        hist.add_widget(self._list, 1)
        row2 = QHBoxLayout()
        btn_refresh = SecondaryButton("刷新")
        btn_refresh.clicked.connect(lambda: self._reload_history(report=True))
        row2.addWidget(btn_refresh)
        row2.addStretch(1)
        hist.add_layout(row2)
        scroll.add_widget(hist)
        scroll.add_stretch(1)

        bus = get_bus()
        bus.status.connect(lambda *_: self._reload_history(report=False))
        bus.toast.connect(lambda *_: self._reload_history(report=False))

        self._reload_history(report=False)
        self.apply_page_focus_policy()

    def primary_focus_widget(self) -> QWidget | None:
        return self._btn_status

    def focus_tab_widgets(self) -> list[QWidget]:
        return [self._btn_status]

    def _email_status_text(self) -> str:
        try:
            from services.integrations.config import integration_enabled

            return "已启用" if integration_enabled("email") else "未启用"
        except Exception:
            return "未知（无法读取 integrations）"

    def _send_test(self, channel: str) -> None:
        notify(
            NotifyLevel.INFO,
            title="通知试发",
            body=f"通道 {channel} · 来自系统「通知」页",
            channel=channel,
            parent=self,
        )
        self._reload_history(report=False)
        self.report_status(f"已试发 · {channel}", level=StatusLevel.SUCCESS)

    def _reload_history(self, *, report: bool = False) -> None:
        items = recent_notifications(40)
        self._list.clear()
        if not items:
            self._list.addItem("（暂无记录，可点上方试发）")
        else:
            for item in items:
                ts = item.get("ts") or "—"
                ch = item.get("channel") or "?"
                lvl = item.get("level") or "info"
                title = item.get("title") or ""
                body = item.get("body") or ""
                text = f"{ts} · [{ch}/{lvl}] {title}"
                if body and body != title:
                    text = f"{text} — {body}"
                self._list.addItem(text)
        if report:
            self.report_status(f"最近通知 {len(items)} 条")

    def on_enter(self) -> None:
        self._reload_history(report=False)
        self.report_status("通知")
