# -*- coding: utf-8 -*-
"""TOA3 控件库 — 业务页唯一控件来源（对照 modules/gallery 验收）。"""
from __future__ import annotations

from widgets.buttons import DangerButton, InlineButton, MessageKindButton, PrimaryButton, SecondaryButton
from widgets.containers import FormSection, PageHeader, ScrollPage
from widgets.dialog_actions import DialogButtonRow
from widgets.displays import CalendarWidget, DataTable, ListWidget, ProgressBar, TabWidget, TreeWidget
from widgets.inputs import (
    ComboBox,
    DateEdit,
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
from widgets.tool_cards import StatusDot, ToolLaunchCard

CONTROL_CLASSES = [
    "PageTitle",
    "SectionTitle",
    "HintLabel",
    "SemanticLabel",
    "PrimaryButton",
    "SecondaryButton",
    "DangerButton",
    "MessageKindButton",
    "InlineButton",
    "LineEdit",
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
    "ListWidget",
    "TreeWidget",
    "ProgressBar",
    "TabWidget",
    "DataTable",
    "DialogButtonRow",
    "ListPanel",
    "FormEditDialog",
    "confirm_delete",
    "ToolLaunchCard",
    "StatusDot",
]

__all__ = CONTROL_CLASSES
