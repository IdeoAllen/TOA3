# -*- coding: utf-8 -*-
"""关于：品牌信息 + 愿景要点 + 检查更新。"""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from app.dialog_chrome import (
    add_dialog_hero,
    add_form_section,
    apply_dialog_root,
    make_info_form,
    value_label,
)
from core.base_dialog import BaseDialog
from core.user_messages import show_error, show_info
from services.icon_registry import brand_logo_pixmap
from services.product_vision import tagline, vision_display_rows
from services.system_info import get_system_info, logo_path
from services.update_check import UpdateCheckResult, format_up_to_date_message, get_update_hub
from app.update_available_dialog import present_update_available
from widgets import DialogButtonRow, HintLabel


class AboutDialog(BaseDialog):
    """产品品牌、版本与愿景要点。"""

    dialog_kind = "account"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于")
        self._update_result: UpdateCheckResult | None = None
        self._update_busy = False
        info = get_system_info()

        root = QVBoxLayout(self)
        apply_dialog_root(root)

        pix = brand_logo_pixmap(56, 56, parent=self) if logo_path() is not None else None
        add_dialog_hero(
            root,
            pixmap=pix,
            title=str(info.get("brand_name") or "TOA"),
            subtitle=tagline(),
            icon_size=56,
        )

        rows = vision_display_rows()
        if rows:
            vision = make_info_form()
            for label, text in rows:
                vision.addRow(label, value_label(text))
            add_form_section(root, "使命 · 愿景 · 目标 · 定位", vision)

        meta = make_info_form()
        try:
            from services.user_plan_presentation import user_software_version

            version_text = user_software_version()
        except Exception:
            version_text = str(info.get("app_version") or "—")
        meta.addRow("版本", value_label(version_text))
        profile = str(info.get("build_profile") or "").strip()
        if profile:
            meta.addRow("发行", value_label(profile))
        meta.addRow("产品", value_label(str(info.get("app_name") or "—")))
        meta.addRow("作者", value_label(str(info.get("author") or "—") or "—"))
        email = str(info.get("author_email") or "").strip()
        if email:
            meta.addRow("联系", value_label(email, selectable=True))
        add_form_section(root, "版本信息", meta)

        root.addWidget(HintLabel("检查更新在此；换码与退出见顶栏用户。"))

        actions = DialogButtonRow()
        self._btn_check = actions.add_secondary("检查更新", self._on_check_update)
        actions.add_primary("关闭", self.accept)
        root.addWidget(actions)

        hub = get_update_hub()
        hub.checking_changed.connect(self._on_hub_checking)
        hub.result_ready.connect(self._on_hub_result)

    def _on_hub_checking(self, busy: bool) -> None:
        self._set_check_busy(busy)

    def _on_hub_result(self, result: object) -> None:
        if get_update_hub().last_reason() != "about":
            return
        if not self.isVisible():
            return
        if not isinstance(result, UpdateCheckResult):
            show_error(self, "检查更新失败：返回无效", title="检查更新")
            return
        try:
            self._on_update_checked(result)
        except Exception as exc:
            show_error(self, f"检查更新失败：{exc}", title="检查更新")

    def _set_check_busy(self, busy: bool) -> None:
        self._update_busy = busy
        self._btn_check.setEnabled(not busy)
        self._btn_check.setText("检查中…" if busy else "检查更新")

    def _on_check_update(self) -> None:
        if self._update_busy:
            return
        get_update_hub().check_async(reason="about")

    def _on_update_checked(self, result: UpdateCheckResult) -> None:
        self._update_result = result
        if result.has_update:
            present_update_available(self, result)
            return
        show_info(self, format_up_to_date_message(result), title="检查更新")
