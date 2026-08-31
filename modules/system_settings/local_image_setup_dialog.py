# -*- coding: utf-8 -*-
"""本机生图 · 一键安装对话框（小白向）。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from core.base_dialog import BaseDialog
from core.user_messages import show_success, show_warning
from services.local_models_setup import combined_status_summary, install_all
from services.local_image_setup import auto_find_and_migrate, status_summary
from services.local_image_runtime import import_offline_pack, install_status
from services.model_catalog import set_active_profile_id
from widgets import (
    ComboBox,
    DialogButtonRow,
    HintLabel,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
)


class _SetupWorker(QObject):
    progress = Signal(str, int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, mode: str, bundle_id: str, runtime_profile: str) -> None:
        super().__init__()
        self._mode = mode
        self._bundle_id = bundle_id
        self._runtime_profile = runtime_profile

    def run(self) -> None:
        def _prog(msg: str, cur: int = 0, total: int = 0) -> None:
            self.progress.emit(msg, cur, total)

        try:
            if self._mode == "scan":
                ok, msg = auto_find_and_migrate(progress=_prog)
            else:
                ok, msg = install_all(
                    self._bundle_id,
                    runtime_profile=self._runtime_profile,
                    progress=_prog,
                )
            if ok:
                self.finished_ok.emit(msg)
            else:
                self.failed.emit(msg)
        except Exception as exc:
            self.failed.emit(str(exc))


class LocalImageSetupDialog(BaseDialog):
    """安装本机生图：一键下载 / 自动查找 / 导入离线包。"""

    dialog_kind = "large"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("安装本机模型")
        self._thread: QThread | None = None
        self._worker: _SetupWorker | None = None
        self.ready = False

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            HintLabel(
                "一键装好「本机生图 + 去水印 LaMa」，不用自己找文件。"
                "生图包较大，请保持网络并耐心等待。"
            )
        )

        self._status = HintLabel(combined_status_summary())
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        tier_row = QHBoxLayout()
        tier_row.addWidget(HintLabel("显存档位"))
        self._bundle = ComboBox()
        self._bundle.addItem("均衡（6–8GB · 推荐）", "balanced")
        self._bundle.addItem("低配（约 4GB）", "low")
        self._bundle.setMinimumWidth(220)
        tier_row.addWidget(self._bundle, 1)
        lay.addLayout(tier_row)

        rt_row = QHBoxLayout()
        rt_row.addWidget(HintLabel("运行方式"))
        self._runtime = ComboBox()
        self._runtime.addItem("NVIDIA 显卡（推荐）", "win_cuda12")
        self._runtime.addItem("无 NVIDIA · CPU（较慢）", "win_cpu")
        self._runtime.addItem("Vulkan", "win_vulkan")
        self._runtime.setMinimumWidth(220)
        rt_row.addWidget(self._runtime, 1)
        lay.addLayout(rt_row)

        self._progress = ProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        lay.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_download = PrimaryButton("一键下载并安装")
        self._btn_download.clicked.connect(lambda: self._start("download"))
        btn_row.addWidget(self._btn_download)
        btn_scan = SecondaryButton("从本机自动查找")
        btn_scan.clicked.connect(lambda: self._start("scan"))
        btn_row.addWidget(btn_scan)
        btn_import = SecondaryButton("导入离线包…")
        btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(btn_import)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        buttons = DialogButtonRow()
        buttons.add_primary("关闭", self.accept)
        lay.addWidget(buttons)

        from services.local_inpaint_runtime import install_status as lama_st

        st = install_status()
        self.ready = bool(st.get("ready")) and bool(lama_st().get("ready"))

    def _set_busy(self, busy: bool) -> None:
        self._btn_download.setEnabled(not busy)
        self._progress.setVisible(busy)
        if busy:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)

    def _refresh_status(self) -> None:
        from services.local_inpaint_runtime import install_status as lama_st

        self._status.setText(combined_status_summary())
        st = install_status()
        self.ready = bool(st.get("ready")) and bool(lama_st().get("ready"))

    def _start(self, mode: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            show_warning(self, "正在安装，请稍候。")
            return
        bundle_id = str(self._bundle.currentData() or "balanced")
        runtime_profile = str(self._runtime.currentData() or "win_cuda12")
        self._set_busy(True)
        self._thread = QThread(self)
        self._worker = _SetupWorker(mode, bundle_id, runtime_profile)
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
        try:
            set_active_profile_id("image_gen", "local_z_image_simple")
        except Exception:
            pass
        self._refresh_status()
        show_success(self, msg)

    def _on_fail(self, msg: str) -> None:
        self._set_busy(False)
        self._refresh_status()
        show_warning(self, msg or "安装未完成，请重试或换网络。")

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _on_import(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择离线包文件夹")
        if not path:
            return
        ok, msg = import_offline_pack(path)
        self._refresh_status()
        if ok:
            try:
                set_active_profile_id("image_gen", "local_z_image_simple")
            except Exception:
                pass
            self.ready = True
            show_success(self, msg)
        else:
            show_warning(self, msg)
