# -*- coding: utf-8 -*-
"""系统设置 · 关于产品（品牌、愿景、版本只读）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.dialog_chrome import make_info_form, value_label
from core.base_page import BasePage
from services.icon_registry import brand_logo_pixmap
from services.product_vision import tagline, vision_home_rows
from services.system_info import get_system_info, logo_path
from widgets import FormSection, HintLabel


class AboutAppSection(QWidget):
    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        info = get_system_info()
        hero = FormSection("产品")
        row = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(72, 72)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if logo_path() is not None:
            pix = brand_logo_pixmap(64, 64, parent=self)
            if not pix.isNull():
                logo.setPixmap(pix)
        else:
            logo.setText("Logo")
        row.addWidget(logo)
        title = QLabel(str(info.get("brand_name") or "运营宝"))
        title.setObjectName("PageTitle")
        sub = QLabel(tagline())
        sub.setObjectName("HintLabel")
        text_col = QVBoxLayout()
        text_col.addWidget(title)
        text_col.addWidget(sub)
        row.addLayout(text_col)
        row.addStretch(1)
        hero.add_layout(row)
        outer.addWidget(hero)

        vision_rows = vision_home_rows()
        if vision_rows:
            box = FormSection("使命 · 愿景 · 目标")
            form = make_info_form()
            for label, text in vision_rows:
                form.addRow(label, value_label(str(text)))
            wrap = QWidget()
            wrap.setLayout(form)
            box.add_widget(wrap)
            outer.addWidget(box)

        meta = FormSection("版本信息")
        form = make_info_form()
        form.addRow("版本", value_label(str(info.get("app_version") or "—")))
        form.addRow("发行", value_label(str(info.get("build_profile") or "—")))
        form.addRow("产品", value_label(str(info.get("app_name") or "—")))
        form.addRow("作者", value_label(str(info.get("author") or "—")))
        email = str(info.get("author_email") or "").strip()
        form.addRow(
            "联系",
            value_label(email or "—", selectable=bool(email)),
        )
        wrap_meta = QWidget()
        wrap_meta.setLayout(form)
        meta.add_widget(wrap_meta)
        outer.addWidget(meta)

        outer.addWidget(
            HintLabel(
                "检查更新、重启与退出见「应用与更新」页签；"
                "顶栏 ℹ 可快速打开关于弹窗。"
            )
        )
        outer.addStretch(1)
