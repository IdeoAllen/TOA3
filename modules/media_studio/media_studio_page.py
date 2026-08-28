# -*- coding: utf-8 -*-
"""媒体工坊：文生图（本地 WebUI / 云端）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from services.model_ready_registry import list_ready
from services.model_catalog import (
    get_active_profile_id,
    set_active_profile_id,
)
from widgets import (
    ComboBox,
    FormSection,
    HintLabel,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ScrollPage,
    SecondaryButton,
    SpinBox,
)


class MediaStudioPage(BasePage):
    page_id = "media_studio"
    page_title = "媒体工坊"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._profiles: list[dict] = []
        self._profile_ids: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "媒体工坊",
                "文生图：从「可用」生图模型中选择（ComfyUI / WebUI / 云端）。"
                "未就绪项在「系统设置 → 能力接入 → 模型库」。",
            )
        )

        model_box = FormSection("生图模型")
        row = QHBoxLayout()
        row.addWidget(HintLabel("当前配置"))
        self._profile_combo = ComboBox()
        self._profile_combo.setMinimumWidth(260)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        row.addWidget(self._profile_combo, 1)
        model_box.add_layout(row)
        model_box.add_widget(
            HintLabel(
                "推荐本地 ComfyUI（8188）；权重不进安装包，见 scripts/model_hub_comfyui.py"
            )
        )
        self._empty_hint = HintLabel("")
        model_box.add_widget(self._empty_hint)
        scroll.add_widget(model_box)

        prompt_box = FormSection("画面描述")
        self._prompt = PlainTextEdit()
        self._prompt.setMinimumHeight(100)
        self._prompt.setPlaceholderText("描述你想生成的画面…")
        prompt_box.add_widget(self._prompt)
        size_row = QHBoxLayout()
        self._w = SpinBox()
        self._w.setRange(256, 2048)
        self._w.setValue(768)
        self._w.setSuffix(" 宽")
        size_row.addWidget(self._w)
        self._h = SpinBox()
        self._h.setRange(256, 2048)
        self._h.setValue(768)
        self._h.setSuffix(" 高")
        size_row.addWidget(self._h)
        size_row.addStretch(1)
        prompt_box.add_layout(size_row)
        scroll.add_widget(prompt_box)

        actions = QHBoxLayout()
        btn = PrimaryButton("生成图片")
        btn.clicked.connect(self._on_generate)
        actions.addWidget(btn)
        btn_cfg = SecondaryButton("打开模型库")
        btn_cfg.clicked.connect(self._open_settings)
        actions.addWidget(btn_cfg)
        actions.addStretch(1)
        scroll.add_layout(actions)

        prev = FormSection("预览")
        self._preview = HintLabel("生成后显示预览")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(200)
        prev.add_widget(self._preview)
        scroll.add_widget(prev)
        scroll.add_stretch(1)

        self._reload_profiles()

    def primary_focus_widget(self):
        return self._prompt

    def on_enter(self) -> None:
        self._reload_profiles(select_active=True)
        self.report_status("媒体工坊 · 文生图")

    def _reload_profiles(self, *, select_active: bool = False) -> None:
        self._profiles = list_ready("image_gen", ready_only=True)
        self._profile_ids = [
            str(p.get("id") or "") for p in self._profiles if p.get("source") == "catalog"
        ]
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for p in self._profiles:
            if p.get("source") != "catalog":
                continue
            label = str(p.get("label") or p.get("id") or "未命名")
            provider = str(p.get("provider") or "")
            if provider:
                label = f"{label} · {provider}"
            self._profile_combo.addItem(label, str(p.get("id") or ""))
        self._profile_combo.blockSignals(False)
        if not self._profile_ids:
            self._empty_hint.setText(
                "暂无可用生图模型 → 系统设置 → 模型库：启动 ComfyUI 或配置云端 Key。"
            )
            self._profile_combo.addItem("（无可用模型）", "")
        else:
            self._empty_hint.setText("")
        if select_active and self._profile_ids:
            active = get_active_profile_id("image_gen")
            idx = self._profile_ids.index(active) if active in self._profile_ids else 0
            self._profile_combo.setCurrentIndex(idx)

    def _current_profile_id(self) -> str:
        idx = self._profile_combo.currentIndex()
        if 0 <= idx < len(self._profile_ids):
            return self._profile_ids[idx]
        return ""

    def _on_profile_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._profile_ids):
            return
        pid = self._profile_ids[index]
        if pid:
            set_active_profile_id("image_gen", pid)

    def _on_generate(self) -> None:
        prompt = self._prompt.toPlainText().strip()
        if not prompt:
            show_warning(self, "请先填写画面描述。")
            return
        pid = self._current_profile_id()
        if not pid:
            show_warning(self, "暂无可用生图模型，请先到「系统设置 → 模型库」配置 ComfyUI 或云端 Key。")
            return
        w, h = self._w.value(), self._h.value()

        def _run() -> None:
            from services.integrations import get_client

            client = get_client("image_gen")
            path = client.generate(prompt, width=w, height=h, profile_id=pid)
            self._show_preview(path)
            show_saved(self, "图片已生成", str(path.parent))

        self.run_safe(_run, title="图像生成失败")

    def _show_preview(self, path: Path) -> None:
        pix = QPixmap(str(path))
        if pix.isNull():
            self._preview.setText(path.name)
            return
        scaled = pix.scaled(
            480,
            360,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(scaled)
        self.report_status("预览已更新", level=StatusLevel.SUCCESS)

    def _open_settings(self) -> None:
        shell = self.window()
        if shell is not None and hasattr(shell, "navigate"):
            shell.navigate("system_settings")
            page = getattr(shell, "_pages", {}).get("system_settings")
            if page is not None and hasattr(page, "open_model_hub_tab"):
                page.open_model_hub_tab()
            elif page is not None and hasattr(page, "open_capability_tab"):
                page.open_capability_tab(image=True)
