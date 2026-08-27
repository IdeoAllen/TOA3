# -*- coding: utf-8 -*-
"""Harness 右栏：token / 上下文 / 目标仪表。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from services.harness_store import overview_from_status, session_detail, trend_series
from widgets import FormSection, HintLabel, ReadOnlyPlainTextEdit, SecondaryButton


class StatusPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        box = FormSection("用量概览")
        self._summary = ReadOnlyPlainTextEdit()
        self._summary.setMaximumHeight(120)
        self._summary.setPlaceholderText("token / 会话统计…")
        box.add_widget(self._summary)
        lay.addWidget(box)

        trend_box = FormSection("每步 token 趋势")
        self._trend = ReadOnlyPlainTextEdit()
        self._trend.setMaximumHeight(100)
        self._trend.setPlaceholderText("选中左栏会话后显示…")
        trend_box.add_widget(self._trend)
        lay.addWidget(trend_box)

        goal_box = FormSection("当前目标")
        self._goal = ReadOnlyPlainTextEdit()
        self._goal.setMaximumHeight(80)
        goal_box.add_widget(self._goal)
        lay.addWidget(goal_box)

        detail_box = FormSection("会话详情")
        self._detail = ReadOnlyPlainTextEdit()
        self._detail.setMinimumHeight(120)
        detail_box.add_widget(self._detail)
        lay.addWidget(detail_box, 1)

        btn = SecondaryButton("刷新仪表")
        btn.clicked.connect(self.refresh_overview)
        lay.addWidget(btn)

        self._current_session: str = ""

    def refresh_overview(self) -> None:
        ov = overview_from_status()
        snap = ov.get("status") or {}
        lines = [
            f"工作区：{snap.get('workspaces', '—')}",
            f"会话：{snap.get('sessions', '—')}（归档 {snap.get('archived', 0)}）",
            f"输入 token：{snap.get('inputTokens', '—')}",
            f"输出 token：{snap.get('outputTokens', '—')}",
            f"上下文峰值：{snap.get('maxContextPct', '—')}%",
            f"DSH_HOME：{ov.get('dsh_home', '')}",
        ]
        self._summary.setPlainText("\n".join(lines))
        goal = snap.get("goal") or snap.get("activeGoal")
        if isinstance(goal, dict):
            obj = goal.get("objective") or goal.get("goal", {}).get("objective")
            self._goal.setPlainText(str(obj or "无活跃目标"))
        else:
            self._goal.setPlainText(str(goal or "无活跃目标"))

    def show_session(self, session_id: str) -> None:
        self._current_session = session_id
        detail = session_detail(session_id) or {}
        parts = [
            f"标题：{detail.get('title', '')}",
            f"工作区：{detail.get('workspace', '')}",
            f"目录：{detail.get('cwd', '')}",
        ]
        tu = detail.get("tokenUsage") or {}
        if tu:
            parts.append(
                f"token 输入/输出：{tu.get('inputTokens', '—')} / {tu.get('outputTokens', '—')}"
            )
        cp = detail.get("contextPressure") or detail.get("contextPct")
        if cp is not None:
            parts.append(f"上下文压力：{cp}")
        todos = detail.get("todos")
        if todos:
            parts.append(f"待办：{todos}")
        self._detail.setPlainText("\n".join(parts))

        series = trend_series(session_id)
        if series:
            spark = []
            for step in series[-12:]:
                inp = step.get("inputTokens") or step.get("input") or 0
                out = step.get("outputTokens") or step.get("output") or 0
                spark.append(f"步{step.get('step', '?')}: ↑{inp} ↓{out}")
            self._trend.setPlainText("\n".join(spark))
        else:
            self._trend.clear()
