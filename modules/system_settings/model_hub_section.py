# -*- coding: utf-8 -*-
"""系统设置 · 模型库（Ready 列表 + 本机生图安装）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from core.user_messages import show_info
from services.local_image_setup import status_summary
from services.model_catalog import list_capabilities
from services.model_ready_registry import ReadyStatus, list_all_grouped, list_ready
from widgets import (
    FormSection,
    HintLabel,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    SecondaryButton,
)


class ModelHubSection(QWidget):
    """就绪总览 + 本机生图安装入口。"""

    def __init__(self, parent: BasePage) -> None:
        super().__init__(parent)
        self._page = parent
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(
            HintLabel(
                "本机生图：点一次「安装本机生图」即可（自动下载或从 ComfyUI 目录找已有文件）。"
                "ComfyUI 专业对接下一步再做。"
            )
        )

        img = FormSection("生图算力")
        self._img_status = HintLabel("")
        self._img_status.setWordWrap(True)
        img.add_widget(self._img_status)
        img_row = QHBoxLayout()
        btn_install = PrimaryButton("安装本机生图…")
        btn_install.clicked.connect(self._on_install_local)
        img_row.addWidget(btn_install)
        img_row.addStretch(1)
        img.add_layout(img_row)
        lay.addWidget(img)

        box = FormSection("就绪列表（算力卡包）")
        self._view = ReadOnlyPlainTextEdit()
        self._view.setMinimumHeight(280)
        box.add_widget(self._view)
        row = QHBoxLayout()
        btn_refresh = PrimaryButton("刷新")
        btn_refresh.clicked.connect(lambda: self.refresh(report=True))
        row.addWidget(btn_refresh)
        btn_llm = SecondaryButton("配置文本大模型")
        btn_llm.clicked.connect(lambda: self._goto_capability("大模型"))
        row.addWidget(btn_llm)
        btn_models = SecondaryButton("绑定 / 设默认")
        btn_models.clicked.connect(self._goto_registry)
        row.addWidget(btn_models)
        row.addStretch(1)
        box.add_layout(row)
        lay.addWidget(box)
        lay.addStretch(1)
        self.refresh(report=False)

    def refresh(self, *, report: bool = True) -> None:
        from services.model_ready_registry import refresh_local_endpoint_probes

        try:
            refresh_local_endpoint_probes(deep=False, force=False)
        except Exception:
            pass

        self._img_status.setText(status_summary())

        lines: list[str] = []
        grouped = list_all_grouped()
        cap_labels = {
            "text_llm": "文本大模型",
            "image_gen": "图像生成",
        }
        for cap in list_capabilities():
            title = cap_labels.get(cap, cap)
            lines.append(f"【{title}】")
            items = grouped.get(cap) or []
            if not items:
                lines.append("  （无登记配置）")
                lines.append("")
                continue
            for row in items:
                mark = "✓" if row.get("status") == ReadyStatus.READY else "○"
                src = "本机文件" if row.get("source") != "catalog" else row.get("provider", "")
                lines.append(
                    f"  {mark} {row.get('label')} · {row.get('status_label')} [{src}]"
                )
                hint = str(row.get("hint") or "").strip()
                if hint and row.get("status") != ReadyStatus.READY:
                    lines.append(f"      → {hint}")
            ready_n = len(list_ready(cap, ready_only=True))
            lines.append(f"  可用 {ready_n} / 共 {len(items)}")
            lines.append("")
        self._view.setPlainText("\n".join(lines).strip())
        if report:
            self._page.report_status("已刷新算力来源")

    def _on_install_local(self) -> None:
        from modules.system_settings.local_image_setup_dialog import LocalImageSetupDialog

        dlg = LocalImageSetupDialog(self)
        dlg.exec()
        self.refresh(report=False)
        if dlg.ready:
            self._page.report_status("本机生图已就绪")

    def _goto_capability(self, tab_name: str) -> None:
        integrations = getattr(self._page, "_integrations", None)
        if integrations is not None and hasattr(integrations, "select_sub_tab"):
            integrations.select_sub_tab(tab_name)
            return
        shell = self._page.window()
        if shell is not None and hasattr(shell, "navigate"):
            self._page.open_capability_tab(image=(tab_name == "图像生成"))

    def _goto_registry(self) -> None:
        if hasattr(self._page, "open_model_hub_tab"):
            # 模型管理与模型库可能同区；优先跳模型管理
            page = self._page
            if hasattr(page, "open_models_tab"):
                page.open_models_tab()
            else:
                page.open_model_hub_tab()

    def _open_comfy_script_hint(self) -> None:
        from services.config_service import project_root

        script = project_root() / "scripts" / "model_hub_comfyui.py"
        show_info(
            self._page,
            "专业用户终端运行：\npython scripts/model_hub_comfyui.py\n\n"
            "普通用户请用「安装本机生图」。\n\n"
            f"脚本路径：{script}",
        )
