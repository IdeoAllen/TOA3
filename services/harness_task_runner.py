# -*- coding: utf-8 -*-
"""Harness 阻塞任务：Sidecar 启停/探测放后台线程，避免卡死 UI。"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Qt


class HarnessTaskWorker(QObject):
    finished = Signal(object)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(("ok", self._fn()))
        except Exception as exc:
            self.finished.emit(("err", exc))


class HarnessTaskRunner(QObject):
    """在 QThread 中执行 fn()；finished(ok, result|exc) 回到主线程。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: HarnessTaskWorker | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def run(self, fn: Callable[[], Any], *, on_done: Callable[[bool, Any], None]) -> bool:
        if self.is_running():
            return False

        self._thread = QThread(self)
        self._worker = HarnessTaskWorker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        def _finished(payload: object) -> None:
            kind = "err"
            value: Any = None
            if isinstance(payload, tuple) and len(payload) == 2:
                kind, value = payload
            try:
                on_done(kind == "ok", value)
            finally:
                if self._thread is not None:
                    self._thread.quit()

        self._worker.finished.connect(_finished, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()
        return True

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
