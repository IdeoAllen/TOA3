# -*- coding: utf-8 -*-
"""编码智能体 · 环境维护弹窗（小白人话 · 日常入口在本页「更多」）。"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from core.user_messages import show_info, show_warning
from services.harness_credentials import diagnose_llm_access, masked_status, save_api_key
from services.harness_config import load_harness_config, save_harness_config
from services.harness_surface import BROWSER_BETTER_HINT, set_surface_mode, surface_mode
from widgets import (
    CheckBox,
    ComboBox,
    FormSection,
    HintLabel,
    PasswordLineEdit,
    PrimaryButton,
    SecondaryButton,
    SemanticLabel,
)


class HarnessMaintainDialog(BaseDialog):
    """密钥 / 显示方式 / 版本备份 / 出问题了 · 人话动作。路径级排障不进日常面。"""

    dialog_kind = "medium"

    def __init__(
        self,
        parent=None,
        *,
        on_repair: Callable[[], None] | None = None,
        on_restore: Callable[[], None] | None = None,
        on_upgrade: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_backup_system: Callable[[], None] | None = None,
        on_restore_system: Callable[[], None] | None = None,
        on_open_backups: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("环境维护")
        self._on_repair = on_repair
        self._on_restore = on_restore
        self._on_upgrade = on_upgrade
        self._on_restart = on_restart
        self._on_backup_system = on_backup_system
        self._on_restore_system = on_restore_system
        self._on_open_backups = on_open_backups

        root = QVBoxLayout(self)
        root.setSpacing(12)

        root.addWidget(
            HintLabel(
                "日常在本页启停即可。这里改对话密钥、显示方式；"
                "手动升级前请先「备份系统」；坏了再点下面的按钮。"
            )
        )

        # —— 版本信息 ——
        ver = FormSection("运行环境版本")
        try:
            from services.harness_system_backup import list_system_backups, version_info

            info = version_info()
            snaps = list_system_backups()
        except Exception:
            info = {
                "flavor_label": "?",
                "installed_bundle": "?",
                "pinned_bundle": "?",
                "dsh_core": "?",
                "dsh_pinned": "?",
                "needs_repin": False,
                "core_drift": False,
            }
            snaps = []

        lines = (
            f"口味：{info.get('flavor_label')}　"
            f"程序包：本机 {info.get('installed_bundle')} → 钉扎 {info.get('pinned_bundle')}\n"
            f"内核 dsh：本机 {info.get('dsh_core')} → 钉扎 {info.get('dsh_pinned')}"
        )
        kind = "warning" if info.get("needs_repin") else "info"
        self._ver_banner = SemanticLabel(lines, kind=kind)
        self._ver_banner.setWordWrap(True)
        ver.add_widget(self._ver_banner)
        if info.get("core_drift"):
            ver.add_widget(
                HintLabel(
                    "本机内核已偏离运营宝钉扎（常见于在安装目录里手动 npm 升级）。"
                    "请先「备份系统」，再点「更新环境」恢复官方程序包。"
                )
            )
        else:
            ver.add_widget(
                HintLabel(
                    "升级前点「备份系统」；升坏了可「从系统备份恢复」。"
                    f"当前已有 {len(snaps)} 份系统备份（最多保留 3 代）。"
                )
            )

        ver_row = QHBoxLayout()
        btn_backup = PrimaryButton("备份系统")
        btn_backup.setToolTip("升级前点这个：整包快照安装树与会话目录，升坏了能回去")
        btn_backup.clicked.connect(self._click_backup_system)
        ver_row.addWidget(btn_backup)

        btn_upgrade = SecondaryButton("更新环境")
        btn_upgrade.setToolTip("下载并换上钉扎版运行环境；会先自动备份")
        btn_upgrade.clicked.connect(self._click_upgrade)
        ver_row.addWidget(btn_upgrade)

        btn_restore_sys = SecondaryButton("从系统备份恢复")
        btn_restore_sys.setToolTip("用最近一次系统备份覆盖当前安装树")
        btn_restore_sys.setEnabled(bool(snaps))
        btn_restore_sys.clicked.connect(self._click_restore_system)
        ver_row.addWidget(btn_restore_sys)

        btn_open_bak = SecondaryButton("打开备份目录")
        btn_open_bak.clicked.connect(self._click_open_backups)
        ver_row.addWidget(btn_open_bak)
        ver_row.addStretch(1)
        ver.add_layout(ver_row)
        root.addWidget(ver)

        # —— 常用 ——
        daily = FormSection("常用")
        form = QFormLayout()
        cfg = load_harness_config()

        self._api_key = PasswordLineEdit()
        self._api_key.setPlaceholderText("粘贴 DeepSeek 对话密钥（只存本机）")
        form.addRow("对话密钥", self._api_key)
        self._key_status = HintLabel(masked_status())
        form.addRow("当前密钥", self._key_status)

        self._surface = ComboBox()
        self._surface.addItem("在套件里看（默认）", "embed")
        self._surface.addItem(f"提示用浏览器看（{BROWSER_BETTER_HINT}）", "browser")
        self._surface.setCurrentIndex(0 if surface_mode() == "embed" else 1)
        form.addRow("怎么看界面", self._surface)

        self._auto = CheckBox("打开本页时自动启动")
        self._auto.setChecked(bool(cfg.get("auto_start", True)))
        form.addRow("", self._auto)

        self._stop_exit = CheckBox("关掉运营宝时结束后台服务")
        self._stop_exit.setChecked(bool(cfg.get("stop_on_app_exit", False)))
        form.addRow("", self._stop_exit)

        daily.add_layout(form)
        save_row = QHBoxLayout()
        btn_save = PrimaryButton("保存常用设置")
        btn_save.clicked.connect(self._save_daily)
        save_row.addWidget(btn_save)
        save_row.addStretch(1)
        daily.add_layout(save_row)
        root.addWidget(daily)

        # —— 出问题了 ——
        fix = FormSection("出问题了")
        fix.add_widget(
            HintLabel(
                "起不来、页面空白、插件搞挂：先「修一下」；"
                "还不行再「回到上次能用的配置」或上面的「从系统备份恢复」。"
            )
        )
        fix_row = QHBoxLayout()
        btn_repair = PrimaryButton("修一下")
        btn_repair.setToolTip("自动检查并整理环境，然后重新启动")
        btn_repair.clicked.connect(self._click_repair)
        fix_row.addWidget(btn_repair)

        btn_restore = SecondaryButton("回到上次能用的配置")
        btn_restore.setToolTip("只恢复 web 插件配置快照（不含整包程序）")
        btn_restore.clicked.connect(self._click_restore)
        fix_row.addWidget(btn_restore)

        btn_restart = SecondaryButton("重新启动")
        btn_restart.setToolTip("关掉再开，不改配置")
        btn_restart.clicked.connect(self._click_restart)
        fix_row.addWidget(btn_restart)
        fix.add_layout(fix_row)

        diag_row = QHBoxLayout()
        btn_diag = SecondaryButton("导出诊断包")
        btn_diag.setToolTip("打包脱敏状态与启动记录，发给客服即可（不含密钥）")
        btn_diag.clicked.connect(self._click_export_diag)
        diag_row.addWidget(btn_diag)
        diag_row.addStretch(1)
        fix.add_layout(diag_row)
        root.addWidget(fix)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = SecondaryButton("关闭")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        root.addLayout(close_row)

    def _save_daily(self) -> None:
        key = self._api_key.text().strip()
        if key:
            ok, msg = save_api_key(key)
            if not ok:
                show_warning(self, msg)
                return
            self._api_key.clear()
            self._key_status.setText(masked_status())

        save_harness_config(
            {
                "auto_start": self._auto.isChecked(),
                "stop_on_app_exit": self._stop_exit.isChecked(),
            }
        )
        set_surface_mode(str(self._surface.currentData() or "embed"))

        key_ok, key_msg = diagnose_llm_access()
        tip = "已保存。"
        if key:
            tip += "若对话仍接不上，请点「重新启动」。"
        elif not key_ok:
            tip += f"\n{key_msg}"
        show_info(self, tip)

    def _click_repair(self) -> None:
        self.accept()
        if self._on_repair:
            self._on_repair()

    def _click_restore(self) -> None:
        self.accept()
        if self._on_restore:
            self._on_restore()

    def _click_upgrade(self) -> None:
        self.accept()
        if self._on_upgrade:
            self._on_upgrade()

    def _click_restart(self) -> None:
        self.accept()
        if self._on_restart:
            self._on_restart()

    def _click_backup_system(self) -> None:
        self.accept()
        if self._on_backup_system:
            self._on_backup_system()

    def _click_restore_system(self) -> None:
        self.accept()
        if self._on_restore_system:
            self._on_restore_system()

    def _click_open_backups(self) -> None:
        if self._on_open_backups:
            self._on_open_backups()

    def _click_export_diag(self) -> None:
        from core.user_messages import show_saved
        from services.harness_diagnose import export_diagnostic_pack

        ok, msg, path = export_diagnostic_pack()
        if not ok or path is None:
            show_warning(self, msg or "导出失败")
            return
        show_saved(self, msg, str(path))
