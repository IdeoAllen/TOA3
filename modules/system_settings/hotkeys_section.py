# -*- coding: utf-8 -*-
"""系统设置 · 热键（分层：全局 / 应用 / 页内；模块按一级菜单分组）。"""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout

from core.base_page import BasePage
from services.config_service import get_hotkeys_config, save_hotkeys_config
from services.hotkey_service import get_hotkey_service
from services.menu_registry import DOMAIN_TAB_LABELS
from services.module_hotkeys import get_configured_module_shortcuts, list_shortcut_modules_grouped
from services.screenshot_service import run_screenshot_hotkey
from widgets import CheckBox, FormSection, HintLabel, LineEdit, PrimaryButton, ScrollPage, SecondaryButton


class HotkeysSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("热键与截图")
        self._page = parent
        hk = get_hotkeys_config()
        self._module_fields: dict[str, LineEdit] = {}

        self.add_widget(
            HintLabel(
                "分层约定（详见 docs/standards/快捷键规范.md）：\n"
                "· 全局：托盘隐藏也可用，须带 Alt/Ctrl（如 Alt+A 截图）\n"
                "· 应用：主窗口前台（F11 沉浸 · Ctrl+Q 退出 · Ctrl+K 命令面板）\n"
                "· 页内：←/→ 子模块 · ↑/↓ 功能模块 · K/I 首页跳转\n"
                "· 模块：按顶栏子模块分组，顺序与侧栏菜单一致"
            )
        )

        app_sec = FormSection("全局 · 应用 · 页内")
        form = QFormLayout()
        self._enable_screenshot = CheckBox("启用截图全局热键")
        self._enable_screenshot.setChecked(bool(hk.get("enable_screenshot", True)))
        form.addRow("截图", self._enable_screenshot)

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

        self.add_widget(HintLabel("模块快捷键：按顶栏子模块分组，组内顺序与侧栏一致（留空=不绑定）"))
        mod_scroll = ScrollPage(padded=False)
        mod_scroll.setMaximumHeight(460)
        configured = get_configured_module_shortcuts()
        for gid, glab, rows in list_shortcut_modules_grouped():
            tab = DOMAIN_TAB_LABELS.get(gid, glab)
            title = glab if tab == glab else f"{tab} · {glab}"
            sec = FormSection(title)
            mod_form = QFormLayout()
            for mid, name, effective in rows:
                field = LineEdit(configured.get(mid, ""))
                field.setPlaceholderText(effective or "留空或 none")
                self._module_fields[mid] = field
                mod_form.addRow(name, field)
            sec.add_layout(mod_form)
            mod_scroll.add_widget(sec)
        self.add_widget(mod_scroll)

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

    def _save(self) -> None:
        module_shortcuts: dict[str, str] = {}
        for mid, field in self._module_fields.items():
            val = field.text().strip()
            if val and val.lower() != "none":
                module_shortcuts[mid] = val

        data = {
            "enable_screenshot": self._enable_screenshot.isChecked(),
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
