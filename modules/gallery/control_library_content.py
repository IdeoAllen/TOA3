# -*- coding: utf-8 -*-
"""控件库内容区（全部使用 widgets 控件库）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.user_messages import ask_confirm, show_error, show_info, show_saved, show_success, show_warning
from widgets import (
    CheckBox,
    ComboBox,
    CalendarWidget,
    DangerButton,
    DataTable,
    DateEdit,
    FormSection,
    HintLabel,
    InlineButton,
    LineEdit,
    ListWidget,
    MessageKindButton,
    PageTitle,
    PrimaryButton,
    ProgressBar,
    RadioButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
    Slider,
    SpinBox,
    Switch,
    TabWidget,
)


def build_control_library_content(parent: QWidget | None = None) -> ScrollPage:
    scroll = ScrollPage(parent)

    scroll.add_widget(PageTitle("控件库"))
    scroll.add_widget(HintLabel("标准控件全集 · 业务页仅从此库选用 · 样式由 config/themes → QSS 全局控制"))

    _section_labels(scroll)
    _section_buttons(scroll)
    _section_tool_cards(scroll)
    _section_messages(scroll)
    _section_inputs(scroll)
    _section_check_radio(scroll)
    _section_switch(scroll)
    _section_slider(scroll)
    _section_progress(scroll)
    _section_tabs(scroll)
    _section_table(scroll)
    _section_text_areas(scroll)
    _section_lists(scroll)
    _section_list_edit(scroll)
    scroll.add_stretch(1)
    return scroll


def _section_labels(scroll: ScrollPage) -> None:
    box = FormSection("标签与语义色")
    box.add_widget(PageTitle("页标题（14pt 粗体）"))
    from widgets import SectionTitle

    box.add_widget(SectionTitle("分区标题（12pt 粗体）"))
    box.add_widget(QLabel("正文内容（10pt）"))
    box.add_widget(HintLabel("辅助说明（9pt 次要色）"))
    for text, kind in (
        ("操作成功", "success"),
        ("请注意", "warning"),
        ("发生错误", "danger"),
        ("提示信息", "info"),
    ):
        box.add_widget(SemanticLabel(text, kind=kind))
    scroll.add_widget(box)


def _section_buttons(scroll: ScrollPage) -> None:
    box = FormSection("按钮")
    row = QHBoxLayout()
    row.addWidget(PrimaryButton("主按钮"))
    row.addWidget(SecondaryButton("次按钮"))
    row.addWidget(DangerButton("危险"))
    row.addWidget(InlineButton("行内"))
    box.add_layout(row)

    dis = QHBoxLayout()
    b1 = PrimaryButton("主按钮 · 禁用")
    b1.setEnabled(False)
    dis.addWidget(b1)
    b2 = SecondaryButton("次按钮 · 禁用")
    b2.setEnabled(False)
    dis.addWidget(b2)
    box.add_layout(dis)
    scroll.add_widget(box)


def _section_tool_cards(scroll: ScrollPage) -> None:
    from widgets.tool_cards import ToolLaunchCard

    box = FormSection("工具启动卡（首页办公增效）")
    box.add_widget(HintLabel("图标 + 标题 + 快捷键提示；点击即跳转模块。"))
    row = QHBoxLayout()
    for title, sub, hk, icon in (
        ("快速记事", "会议纪要草稿", "Alt+N", "file-text"),
        ("图片转文字", "OCR 一键提取", "Alt+O", "file-text"),
        ("截图工具", "区域 / 全屏", "Alt+A", "camera"),
    ):
        card = ToolLaunchCard(title, subtitle=sub, shortcut=f"快捷键 {hk}", icon=icon)
        row.addWidget(card)
    row.addStretch(1)
    box.add_layout(row)
    scroll.add_widget(box)


def _section_messages(scroll: ScrollPage) -> None:
    box = FormSection("统一提示窗（主题化 MessageDialog）")
    box.add_widget(HintLabel("业务代码通过 core.user_messages 调用；禁止裸 QMessageBox。"))
    box.add_widget(HintLabel("生成/导出完成必须 show_saved（绿勾「完成」+「打开所在目录」），勿用蓝色信息窗。"))
    row = QHBoxLayout()
    host = scroll.content_widget

    btn_info = MessageKindButton("信息", kind="info")
    btn_info.clicked.connect(
        lambda: show_info(host, "这是一条信息提示，样式与当前主题一致。")
    )
    row.addWidget(btn_info)

    btn_warn = MessageKindButton("警告", kind="warning")
    btn_warn.clicked.connect(
        lambda: show_warning(host, "请注意：操作前请确认数据已备份。")
    )
    row.addWidget(btn_warn)

    btn_err = MessageKindButton("错误", kind="error")
    btn_err.clicked.connect(lambda: show_error(host, "操作失败：示例错误信息。"))
    row.addWidget(btn_err)

    btn_ok = MessageKindButton("成功", kind="success")
    btn_ok.clicked.connect(
        lambda: show_success(host, "操作已完成（无文件产出时可不带打开目录）。")
    )
    row.addWidget(btn_ok)

    btn_saved = MessageKindButton("生成完成", kind="success")
    btn_saved.clicked.connect(
        lambda: show_saved(
            host,
            "示例：文件已生成。\n请点「打开所在目录」验证。",
            Path.home() / "Desktop",
        )
    )
    row.addWidget(btn_saved)

    btn_confirm = MessageKindButton("确认", kind="confirm")
    btn_confirm.clicked.connect(
        lambda: show_info(
            host,
            "已确认" if ask_confirm(host, "确定执行此操作？") else "已取消",
        )
    )
    row.addWidget(btn_confirm)
    row.addStretch(1)
    box.add_layout(row)
    scroll.add_widget(box)


def _section_inputs(scroll: ScrollPage) -> None:
    box = FormSection("输入")
    box.add_widget(LineEdit("单行文本"))
    row = QHBoxLayout()
    ro = LineEdit("只读")
    ro.setReadOnly(True)
    row.addWidget(ro)
    dis = LineEdit("禁用")
    dis.setEnabled(False)
    row.addWidget(dis)
    box.add_layout(row)

    combo = ComboBox()
    combo.addItems(["选项 A", "选项 B", "选项 C"])
    box.add_widget(combo)

    spin = SpinBox()
    spin.setRange(1, 99)
    spin.setValue(8)
    box.add_widget(spin)
    box.add_widget(HintLabel("数字框：上下三角分开，悬停/按下有反馈；数值字色跟主题正文。"))
    box.add_widget(HintLabel("下拉：整框一体，右侧仅箭头无竖线分隔；点框即展开。"))
    box.add_widget(HintLabel("日期：单框一体（日期字 + 日历图标），点任意处打开主题月历。"))
    box.add_widget(DateEdit())
    box.add_widget(CalendarWidget())
    scroll.add_widget(box)


def _section_text_areas(scroll: ScrollPage) -> None:
    box = FormSection("多行文本")
    box.add_widget(ReadOnlyPlainTextEdit("只读多行文本预览区"))
    scroll.add_widget(box)


def _section_list_edit(scroll: ScrollPage) -> None:
    from widgets.list_edit import ListPanel

    box = FormSection("List + Edit 套件")
    panel = ListPanel(hint="标准增删改查操作栏；业务页继承或组合使用。")
    panel.set_items(["示例条目 A", "示例条目 B", "示例条目 C"])
    box.add_widget(panel)
    scroll.add_widget(box)


def _section_lists(scroll: ScrollPage) -> None:
    box = FormSection("列表")
    lst = ListWidget()
    lst.addItems(["历史条目 A", "历史条目 B", "历史条目 C"])
    box.add_widget(lst)
    scroll.add_widget(box)


def _section_check_radio(scroll: ScrollPage) -> None:
    box = FormSection("勾选与单选")
    cb1 = CheckBox("已选中")
    cb1.setChecked(True)
    box.add_widget(cb1)
    box.add_widget(CheckBox("未选中"))
    cbd = CheckBox("禁用")
    cbd.setEnabled(False)
    box.add_widget(cbd)
    r1 = RadioButton("选项 A")
    r1.setChecked(True)
    box.add_widget(r1)
    box.add_widget(RadioButton("选项 B"))
    scroll.add_widget(box)


def _section_switch(scroll: ScrollPage) -> None:
    box = FormSection("开关")
    box.add_widget(HintLabel("拨动开关 · 业务页用 widgets.Switch（objectName=Switch）"))
    on = Switch("已开启")
    on.setChecked(True)
    box.add_widget(on)
    box.add_widget(Switch("已关闭"))
    off = Switch("禁用")
    off.setEnabled(False)
    box.add_widget(off)
    scroll.add_widget(box)


def _section_slider(scroll: ScrollPage) -> None:
    box = FormSection("滑块")
    box.add_widget(HintLabel("水平滑块 · 默认 0–100，业务页用 widgets.Slider"))
    sl = Slider(value=42)
    box.add_widget(sl)
    scroll.add_widget(box)


def _section_progress(scroll: ScrollPage) -> None:
    box = FormSection("进度条")
    pb = ProgressBar()
    pb.setValue(42)
    box.add_widget(pb)
    scroll.add_widget(box)


def _section_tabs(scroll: ScrollPage) -> None:
    box = FormSection("页签")
    tabs = TabWidget()
    for name in ("页签一", "页签二", "页签三"):
        w = QWidget()
        QVBoxLayout(w).addWidget(QLabel(f"{name} 内容"))
        tabs.addTab(w, name)
    box.add_widget(tabs)
    scroll.add_widget(box)


def _section_table(scroll: ScrollPage) -> None:
    box = FormSection("表格")
    table = DataTable(3, 2)
    table.set_headers(["列 A", "列 B"])
    table.set_rows([("甲", "1"), ("乙", "2"), ("丙", "3")])
    table.selectRow(0)
    box.add_widget(table)
    scroll.add_widget(box)
