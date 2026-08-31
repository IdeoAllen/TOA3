# -*- coding: utf-8 -*-
"""Qt 按键事件 ↔ hotkeys.yml 字符串（与 hotkey_service._parse_hotkey 对齐）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

_MODIFIER_ONLY = frozenset(
    {
        Qt.Key.Key_Control,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Meta,
        Qt.Key.Key_AltGr,
    }
)

_KEY_NAMES: dict[int, str] = {
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Return: "Return",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Pause: "Pause",
    Qt.Key.Key_Print: "Print",
    Qt.Key.Key_CapsLock: "CapsLock",
    Qt.Key.Key_NumLock: "NumLock",
    Qt.Key.Key_ScrollLock: "ScrollLock",
}
for _n in range(1, 25):
    _KEY_NAMES[getattr(Qt.Key, f"Key_F{_n}")] = f"F{_n}"


def _key_token(key: int, text: str = "") -> str:
    if key in _KEY_NAMES:
        return _KEY_NAMES[key]
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key)
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key)
    t = str(text or "").strip()
    if len(t) == 1 and t.isprintable() and not t.isspace():
        return t.upper() if t.isalpha() else t
    return ""


def format_qt_key_event(
    event: QKeyEvent,
    *,
    allow_page_keys: bool = False,
    require_modifier: bool = True,
) -> str:
    """把一次按键录制成 Alt+Shift+C / F11 / K 等字符串；无法录制时返回空串。"""
    key = int(event.key())
    if key in _MODIFIER_ONLY:
        return ""
    token = _key_token(key, event.text())
    if not token:
        return ""

    mods = event.modifiers()
    parts: list[str] = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.KeyboardModifier.MetaModifier:
        parts.append("Meta")

    if require_modifier and not parts and not allow_page_keys:
        if token.startswith("F") and token[1:].isdigit():
            return token
        return ""

    if not parts and allow_page_keys:
        return token

    if not parts:
        return token

    return "+".join(parts + [token])
