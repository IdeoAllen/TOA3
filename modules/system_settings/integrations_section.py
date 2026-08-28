# -*- coding: utf-8 -*-
"""系统设置 · 能力接入：模型管理 / OCR / Harness / 连通总览。"""
from __future__ import annotations

from typing import TYPE_CHECKING

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
    TabWidget,
)

if TYPE_CHECKING:
    from modules.system_settings.model_registry_section import ModelRegistrySection


class IntegrationsSection(QWidget):
    """能力接入分类区（管理员全量；终端用户仅模型相关）。"""

    def __init__(self, parent: BasePage, *, admin: bool = True) -> None:
        super().__init__(parent)
        self._page = parent
        self._admin = admin
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        if admin:
            lay.addWidget(
                HintLabel("三方能力经 integrations 接入；Key 仅存本机 data/user。")
            )
        else:
            lay.addWidget(HintLabel("配置模型 URL、模型名与 API Key（仅存本机）。"))

        self._tabs: TabWidget | None = None
        self._model_registry: ModelRegistrySection | None = None

        if admin:
            self._tabs = TabWidget()
            self._tabs.setDocumentMode(True)
            self._tabs.addTab(self._build_model_registry_tab(), "模型管理")
            self._tabs.addTab(self._build_harness_tab(), "Harness")
            self._tabs.addTab(self._build_ocr_tab(), "OCR 识别")
            self._tabs.addTab(self._build_status_tab(), "连通总览")
            lay.addWidget(self._tabs, 1)
        else:
            from modules.system_settings.model_registry_section import ModelRegistrySection

            self._model_registry = ModelRegistrySection(self._page)
            self._model_registry.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            lay.addWidget(self._model_registry, 1)

    def select_sub_tab(self, name: str) -> None:
        aliases = {
            "模型库": "模型管理",
            "大模型": "模型管理",
            "图像生成": "模型管理",
        }
        target = aliases.get(name, name)
        cap_filter: str | None = None
        if name == "大模型":
            cap_filter = "text_llm"
        elif name == "图像生成":
            cap_filter = "image_gen"
        if self._tabs is not None:
            for i in range(self._tabs.count()):
                if self._tabs.tabText(i) == target:
                    self._tabs.setCurrentIndex(i)
                    break
        if self._model_registry is not None and cap_filter is not None:
            self._model_registry.set_capability_filter(cap_filter)

    def _build_model_registry_tab(self) -> QWidget:
        from modules.system_settings.model_registry_section import ModelRegistrySection

        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._model_registry = ModelRegistrySection(self._page)
        self._model_registry.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        outer.addWidget(self._model_registry, 1)
        return w

    def _build_harness_tab(self) -> QWidget:
        from modules.system_settings.harness_section import HarnessSection

        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(HarnessSection(self._page))
        return w

    def _build_ocr_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        box = FormSection("OCR（Tesseract）")
        box.add_widget(
            HintLabel("截图转文字；中文请装 chi_sim 语言包后改为 chi_sim+eng。")
        )
        cfg = integration_config("ocr")
        form = QFormLayout()
        self._ocr_enabled = CheckBox("启用 OCR")
        self._ocr_enabled.setChecked(bool(cfg.get("enabled", True)))
        form.addRow("", self._ocr_enabled)

        self._ocr_path = LineEdit(str(cfg.get("tesseract_path") or ""))
        self._ocr_path.setPlaceholderText(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        form.addRow("Tesseract 路径", self._ocr_path)

        self._ocr_lang = LineEdit(str(cfg.get("lang") or "eng"))
        self._ocr_lang.setPlaceholderText("eng 或 chi_sim+eng")
        form.addRow("语言包", self._ocr_lang)

        box.add_layout(form)
        row = QHBoxLayout()
        btn_save = PrimaryButton("保存 OCR 配置")
        btn_save.clicked.connect(self._save_ocr)
        row.addWidget(btn_save)
        btn_test = SecondaryButton("测试连通")
        btn_test.clicked.connect(self._test_ocr)
        row.addWidget(btn_test)
        row.addStretch(1)
        box.add_layout(row)
        outer.addWidget(box)
        return w

    def _build_status_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        box = FormSection("全部能力状态")
        self._status = ReadOnlyPlainTextEdit()
        self._status.setMinimumHeight(180)
        box.add_widget(self._status)
        row = QHBoxLayout()
        btn_refresh = PrimaryButton("刷新状态")
        btn_refresh.clicked.connect(lambda: self.refresh_status(report=True, probe=True))
        row.addWidget(btn_refresh)
        btn_yml = SecondaryButton("打开 integrations.yml")
        btn_yml.clicked.connect(self._open_yml)
        row.addWidget(btn_yml)
        row.addStretch(1)
        box.add_layout(row)
        outer.addWidget(box, 1)
        self.refresh_status(report=False, probe=False)
        return w

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

        self._page.run_safe(_do, success_status="OCR 配置已保存")

    def _test_ocr(self) -> None:
        from services.integrations import get_client

        client = get_client("ocr")
        ok = bool(client.enabled and client.health_check())
        if ok:
            show_info(self._page, "OCR 路径可用。")
            self._page.report_status("OCR 连通正常")
        else:
            show_warning(self._page, "OCR 未就绪：检查是否启用、tesseract 路径是否正确。")

    def refresh_status(self, *, report: bool = True, probe: bool | None = None) -> None:
        if probe is None:
            probe = report
        lines = status_lines(probe=bool(probe))
        if not hasattr(self, "_status") or self._status is None:
            return
        self._status.setPlainText("\n".join(lines) if lines else "（暂无登记的三方能力）")
        if report:
            self._page.report_status(
                "已探测三方能力连通" if probe else "已刷新三方能力状态（未联网）"
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
