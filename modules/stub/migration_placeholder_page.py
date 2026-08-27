# -*- coding: utf-8 -*-
"""迁移占位页：未实装模块的空页面，展示清单与 TOA2 对照。"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from services.migration_manifest import get_module_meta, module_gaps, status_label
from widgets import FormSection, HintLabel, PageHeader, ScrollPage, SectionTitle


class MigrationPlaceholderPage(BasePage):
    def __init__(
        self,
        module_id: str,
        title: str,
        desc: str = "",
        meta: dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page_id = module_id
        self.page_title = title
        self._meta = meta or get_module_meta(module_id)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                title,
                f"状态：{status_label(module_id)} · 本页为迁移占位，功能将按清单逐个实装。",
            )
        )

        if desc:
            scroll.add_widget(HintLabel(desc))

        info = FormSection("迁移信息")
        lines = [
            f"模块 ID：{module_id}",
            f"优先级：{self._meta.get('priority') or '—'}",
            f"TOA2 参考：{self._meta.get('toa2_ref') or '—'}",
        ]
        note = str(self._meta.get("note") or "").strip()
        if note:
            lines.append(f"说明：{note}")
        info.add_widget(HintLabel("\n".join(lines)))
        scroll.add_widget(info)

        gaps = module_gaps(module_id) or list(self._meta.get("gaps") or [])
        if gaps:
            gap_box = FormSection("待实现（下一批）")
            gap_box.add_widget(HintLabel("\n".join(f"· {g}" for g in gaps)))
            scroll.add_widget(gap_box)

        scroll.add_widget(SectionTitle("开发顺序"))
        from services.migration_manifest import implementation_order

        order = implementation_order()
        if order:
            preview = order[:12]
            more = len(order) - len(preview)
            text = " → ".join(preview)
            if more > 0:
                text += f" …（另有 {more} 项）"
            scroll.add_widget(HintLabel(text))
        scroll.add_widget(
            HintLabel(
                "完整清单见 config/migration_manifest.yml 与 docs/迁移进度.md。\n"
                "实装完成后将替换为本模块业务页。"
            )
        )
        scroll.add_stretch(1)

    def on_enter(self) -> None:
        self.report_status(f"{self.page_title}（{status_label(self.page_id)}）", level=StatusLevel.INFO)
