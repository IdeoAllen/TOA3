# -*- coding: utf-8 -*-
"""系统设置 · 热键（分层：全局 / 应用 / 页内；模块仅常用 + 按需添加）。"""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.config_service import get_hotkeys_config, save_hotkeys_config
from services.hotkey_service import get_hotkey_service
from services.module_hotkeys import (
    _GLOBAL_EXCLUDE_MODULES,
    get_configured_module_shortcuts,
    get_module_shortcut,
    list_hotkey_editor_modules,
    list_hotkey_picker_modules,
)
from services.screenshot_service import run_screenshot_hotkey
from widgets import CheckBox, ComboBox, FormSection, HintLabel, LineEdit, PrimaryButton, SecondaryButton


class HotkeysSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("热键与截图")
        self._page = parent
        hk = get_hotkeys_config()
        self._module_fields: dict[str, LineEdit] = {}
        self._mod_form: QFormLayout | None = None

        self.add_widget(
            HintLabel(
                "全局键须带 Alt/Ctrl（托盘隐藏时仍可用）。"
                "模块只需配常用的；其它用 Ctrl+K 或侧栏打开。"
            )
        )

        app_sec = FormSection("全局 · 应用 · 页内")
        form = QFormLayout()
        self._enable_screenshot = CheckBox("启用截图全局热键")
        self._enable_screenshot.setChecked(bool(hk.get("enable_screenshot", True)))
        form.addRow("截图", self._enable_screenshot)

        self._close_to_tray = CheckBox("关闭窗口时最小化到系统托盘")
        self._close_to_tray.setChecked(bool(hk.get("close_to_background", True)))
        form.addRow("托盘", self._close_to_tray)

        self._shot = LineEdit(str(hk.get("screenshot") or "Alt+A"))
        self._shot_region = LineEdit(str(hk.get("screenshot_region") or "Alt+Shift+A"))
        self._fullscreen = LineEdit(str(hk.get("toggle_fullscreen") or "F11"))
        self._summon = LineEdit(str(hk.get("summon_module_id") or "deduction_note_formatter"))
        self._exit = LineEdit(str(hk.get("exit_app") or "Ctrl+Q"))
        self._restart = LineEdit(str(hk.get("restart_app") or "Ctrl+Shift+R"))
        self._home_k = LineEdit(str(hk.get("home_jump_office") or "K"))
        self._home_i = LineEdit(str(hk.get("home_jump_image") or "I"))

        form.addRow("全局 · 区域截图", self._shot)
        form.addRow("全局 · 全屏截图", self._shot_region)
        form.addRow("应用 · 沉浸全屏", self._fullscreen)
        form.addRow("全局 · 呼出模块 ID", self._summon)
        form.addRow("应用 · 完全退出", self._exit)
        form.addRow("应用 · 重启", self._restart)
        form.addRow("页内 · 首页跳办公", self._home_k)
        form.addRow("页内 · 首页跳图片", self._home_i)
        app_sec.add_layout(form)
        self.add_widget(app_sec)

        mod_sec = FormSection("常用模块唤起")
        self._mod_form = QFormLayout()
        configured = get_configured_module_shortcuts()
        for mid, name, effective in list_hotkey_editor_modules():
            self._add_module_row(self._mod_form, mid, name, configured.get(mid, ""), effective)
        mod_sec.add_layout(self._mod_form)
        self.add_widget(mod_sec)

        add_row = QHBoxLayout()
        self._module_picker = ComboBox()
        self._module_picker.setMinimumWidth(220)
        for mid, name in list_hotkey_picker_modules():
            if mid not in self._module_fields:
                self._module_picker.addItem(name, mid)
        self._new_seq = LineEdit()
        self._new_seq.setPlaceholderText("如 Alt+Shift+T")
        btn_add = SecondaryButton("添加模块快捷键")
        btn_add.clicked.connect(self._add_picked_module)
        add_row.addWidget(self._module_picker)
        add_row.addWidget(self._new_seq)
        add_row.addWidget(btn_add)
        add_row.addStretch(1)
        self.add_layout(add_row)

        row = QHBoxLayout()
        btn_save = PrimaryButton("保存热键")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        btn_test = SecondaryButton("测试区域截图")
        btn_test.clicked.connect(lambda: run_screenshot_hotkey(self._page, full=False))
        row.addWidget(btn_test)
        btn_full = SecondaryButton("测试全屏截图")
        btn_full.clicked.connect(lambda: run_screenshot_hotkey(self._page, full=True))
        row.addWidget(btn_full)
        row.addStretch(1)
        self.add_layout(row)

    def _module_row_label(self, mid: str, name: str) -> str:
        if mid == "screenshot_tool":
            return f"{name}（与上方区域截图同键，勿改打开页）"
        if mid in _GLOBAL_EXCLUDE_MODULES:
            return f"{name}（仅应用前台）"
        return name

    def _add_module_row(
        self,
        form: QFormLayout,
        mid: str,
        name: str,
        configured: str,
        effective: str,
    ) -> None:
        field = LineEdit(configured)
        hint = effective or "留空或 none"
        if mid in _GLOBAL_EXCLUDE_MODULES and effective:
            hint = f"默认 {effective}（仅前台）"
        field.setPlaceholderText(hint)
        self._module_fields[mid] = field
        form.addRow(self._module_row_label(mid, name), field)

    def _add_picked_module(self) -> None:
        if self._mod_form is None:
            return
        mid = str(self._module_picker.currentData() or "").strip()
        if not mid:
            show_warning(self._page, "请选择模块。")
            return
        if mid in self._module_fields:
            show_info(self._page, "该模块已在列表中，直接改右侧输入框即可。")
            return
        name = self._module_picker.currentText()
        seq = self._new_seq.text().strip()
        self._add_module_row(self._mod_form, mid, name, seq, get_module_shortcut(mid))
        idx = self._module_picker.currentIndex()
        self._module_picker.removeItem(idx)
        self._new_seq.clear()
        self._page.report_status(f"已添加：{name}")

    def _save(self) -> None:
        module_shortcuts: dict[str, str] = {}
        for mid, field in self._module_fields.items():
            val = field.text().strip()
            if val and val.lower() != "none":
                module_shortcuts[mid] = val

        data = {
            "enable_screenshot": self._enable_screenshot.isChecked(),
            "close_to_background": self._close_to_tray.isChecked(),
            "screenshot": self._shot.text().strip(),
            "screenshot_region": self._shot_region.text().strip(),
            "toggle_fullscreen": self._fullscreen.text().strip(),
            "summon_module_id": self._summon.text().strip(),
            "exit_app": self._exit.text().strip(),
            "restart_app": self._restart.text().strip(),
            "home_jump_office": self._home_k.text().strip(),
            "home_jump_image": self._home_i.text().strip(),
            "module_shortcuts": module_shortcuts,
        }
        for mid, legacy in (
            ("quick_notepad", "open_notepad"),
            ("pomodoro", "open_pomodoro"),
            ("ocr_tool", "open_ocr"),
            ("clipboard_history", "open_clipboard"),
        ):
            if mid in module_shortcuts:
                data[legacy] = module_shortcuts[mid]
        save_hotkeys_config(data)

        try:
            from services.platform_experience import get_platform_experience

            get_platform_experience().apply_close_to_tray()
        except Exception:
            pass

        shell = self._page.window()
        if shell is not None:
            if hasattr(shell, "reload_window_hotkeys"):
                shell.reload_window_hotkeys()
            if hasattr(shell, "_wire_platform"):
                try:
                    self._reapply_global_hotkeys(shell)
                    self._page.report_status("热键已保存并重注册")
                    return
                except Exception:
                    pass
        self._page.report_status("热键配置已保存")

    def _reapply_global_hotkeys(self, shell) -> None:
        from services.module_hotkeys import global_module_bindings
        from services.screenshot_service import run_screenshot_hotkey

        hk = get_hotkeys_config()
        bindings = {}
        if hk.get("enable_screenshot", True):
            if hk.get("screenshot"):
                bindings[str(hk["screenshot"])] = lambda: run_screenshot_hotkey(shell, full=False)
            if hk.get("screenshot_region"):
                bindings[str(hk["screenshot_region"])] = lambda: run_screenshot_hotkey(
                    shell, full=True
                )
        for seq, mid in global_module_bindings().items():
            if seq in bindings:
                continue
            if mid == "ocr_tool":
                bindings[seq] = shell._run_ocr_hotkey
            elif mid == "clipboard_history":
                bindings[seq] = shell._open_clipboard_quick
            else:
                bindings[seq] = lambda m=mid: shell._summon_module(m)
        errs = get_hotkey_service().apply(bindings)
        if errs:
            self._page.report_status(f"已保存；部分全局键占用：{errs}")
