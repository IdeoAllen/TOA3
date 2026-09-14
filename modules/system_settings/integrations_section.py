# -*- coding: utf-8 -*-
"""系统设置 · 能力接入：截图识字 + 能力状态（短卡片，不堆工程黑话）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.integrations.config import (
    integration_config,
    load_integrations_config,
    save_integrations_config,
)
from services.integrations.registry import status_lines
from widgets import (
    CheckBox,
    FormSection,
    HintLabel,
    LineEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
)

if TYPE_CHECKING:
    from modules.system_settings.model_registry_section import ModelRegistrySection


class IntegrationsSection(QWidget):
    """能力接入（管理员：识字配置；终端用户：模型入口占位）。"""

    def __init__(self, parent: BasePage, *, admin: bool = True) -> None:
        super().__init__(parent)
        self._page = parent
        self._admin = admin
        self._tabs = None  # 兼容旧 select_sub_tab 调用
        self._model_registry: ModelRegistrySection | None = None
        self._status: ReadOnlyPlainTextEdit | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        if not admin:
            lay.addWidget(HintLabel("模型地址与密钥只保存在本机，不会上传。"))
            from modules.system_settings.model_registry_section import ModelRegistrySection

            self._model_registry = ModelRegistrySection(self._page)
            self._model_registry.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            lay.addWidget(self._model_registry, 1)
            return

        lay.addWidget(HintLabel("截图转文字用本机识别程序；密钥与路径只保存在本机。"))
        lay.addWidget(self._build_ocr_card())
        lay.addWidget(self._build_status_card())
        lay.addStretch(1)
        self.refresh_status(report=False, probe=False)

    def select_sub_tab(self, name: str) -> None:
        """兼容旧入口（大模型/图像生成已迁到「模型管理」）。"""
        aliases = {
            "模型库": "模型管理",
            "大模型": "模型管理",
            "图像生成": "模型管理",
        }
        _ = aliases.get(name, name)
        cap_filter: str | None = None
        if name == "大模型":
            cap_filter = "text_llm"
        elif name == "图像生成":
            cap_filter = "image_gen"
        if self._model_registry is not None and cap_filter is not None:
            self._model_registry.set_capability_filter(cap_filter)

    def _build_ocr_card(self) -> QWidget:
        box = FormSection("截图识字")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        box.add_widget(HintLabel("需要本机已安装识别程序。中文请装中文语言包，语言填 chi_sim+eng。"))

        cfg = integration_config("ocr")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._ocr_enabled = CheckBox("启用")
        self._ocr_enabled.setChecked(bool(cfg.get("enabled", True)))
        form.addRow("开关", self._ocr_enabled)

        self._ocr_path = LineEdit(str(cfg.get("tesseract_path") or ""))
        self._ocr_path.setPlaceholderText(r"例如 C:\Program Files\Tesseract-OCR\tesseract.exe")
        self._ocr_path.setMinimumWidth(360)
        form.addRow("程序路径", self._ocr_path)

        self._ocr_lang = LineEdit(str(cfg.get("lang") or "eng"))
        self._ocr_lang.setPlaceholderText("eng 或 chi_sim+eng")
        self._ocr_lang.setMaximumWidth(280)
        form.addRow("语言", self._ocr_lang)

        box.add_layout(form)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_save = PrimaryButton("保存")
        btn_save.clicked.connect(self._save_ocr)
        row.addWidget(btn_save)
        btn_test = SecondaryButton("测一下")
        btn_test.clicked.connect(self._test_ocr)
        row.addWidget(btn_test)
        row.addStretch(1)
        box.add_layout(row)
        return box

    def _build_status_card(self) -> QWidget:
        box = FormSection("能力状态")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        box.add_widget(HintLabel("只看本机是否已配置；点刷新才会实际探测连通。"))

        self._status = ReadOnlyPlainTextEdit()
        self._status.setMinimumHeight(120)
        self._status.setMaximumHeight(200)
        self._status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        box.add_widget(self._status)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_refresh = PrimaryButton("刷新状态")
        btn_refresh.clicked.connect(lambda: self.refresh_status(report=True, probe=True))
        row.addWidget(btn_refresh)
        btn_yml = SecondaryButton("打开配置文件")
        btn_yml.clicked.connect(self._open_yml)
        row.addWidget(btn_yml)
        row.addStretch(1)
        box.add_layout(row)
        return box

    def _save_ocr(self) -> None:
        def _do() -> None:
            save_integrations_config(
                {
                    "ocr": {
                        "enabled": self._ocr_enabled.isChecked(),
                        "provider": "tesseract",
                        "tesseract_path": self._ocr_path.text().strip(),
                        "lang": self._ocr_lang.text().strip() or "eng",
                        "note": "图片 OCR；业务经 OcrClient 调用",
                    }
                }
            )
            load_integrations_config(force=True)
            self.refresh_status(report=False, probe=False)

        self._page.run_safe(_do, success_status="识字配置已保存")

    def _test_ocr(self) -> None:
        from services.integrations import get_client

        client = get_client("ocr")
        ok = bool(client.enabled and client.health_check())
        if ok:
            show_info(self._page, "识字程序可用。")
            self._page.report_status("识字连通正常")
        else:
            show_warning(self._page, "识字未就绪：请确认已启用，且程序路径正确。")

    def refresh_status(self, *, report: bool = True, probe: bool | None = None) -> None:
        if probe is None:
            probe = report
        lines = status_lines(probe=bool(probe))
        if self._status is None:
            return
        self._status.setPlainText("\n".join(lines) if lines else "（暂无登记的能力）")
        if report:
            self._page.report_status(
                "已探测能力连通" if probe else "已刷新能力状态（未联网）"
            )

    def _open_yml(self) -> None:
        import os
        import subprocess
        import sys

        from services.config_service import project_root

        path = project_root() / "config" / "integrations.yml"
        if not path.is_file():
            show_warning(self._page, f"未找到配置文件：{path}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as e:
            from core.user_messages import show_error

            show_error(self._page, f"无法打开文件：{e}")
