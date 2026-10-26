# -*- coding: utf-8 -*-
"""发现新版本：下载安装 / 打开下载页 / 复制 IT 说明。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTextEdit, QVBoxLayout

from app.dialog_chrome import add_dialog_hero, apply_dialog_root
from app.setup_download_dialog import present_setup_download
from core.base_dialog import BaseDialog
from core.user_messages import show_info
from services.update_check import UpdateCheckResult, open_download_page
from widgets import DialogButtonRow, FormSection, HintLabel


def _upgrade_script_candidates() -> list[Path]:
    out: list[Path] = []
    try:
        import sys

        if getattr(sys, "frozen", False):
            out.append(Path(sys.executable).resolve().parent / "TOA3-upgrade.bat")
    except Exception:
        pass
    local = Path.home() / "AppData" / "Local" / "Programs" / "TOA3" / "TOA3-upgrade.bat"
    out.append(local)
    try:
        from services.config_service import project_root

        root = project_root()
        out.append(root / "packaging" / "dist" / "TOA3-upgrade.bat")
        for p in (root / "packaging" / "dist").glob("TOA3-v*-win64/TOA3-upgrade.bat"):
            out.append(p)
    except Exception:
        pass
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def find_upgrade_script() -> Path | None:
    for p in _upgrade_script_candidates():
        if p.is_file():
            return p
    return None


def it_upgrade_clipboard_text(result: UpdateCheckResult) -> str:
    ver = result.latest_version or ""
    page = result.download_page or "https://toa-service.yczh.tech/download/"
    exe = result.download_url or ""
    script = find_upgrade_script()
    lines = [
        f"TOA3 升级说明 · 目标版本 v{ver}" if ver else "TOA3 升级说明",
        f"1. 下载页：{page}",
    ]
    if exe:
        lines.append(f"2. 安装包直链：{exe}")
    lines.append("3. 关闭正在运行的 TOA3 后运行安装包（同 AppId 覆盖升级，保留用户数据）。")
    if script:
        lines.append(f"4. IT 脚本（本机）：{script}")
        lines.append("   静默示例：设置环境变量 TOA_LICENSE=授权码 后执行 TOA3-upgrade.bat")
    else:
        lines.append("4. IT：从安装包同目录使用 TOA3-upgrade.bat（打包产物内）。")
    return "\n".join(lines)


class UpdateAvailableDialog(BaseDialog):
    """有可用更新时的操作对话框。"""

    dialog_kind = "medium"

    def __init__(self, parent, result: UpdateCheckResult) -> None:
        super().__init__(parent)
        self._result = result
        latest = result.latest_version or "新版本"
        self.setWindowTitle("有可用更新")

        root = QVBoxLayout(self)
        apply_dialog_root(root)
        add_dialog_hero(
            root,
            pixmap=None,
            title=f"发现 v{latest}",
            subtitle=f"当前 {result.current_version}",
        )

        if result.below_min_version and result.min_version:
            root.addWidget(
                HintLabel(
                    f"当前版本低于最低可升级要求 v{result.min_version}，请尽快升级。"
                )
            )

        notes = (result.release_notes or "").strip() or "暂无更新说明。"
        notes_sec = FormSection("更新说明")
        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(notes)
        body.setMinimumHeight(120)
        notes_sec.add_widget(body)
        root.addWidget(notes_sec)

        root.addWidget(
            HintLabel("可直接下载安装包并运行；也可打开官方下载页。安装时会关闭本应用。")
        )

        actions = DialogButtonRow()
        actions.add_secondary("复制升级说明", self._copy_it)
        actions.add_secondary("打开下载页", self._open_page)
        if result.download_url:
            actions.add_primary("下载并安装", self._start_download)
        else:
            actions.add_primary("打开下载页", self._open_page)
        root.addWidget(actions)

    def _start_download(self) -> None:
        url = (self._result.download_url or "").strip()
        if not url:
            self._open_page()
            return
        self.accept()
        present_setup_download(
            self.parentWidget() or self,
            download_url=url,
            version=self._result.latest_version,
        )

    def _open_page(self) -> None:
        open_download_page(self._result)
        self.accept()

    def _copy_it(self) -> None:
        text = it_upgrade_clipboard_text(self._result)
        QGuiApplication.clipboard().setText(text)
        show_info(self, "升级说明已复制到剪贴板。", title="已复制")


def present_update_available(parent, result: UpdateCheckResult) -> None:
    """有更新时弹出专用对话框；无更新则不应调用。"""
    if not result.has_update:
        return
    dlg = UpdateAvailableDialog(parent, result)
    dlg.exec()
