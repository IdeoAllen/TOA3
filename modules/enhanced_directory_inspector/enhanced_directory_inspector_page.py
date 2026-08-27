# -*- coding: utf-8 -*-
"""交付材料生成（利刃 / 破晓完整 PPT + 目录骨架）。"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_warning
from modules.enhanced_directory_inspector.enhanced_directory_inspector_service import (
    generate_deliverables,
)
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
)


class EnhancedDirectoryInspectorPage(BasePage):
    page_id = "enhanced_directory_inspector"
    page_title = "交付材料生成"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "交付材料生成",
                "选择班级根目录，生成标准文件夹结构 + 清单；按利刃/破晓模板生成完整交付 PPT。",
            )
        )

        form = FormSection("班级信息")
        name_row = QHBoxLayout()
        name_row.addWidget(HintLabel("班级名称"))
        self._class_name = LineEdit()
        self._class_name.setPlaceholderText("可选，用于清单标题与 PPT 占位替换")
        name_row.addWidget(self._class_name, 1)
        form.add_layout(name_row)

        path_row = QHBoxLayout()
        path_row.addWidget(HintLabel("班级根目录"))
        self._root = LineEdit()
        self._root.setPlaceholderText("选择班级交付根目录…")
        path_row.addWidget(self._root, 1)
        btn_browse = SecondaryButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        form.add_layout(path_row)

        type_row = QHBoxLayout()
        type_row.addWidget(HintLabel("项目模板"))
        self._project = ComboBox()
        self._project.addItem("利刃（lixiao）", "lixiao")
        self._project.addItem("破晓（poxiao）", "poxiao")
        type_row.addWidget(self._project, 1)
        form.add_layout(type_row)

        self._with_pptx = CheckBox("生成完整交付 PPT（需 python-pptx + 模板）")
        self._with_pptx.setChecked(True)
        form.add_widget(self._with_pptx)
        form.add_widget(
            HintLabel("PPT 优先走完整引擎（mapping_rules 精确配图）；失败时回退模板填充。")
        )
        scroll.add_widget(form)

        actions = QHBoxLayout()
        btn_go = PrimaryButton("生成交付材料")
        btn_go.clicked.connect(self._on_generate)
        actions.addWidget(btn_go)
        actions.addStretch(1)
        scroll.add_layout(actions)

        out_box = FormSection("结果")
        self._log = ReadOnlyPlainTextEdit()
        self._log.setMinimumHeight(180)
        out_box.add_widget(self._log)
        scroll.add_widget(out_box)
        scroll.add_stretch(1)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._root

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择班级根目录")
        if path:
            self._root.setText(path)

    def _on_generate(self) -> None:
        root = self._root.text().strip()
        if not root:
            show_warning(self, "请先选择班级根目录。")
            return
        project_type = self._project.currentData() or "lixiao"

        def _run() -> None:
            result = generate_deliverables(
                root,
                class_name=self._class_name.text().strip(),
                with_pptx=self._with_pptx.isChecked(),
                project_type=str(project_type),
            )
            self._log.setPlainText(result.summary)
            self.report_status("交付材料已生成", level=StatusLevel.SUCCESS)
            show_saved(self, f"已写入：\n{result.class_root}", result.class_root)

        self.run_safe(_run, title="生成失败")

    def on_enter(self) -> None:
        self.report_status("交付材料生成")
        self.schedule_primary_focus()
