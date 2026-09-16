# -*- coding: utf-8 -*-
"""TOA3 控件库 — 业务页唯一控件来源（对照 modules/gallery 验收）。"""
from __future__ import annotations

from widgets.buttons import (
    DangerButton,
    InlineButton,
    MenuButton,
    MessageKindButton,
    PrimaryButton,
    SecondaryButton,
)
from widgets.containers import (
    FormRow,
    FormSection,
    GridBox,
    HBox,
    PageHeader,
    PathRow,
    ScrollPage,
    SplitPane,
    VBox,
)
from widgets.dialog_actions import DialogButtonRow
from widgets.displays import CalendarWidget, DataTable, ListWidget, ProgressBar, SoftActivityBar, TabWidget, TreeWidget
from widgets.inputs import (
    ComboBox,
    DateEdit,
    HotkeyCaptureEdit,
    LineEdit,
    PasswordLineEdit,
    PlainTextEdit,
    ReadOnlyPlainTextEdit,
    ReadOnlyTextEdit,
    SpinBox,
    TextEdit,
)
from widgets.selection import CheckBox, RadioButton, Slider, Switch
from widgets.themed_labels import HintLabel, PageTitle, SectionTitle, SemanticLabel
from widgets.theme_picker import ThemePicker
from widgets.tool_cards import StatusDot, ToolLaunchCard
from widgets.home_hero import HomeHeroBand, HomePromiseStrip, HomeSectionLabel
from widgets.charts import PieChartWidget

# list_edit 依赖 BaseDialog，延迟导出以免与 core.user_messages 循环导入
_LIST_EDIT_NAMES = frozenset(
    {
        "ListPanel",
        "ManageTablePanel",
        "FormEditDialog",
        "confirm_delete",
        "manage_panel_from_fields",
    }
)

CONTROL_CLASSES = [
    "PageTitle",
    "SectionTitle",
    "HintLabel",
    "SemanticLabel",
    "PrimaryButton",
    "SecondaryButton",
    "MenuButton",
    "DangerButton",
    "MessageKindButton",
    "InlineButton",
    "LineEdit",
    "HotkeyCaptureEdit",
    "PasswordLineEdit",
    "PlainTextEdit",
    "ReadOnlyPlainTextEdit",
    "TextEdit",
    "ReadOnlyTextEdit",
    "ComboBox",
    "SpinBox",
    "DateEdit",
    "CalendarWidget",
    "CheckBox",
    "Switch",
    "RadioButton",
    "Slider",
    "FormSection",
    "ScrollPage",
    "PageHeader",
    "HBox",
    "VBox",
    "FormRow",
    "PathRow",
    "GridBox",
    "SplitPane",
    "ListWidget",
    "TreeWidget",
    "ProgressBar",
    "SoftActivityBar",
    "TabWidget",
    "DataTable",
    "DialogButtonRow",
    "ListPanel",
    "ManageTablePanel",
    "FormEditDialog",
    "confirm_delete",
    "manage_panel_from_fields",
    "ToolLaunchCard",
    "StatusDot",
    "HomeHeroBand",
    "HomePromiseStrip",
    "HomeSectionLabel",
    "ThemePicker",
    "PieChartWidget",
]

__all__ = CONTROL_CLASSES


def __getattr__(name: str):
    if name in _LIST_EDIT_NAMES:
        from widgets import list_edit as _le

        return getattr(_le, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
