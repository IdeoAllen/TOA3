# -*- coding: utf-8 -*-
"""下载当前/指定版 Setup：进度对话框（不依赖「有更新」）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout

from app.dialog_chrome import add_dialog_hero, apply_dialog_root
from core.base_dialog import BaseDialog
from core.user_messages import ask_confirm, show_error, show_saved
from services.setup_download import (
    SetupDownloadResult,
    get_setup_download_hub,
    launch_setup_installer,
    setup_download_dir,
)
from widgets import DialogButtonRow, HintLabel, ProgressBar


class SetupDownloadDialog(BaseDialog):
    """异步下载安装包并可选立即安装。"""

    dialog_kind = "medium"

    def __init__(
        self,
        parent,
        *,
        download_url: str,
        version: str | None = None,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent)
        self._url = (download_url or "").strip()
        self._version = (version or "").strip() or None
        self._downloaded: Path | None = None
        self._closing = False
        title_ver = f"v{self._version}" if self._version else "安装包"
        self.setWindowTitle("下载安装包")

        root = QVBoxLayout(self)
        apply_dialog_root(root)
        add_dialog_hero(
            root,
            pixmap=None,
            title=f"下载 {title_ver}",
            subtitle="支持断点续传；取消后再次下载可接着传",
        )
        self._status = HintLabel("准备下载…")
        root.addWidget(self._status)
        self._progress = ProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        actions = DialogButtonRow()
        self._btn_folder = actions.add_secondary("打开目录", self._open_folder)
        self._btn_retry = actions.add_secondary("重试", self._start)
        self._btn_retry.setVisible(False)
        self._btn_close = actions.add_secondary("取消", self._on_cancel)
        self._btn_run = actions.add_primary("运行安装程序", self._run_now)
        self._btn_run.setEnabled(False)
        self._btn_run.setVisible(False)
        root.addWidget(actions)

        hub = get_setup_download_hub()
        hub.progress.connect(self._on_progress, Qt.ConnectionType.UniqueConnection)
        hub.finished.connect(self._on_finished, Qt.ConnectionType.UniqueConnection)
        hub.busy_changed.connect(self._on_busy, Qt.ConnectionType.UniqueConnection)

        if auto_start:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._start)

    def _start(self) -> None:
        if not self._url:
            show_error(self, "没有可用的安装包地址。", title="下载")
            return
        hub = get_setup_download_hub()
        if hub.is_busy():
            self._status.setText("已有下载任务进行中…")
            return
        self._closing = False
        self._btn_retry.setVisible(False)
        self._btn_run.setVisible(False)
        self._status.setText("正在连接服务器…")
        self._progress.setRange(0, 0)
        if not hub.start(self._url, version=self._version):
            show_error(self, "无法开始下载。", title="下载")
            self._btn_retry.setVisible(True)

    def _open_folder(self) -> None:
        from services.os_open import open_in_file_manager

        path = self._downloaded or setup_download_dir(create=True)
        open_in_file_manager(str(path), select=bool(self._downloaded and Path(self._downloaded).is_file()))

    def _on_cancel(self) -> None:
        hub = get_setup_download_hub()
        if hub.is_busy():
            hub.cancel()
            self._status.setText("正在取消（已下部分会保留，可续传）…")
            self._btn_close.setEnabled(False)
            return
        self.reject()

    def reject(self) -> None:
        self._closing = True
        hub = get_setup_download_hub()
        if hub.is_busy():
            hub.cancel()
        super().reject()

    def _on_busy(self, busy: bool) -> None:
        if busy:
            self._btn_close.setText("取消")
            self._btn_close.setEnabled(True)
            self._btn_retry.setVisible(False)
        else:
            self._btn_close.setText("关闭")
            self._btn_close.setEnabled(True)

    def _on_progress(self, msg: str, done: int, total: int) -> None:
        if self._closing or not self.isVisible():
            return
        self._status.setText(msg)
        if total > 0:
            self._progress.setRange(0, 1000)
            self._progress.setValue(max(0, min(1000, int(done * 1000 / total))))
        else:
            self._progress.setRange(0, 0)

    def _on_finished(self, result: object) -> None:
        if self._closing or not self.isVisible():
            return
        if not isinstance(result, SetupDownloadResult):
            show_error(self, "下载失败：返回无效", title="下载")
            self._btn_retry.setVisible(True)
            return
        if not result.ok or result.path is None:
            err = (result.error or "未知错误").strip()
            if "取消" in err:
                self._status.setText("已取消 · 可点「重试」续传")
                self._btn_retry.setVisible(True)
                self._btn_close.setText("关闭")
                self._btn_close.setEnabled(True)
                if result.bytes_done > 0:
                    self._progress.setRange(0, 1000)
                return
            show_error(self, f"下载失败：{err}\n可点「重试」继续（支持续传）。", title="下载")
            self._status.setText("下载失败 · 可重试续传")
            self._btn_retry.setVisible(True)
            return
        self._downloaded = result.path
        self._progress.setRange(0, 1000)
        self._progress.setValue(1000)
        self._status.setText(f"已保存：{result.path.name}")
        show_saved(self, f"安装包已下载：{result.path.name}", result.path)
        if ask_confirm(
            self,
            "是否立即运行安装程序？\n安装过程会关闭正在运行的 TOA3，完成后请重新打开。",
            title="运行安装程序",
        ):
            try:
                launch_setup_installer(result.path)
            except Exception as exc:
                show_error(self, f"无法启动安装程序：{exc}", title="安装")
                self._btn_run.setVisible(True)
                self._btn_run.setEnabled(True)
                return
            self.accept()
            self._quit_app()
        else:
            self._btn_run.setVisible(True)
            self._btn_run.setEnabled(True)

    def _run_now(self) -> None:
        if self._downloaded is None:
            return
        try:
            launch_setup_installer(self._downloaded)
        except Exception as exc:
            show_error(self, f"无法启动安装程序：{exc}", title="安装")
            return
        self.accept()
        self._quit_app()

    def _quit_app(self) -> None:
        try:
            w = self.parentWidget()
            while w is not None:
                if hasattr(w, "_quit_app"):
                    w._quit_app()
                    return
                w = w.parentWidget()
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            pass


def present_setup_download(
    parent,
    *,
    download_url: str,
    version: str | None = None,
) -> None:
    url = (download_url or "").strip()
    if not url:
        show_error(parent, "没有可用的安装包地址。", title="下载")
        return
    dlg = SetupDownloadDialog(parent, download_url=url, version=version, auto_start=True)
    dlg.exec()
