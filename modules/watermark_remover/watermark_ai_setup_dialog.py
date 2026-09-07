# -*- coding: utf-8 -*-
"""去水印 · AI 增强两步安装引导（小白向 · ≤2 步）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from core.user_messages import show_success, show_warning
from widgets import DialogButtonRow, HintLabel, PrimaryButton, ProgressBar, SecondaryButton


class _LamaDownloadWorker(QObject):
    progress = Signal(str, int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def run(self) -> None:
        def _prog(msg: str, cur: int = 0, total: int = 0) -> None:
            self.progress.emit(msg, cur, total)

        try:
            from services.local_inpaint_runtime import download_weights, install_status

            st = install_status()
            missing = list(st.get("missing") or [])
            if "PyTorch" in missing:
                self.failed.emit(
                    "本机还缺运行环境（PyTorch）。请点「完整一键安装」一次装齐，或到系统设置 → 安装本机模型。"
                )
                return
            ok, msg = download_weights(progress=_prog)
            if ok:
                self.finished_ok.emit(msg)
            else:
                self.failed.emit(msg)
        except Exception as exc:
            self.failed.emit(str(exc))


class WatermarkAiSetupDialog(BaseDialog):
    """探索 AI 增强：① 安装模型 → ② 勾选「AI 增强」。"""

    dialog_kind = "medium"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("安装 AI 增强（两步）")
        self.installed = False
        self._thread: QThread | None = None
        self._worker: _LamaDownloadWorker | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            HintLabel(
                "默认本地修复已够用。若电脑有条件、想效果更好，按下面两步探索即可——"
                "不用改配置文件。"
            )
        )
        lay.addWidget(
            HintLabel(
                "① 点「下载去水印模型」装好（只装这一件）\n"
                "② 关闭本窗后，勾选页面上的「AI 增强」"
            )
        )
        self._status = HintLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        self._progress = ProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        lay.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_dl = PrimaryButton("① 下载去水印模型")
        self._btn_dl.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_dl)
        btn_full = SecondaryButton("完整一键安装…")
        btn_full.setToolTip("同时装本机生图运行环境（缺 PyTorch 时用这个）")
        btn_full.clicked.connect(self._open_full_setup)
        btn_row.addWidget(btn_full)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        buttons = DialogButtonRow()
        buttons.add_primary("完成", self.accept)
        lay.addWidget(buttons)

        self._refresh_status()

    def _refresh_status(self) -> None:
        from services.local_inpaint_runtime import install_status

        st = install_status()
        if st.get("ready"):
            self.installed = True
            self._status.setText(
                f"① 已完成 · {st.get('user_hint') or '模型就绪'}。请关窗后勾选「AI 增强」。"
            )
            self._btn_dl.setEnabled(False)
        else:
            self.installed = False
            miss = "、".join(st.get("missing") or []) or "待安装"
            self._status.setText(f"① 待完成 · 缺 {miss}。点上方主按钮即可。")

    def _set_busy(self, busy: bool) -> None:
        self._btn_dl.setEnabled(not busy)
        self._progress.setVisible(busy)
        if busy:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)

    def _start_download(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在下载，请稍候。")
            return
        self._set_busy(True)
        self._thread = QThread(self)
        self._worker = _LamaDownloadWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _on_progress(self, msg: str, cur: int, total: int) -> None:
        self._status.setText(msg)
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(min(cur, total))
            pct = int(cur * 100 / total) if total else 0
            self._progress.setFormat(f"{pct}%")
        else:
            self._progress.setRange(0, 0)

    def _on_ok(self, msg: str) -> None:
        self._set_busy(False)
        self._refresh_status()
        show_success(self, f"{msg}\n下一步：关闭本窗，勾选「AI 增强」。")

    def _on_fail(self, msg: str) -> None:
        self._set_busy(False)
        self._refresh_status()
        show_warning(self, msg)

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _open_full_setup(self) -> None:
        from modules.system_settings.local_image_setup_dialog import LocalImageSetupDialog

        dlg = LocalImageSetupDialog(self)
        dlg.exec()
        self._refresh_status()
