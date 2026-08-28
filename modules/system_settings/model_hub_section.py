# -*- coding: utf-8 -*-
"""系统设置 · 模型库（Ready 列表，ComfyUI 式）。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.base_page import BasePage
from services.model_catalog import list_capabilities
from services.model_ready_registry import ReadyStatus, list_all_grouped, list_ready
from widgets import FormSection, HintLabel, PrimaryButton, ReadOnlyPlainTextEdit, SecondaryButton


class ModelHubSection(QWidget):
  """只读 v1：展示各能力下 Ready / 待配置 / 待下载。"""

  def __init__(self, parent: BasePage) -> None:
    super().__init__(parent)
    self._page = parent
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)

    lay.addWidget(
      HintLabel(
        "对标 ComfyUI：安装包不含模型权重。任务页只从「可用」列表选模型；"
        "缺密钥、缺端点、缺权重在此查看并去「能力接入」配置或按脚本下载。"
      )
    )

    box = FormSection("就绪列表")
    self._view = ReadOnlyPlainTextEdit()
    self._view.setMinimumHeight(320)
    box.add_widget(self._view)
    row = QHBoxLayout()
    btn_refresh = PrimaryButton("刷新")
    btn_refresh.clicked.connect(lambda: self.refresh(report=True))
    row.addWidget(btn_refresh)
    btn_llm = SecondaryButton("配置文本大模型")
    btn_llm.clicked.connect(lambda: self._goto_capability("大模型"))
    row.addWidget(btn_llm)
    btn_img = SecondaryButton("配置图像生成")
    btn_img.clicked.connect(lambda: self._goto_capability("图像生成"))
    row.addWidget(btn_img)
    btn_script = SecondaryButton("ComfyUI 指引")
    btn_script.clicked.connect(self._open_comfy_script_hint)
    row.addWidget(btn_script)
    row.addStretch(1)
    box.add_layout(row)
    lay.addWidget(box)
    lay.addStretch(1)
    self.refresh(report=False)

  def refresh(self, *, report: bool = True) -> None:
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
      self._page.report_status("已刷新模型库")

  def _goto_capability(self, tab_name: str) -> None:
    shell = self._page.window()
    integrations = getattr(self._page, "_integrations", None)
    if integrations is not None and hasattr(integrations, "select_sub_tab"):
      integrations.select_sub_tab(tab_name)
      return
    if shell is not None and hasattr(shell, "navigate"):
      self._page.open_capability_tab(image=(tab_name == "图像生成"))

  def _open_comfy_script_hint(self) -> None:
    from core.user_messages import show_info
    from services.config_service import project_root

    script = project_root() / "scripts" / "model_hub_comfyui.py"
    show_info(
      self._page,
      "终端运行：\npython scripts/model_hub_comfyui.py\n\n"
      f"脚本路径：{script}",
    )
