# -*- coding: utf-8 -*-
"""系统设置 · 热键（分层：全局 / 应用 / 页内；模块仅常用 + 按需添加）。"""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout

from core.base_page import BasePage
from core.user_messages import show_info, show_warning
from services.config_service import get_hotkeys_config, save_hotkeys_config
from services.menu_registry import is_migrated
from services.module_hotkeys import (
    _GLOBAL_EXCLUDE_MODULES,
    get_configured_module_shortcuts,
    get_module_shortcut,
    list_hotkey_editor_modules,
    list_hotkey_picker_modules,
    normalize_module_id,
)
from services.screenshot_service import run_screenshot_hotkey
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    HotkeyCaptureEdit,
    PrimaryButton,
    SecondaryButton,
)


def _resolve_summon_module_id(raw: object) -> str:
    return normalize_module_id(raw)


class HotkeysSection(FormSection):
    def __init__(self, parent: BasePage) -> None:
        super().__init__("热键与截图")
        self._page = parent
        hk = get_hotkeys_config()
        self._module_fields: dict[str, HotkeyCaptureEdit] = {}
        self._mod_form: QFormLayout | None = None

        self.add_widget(
            HintLabel(
                "录制方式：点输入框 → 按下快捷键（自动填入）→ 点「保存热键」。"
                "全局键须带 Alt/Ctrl；双击 Ctrl 可唤起主窗，并可选跳进指定模块。"
            )
        )

        app_sec = FormSection("全局 · 应用 · 页内")
        form = QFormLayout()
        self._enable_toggle = CheckBox("启用双击 Ctrl 唤起主窗")
        self._enable_toggle.setChecked(bool(hk.get("enable_global_toggle", True)))
        form.addRow("唤起", self._enable_toggle)

        self._toggle_window = HotkeyCaptureEdit("")
        self._toggle_window.setPlaceholderText("可选，如 Alt+`（与双击 Ctrl 并存）")
        form.addRow("备用唤起键", self._toggle_window)
        alt_tw = str(hk.get("toggle_window") or "").strip()
        if alt_tw and alt_tw.lower() != "none" and not self._is_alt_toggle_spec(alt_tw):
            self._toggle_window.setText(alt_tw)

        self._summon = ComboBox()
        self._summon.setMinimumWidth(260)
        self._summon.addItem("无（仅显示主窗）", None)
        summon_id = _resolve_summon_module_id(hk.get("summon_module_id"))
        pick_index = 0
        for idx, (mid, name) in enumerate(list_hotkey_picker_modules(), start=1):
            self._summon.addItem(f"{name}（{mid}）", mid)
            if mid == summon_id:
                pick_index = idx
        self._summon.setCurrentIndex(pick_index)
        form.addRow("唤起后打开", self._summon)

        self._enable_screenshot = CheckBox("启用截图全局热键")
        self._enable_screenshot.setChecked(bool(hk.get("enable_screenshot", True)))
        form.addRow("截图", self._enable_screenshot)

        self._close_to_tray = CheckBox("关闭窗口时最小化到系统托盘")
        self._close_to_tray.setChecked(bool(hk.get("close_to_background", True)))
        form.addRow("托盘", self._close_to_tray)

        self._enable_drop = CheckBox("拖入文件/文件夹时打开桌面浏览")
        self._enable_drop.setChecked(bool(hk.get("enable_drop_open_desktop", True)))
        form.addRow("拖入", self._enable_drop)

        self._enable_immersive = CheckBox("启用沉浸全屏热键（默认 F11，仅应用前台）")
        self._enable_immersive.setChecked(bool(hk.get("enable_immersive_hotkey", True)))
        form.addRow("全屏", self._enable_immersive)

        self._shot = HotkeyCaptureEdit(str(hk.get("screenshot") or "Alt+A"))
        self._shot_region = HotkeyCaptureEdit(str(hk.get("screenshot_region") or "Alt+Shift+A"))
        self._fullscreen = HotkeyCaptureEdit(str(hk.get("toggle_fullscreen") or "F11"))
        self._exit = HotkeyCaptureEdit(str(hk.get("exit_app") or "Ctrl+Q"), require_modifier=True)
        self._restart = HotkeyCaptureEdit(str(hk.get("restart_app") or "Ctrl+Shift+R"))
        self._home_k = HotkeyCaptureEdit(
            str(hk.get("home_jump_office") or "K"),
            allow_page_keys=True,
            require_modifier=False,
        )
        self._home_i = HotkeyCaptureEdit(
            str(hk.get("home_jump_image") or "I"),
            allow_page_keys=True,
            require_modifier=False,
        )

        form.addRow("区域截图", self._shot)
        form.addRow("全屏截图", self._shot_region)
        form.addRow("沉浸全屏键", self._fullscreen)
        form.addRow("完全退出", self._exit)
        form.addRow("重启应用", self._restart)
        form.addRow("首页跳办公", self._home_k)
        form.addRow("首页跳图片", self._home_i)
        app_sec.add_layout(form)
        self.add_widget(app_sec)

        mod_sec = FormSection("常用模块唤起")
        mod_sec.add_widget(
            HintLabel("下方为各模块全局快捷键；留空表示不绑定。保存后托盘隐藏时也可唤起。")
        )
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
        self._new_seq = HotkeyCaptureEdit()
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

    @staticmethod
    def _is_alt_toggle_spec(spec: str) -> bool:
        from services.double_ctrl_summon import is_double_ctrl_spec

        return is_double_ctrl_spec(spec)

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
        initial: str = configured
        field = HotkeyCaptureEdit(initial)
        hint = effective or "留空表示不绑定"
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
            show_info(self._page, "该模块已在列表中，直接点右侧输入框录制即可。")
            return
        name = self._module_picker.currentText()
        seq = self._new_seq.text().strip()
        self._add_module_row(self._mod_form, mid, name, seq, get_module_shortcut(mid))
        idx = self._module_picker.currentIndex()
        self._module_picker.removeItem(idx)
        self._new_seq.clear()
        self._page.report_status(f"已添加：{name}")

    def _save(self) -> None:
        summon_id = normalize_module_id(self._summon.currentData())
        if summon_id and not is_migrated(summon_id):
            show_warning(
                self._page,
                f"「唤起后打开」模块无效：{summon_id}\n请从下拉列表选择，勿手输 ID。",
            )
            return

        module_shortcuts: dict[str, str] = {}
        for mid, field in self._module_fields.items():
            val = field.text().strip()
            if val and val.lower() != "none":
                module_shortcuts[mid] = val

        toggle_alt = self._toggle_window.text().strip()
        if self._enable_toggle.isChecked():
            toggle_saved = toggle_alt or "Double+Ctrl"
        else:
            toggle_saved = toggle_alt or "none"
        data = {
            "enable_global_toggle": self._enable_toggle.isChecked(),
            "toggle_window": toggle_saved,
            "enable_screenshot": self._enable_screenshot.isChecked(),
            "close_to_background": self._close_to_tray.isChecked(),
            "enable_drop_open_desktop": self._enable_drop.isChecked(),
            "enable_immersive_hotkey": self._enable_immersive.isChecked(),
            "screenshot": self._shot.text().strip(),
            "screenshot_region": self._shot_region.text().strip(),
            "toggle_fullscreen": self._fullscreen.text().strip(),
            "summon_module_id": summon_id,
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
            get_platform_experience()._rebuild_tray_menu()
        except Exception:
            pass

        shell = self._page.window()
        if shell is not None and hasattr(shell, "reload_window_hotkeys"):
            try:
                errs = shell.reload_window_hotkeys()
                if errs:
                    self._page.report_status(
                        f"已保存；部分全局键被占用：{', '.join(sorted(errs.keys()))}"
                    )
                    return
                from services.edition_isolation import should_register_global_hotkeys

                ok, reason = should_register_global_hotkeys()
                if not ok:
                    self._page.report_status(f"已保存；{reason}")
                    return
                tip = "热键已保存并重注册"
                if summon_id:
                    name = self._summon.currentText()
                    tip += f"；双击 Ctrl 将打开「{name.split('（', 1)[0]}」"
                self._page.report_status(tip)
                return
            except Exception:
                pass
        self._page.report_status("热键配置已保存")
