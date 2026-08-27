# -*- coding: utf-8 -*-
"""系统设置 · 能力接入：大模型 / OCR / 状态总览。"""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.integrations.config import (
    integration_config,
    load_integrations_config,
    save_integrations_config,
)
from services.integrations.registry import status_lines
from services.integrations.secrets import get_secret, set_secret
from widgets import (
    CheckBox,
    FormSection,
    HintLabel,
    LineEdit,
    PasswordLineEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
    SpinBox,
    TabWidget,
)


class IntegrationsSection(QWidget):
    """能力接入分类区（放入设置页「能力接入」页签）。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(
            HintLabel(
                "办公能力统一经 services/integrations 接入。"
                "API Key 仅存本机 data/user/integrations_secrets.json，不写进仓库。"
            )
        )

        tabs = TabWidget()
        tabs.addTab(self._build_llm_tab(), "大模型")
        tabs.addTab(self._build_harness_tab(), "Harness")
        tabs.addTab(self._build_ocr_tab(), "OCR 识别")
        tabs.addTab(self._build_status_tab(), "连通总览")
        lay.addWidget(tabs)

    def _build_llm_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
        box = FormSection("大模型（OpenAI 兼容）")
        box.add_widget(
            HintLabel(
                "适用于文案润色、摘要、模板填充。"
                "兼容 DeepSeek / 通义 / 月之暗面 / 本地 Ollama（OpenAI 协议）等。"
            )
        )
        cfg = integration_config("llm")
        form = QFormLayout()
        self._llm_enabled = CheckBox("启用大模型能力")
        self._llm_enabled.setChecked(bool(cfg.get("enabled")))
        form.addRow("", self._llm_enabled)

        self._llm_base = LineEdit(str(cfg.get("api_base") or ""))
        self._llm_base.setPlaceholderText("例如 https://api.openai.com/v1 或 https://api.deepseek.com/v1")
        form.addRow("API 地址", self._llm_base)

        self._llm_model = LineEdit(str(cfg.get("model") or ""))
        self._llm_model.setPlaceholderText("例如 kimi-k2.6 / deepseek-chat / gpt-4o-mini")
        form.addRow("模型名", self._llm_model)

        self._llm_key = PasswordLineEdit()
        existing = get_secret("llm", "api_key")
        if existing:
            self._llm_key.setPlaceholderText("已保存（留空保留原密钥；填新值覆盖）")
        else:
            self._llm_key.setPlaceholderText("API Key（可选：也可用环境变量 TOA_LLM_API_KEY）")
        form.addRow("API Key", self._llm_key)

        self._llm_temp = SpinBox()
        self._llm_temp.setRange(0, 100)
        self._llm_temp.setValue(int(float(cfg.get("temperature", 0.7)) * 100))
        self._llm_temp.setSuffix("%")
        form.addRow("温度×100", self._llm_temp)

        box.add_layout(form)
        row = QHBoxLayout()
        btn_save = PrimaryButton("保存大模型配置")
        btn_save.clicked.connect(self._save_llm)
        row.addWidget(btn_save)
        btn_test = SecondaryButton("测试连通")
        btn_test.clicked.connect(self._test_llm)
        row.addWidget(btn_test)
        btn_clear = SecondaryButton("清除本机 Key")
        btn_clear.clicked.connect(self._clear_llm_key)
        row.addWidget(btn_clear)
        row.addStretch(1)
        box.add_layout(row)
        outer.addWidget(box)
        outer.addStretch(1)
        return w

    def _build_harness_tab(self) -> QWidget:
        from modules.system_settings.harness_section import HarnessSection

        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(HarnessSection(self._page))
        return w

    def _build_ocr_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
        box = FormSection("OCR（Tesseract）")
        box.add_widget(
            HintLabel(
                "截图转文字 / 图片 OCR。装中文语言包后可将语言改为 chi_sim+eng。"
            )
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
        outer.addStretch(1)
        return w

    def _build_status_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
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
        outer.addWidget(box)
        outer.addStretch(1)
        self.refresh_status(report=False, probe=False)
        return w

    def _save_llm(self) -> None:
        base = self._llm_base.text().strip()
        model = self._llm_model.text().strip()
        enabled = self._llm_enabled.isChecked()
        if enabled and (not base or not model):
            show_warning(self._page, "启用大模型时请填写 API 地址与模型名。")
            return
        temp = max(0.0, min(1.0, self._llm_temp.value() / 100.0))

        def _do() -> None:
            save_integrations_config(
                {
                    "llm": {
                        "enabled": enabled,
                        "provider": "openai_compatible",
                        "api_base": base,
                        "model": model,
                        "temperature": temp,
                        "note": "摘要、改写、模板填充；密钥存本机 secrets",
                    }
                }
            )
            key = self._llm_key.text().strip()
            if key:
                set_secret("llm", "api_key", key)
                self._llm_key.clear()
                self._llm_key.setPlaceholderText("已保存（留空保留原密钥；填新值覆盖）")
            load_integrations_config(force=True)
            self.refresh_status(report=False, probe=False)

        self._page.run_safe(_do, success_status="大模型配置已保存")

    def _clear_llm_key(self) -> None:
        set_secret("llm", "api_key", "")
        self._llm_key.clear()
        self._llm_key.setPlaceholderText("API Key（可选：也可用环境变量 TOA_LLM_API_KEY）")
        self._page.report_status("已清除本机大模型 Key")
        show_info(self._page, "本机 API Key 已清除。")

    def _test_llm(self) -> None:
        from services.integrations import get_client

        client = get_client("llm")
        if not client.enabled:
            show_warning(self._page, "请先勾选「启用」并保存。")
            return
        if not client.health_check():
            show_warning(self._page, "配置不完整：需要 API 地址。")
            return
        try:
            text = client.complete("只用两个字回复：成功", system="你是连通测试助手。")
            show_info(self._page, f"连通正常。\n模型回复：{text[:80]}")
            self._page.report_status("大模型连通正常")
        except Exception as exc:
            show_warning(self._page, f"连通失败：{exc}")

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
        # 按钮刷新才联网探测；打开页/保存配置只读本地开关
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
        from pathlib import Path
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
