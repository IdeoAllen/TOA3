# -*- coding: utf-8 -*-
"""媒体工坊 · 生成任务队列（ComfyUI 式排队执行）。"""
from __future__ import annotations

import re
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

ProgressFn = Callable[[str], None]
CancelFn = Callable[[], bool]


def _parse_progress_pct(message: str) -> int | None:
    m = re.search(r"(\d+)\s*%", message or "")
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


@dataclass
class MediaGenSpec:
    kind: str
    prompt: str
    profile_id: str
    image_paths: list[str]
    width: int
    height: int
    image_size: str
    ratio: str
    resolution: str
    duration: int
    generate_audio: bool = False
    web_search: bool = False
    image_quality: str = ""
    image_n: int = 1
    label: str = ""


@dataclass
class MediaGenTask:
    spec: MediaGenSpec
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "pending"  # pending | running | completed | failed | cancelled
    progress: int = 0
    indeterminate: bool = True
    message: str = "等待中…"
    result_path: str = ""
    error: str = ""


class _GenWorker(QObject):
    progress = Signal(str, int, bool)  # message, percent(-1 indeterminate), indeterminate flag
    finished_ok = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, spec: MediaGenSpec, parent=None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancel(self) -> None:
        if self._cancelled:
            raise RuntimeError("已取消生成。")

    def run(self) -> None:
        from services.integrations import get_client

        try:
            self._check_cancel()
            self.progress.emit("正在提交…", -1, True)
            spec = self._spec
            if spec.kind == "video":
                client = get_client("video_gen")
                path = client.generate(
                    spec.prompt,
                    profile_id=spec.profile_id,
                    image_paths=spec.image_paths or None,
                    ratio=spec.ratio,
                    resolution=spec.resolution,
                    duration=spec.duration,
                    generate_audio=spec.generate_audio,
                    web_search=spec.web_search,
                    progress=self._on_client_progress,
                    cancel_check=lambda: self._cancelled,
                )
            else:
                client = get_client("image_gen")
                self.progress.emit("正在生成图片…", -1, True)
                patch: dict = {}
                if spec.image_size:
                    patch["size"] = spec.image_size
                    patch["resolution"] = spec.image_size
                if spec.image_quality:
                    patch["quality"] = spec.image_quality
                if spec.image_n > 1:
                    patch["n"] = int(spec.image_n)
                if patch:
                    try:
                        from services.model_catalog import save_user_profile_patch

                        save_user_profile_patch("image_gen", spec.profile_id, patch)
                    except Exception:
                        pass
                path = client.generate(
                    spec.prompt,
                    width=spec.width,
                    height=spec.height,
                    profile_id=spec.profile_id,
                    image_paths=spec.image_paths or None,
                )
            self._check_cancel()
            self.progress.emit("完成", 100, False)
            self.finished_ok.emit(str(path))
        except Exception as exc:
            if self._cancelled or "已取消" in str(exc):
                self.cancelled.emit()
                return
            self.failed.emit(str(getattr(exc, "user_message", None) or exc))

    def _on_client_progress(self, msg: str) -> None:
        if self._cancelled:
            return
        pct = _parse_progress_pct(msg)
        if pct is not None:
            self.progress.emit(msg, pct, False)
        else:
            self.progress.emit(msg, -1, True)


class MediaGenQueueController(QObject):
    """串行队列：一次跑一个任务，其余排队。"""

    task_updated = Signal(str)
    queue_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tasks: dict[str, MediaGenTask] = {}
        self._order: list[str] = []
        self._pending: deque[str] = deque()
        self._running_id: str | None = None
        self._thread: QThread | None = None
        self._worker: _GenWorker | None = None

    def tasks(self) -> list[MediaGenTask]:
        return [self._tasks[tid] for tid in self._order if tid in self._tasks]

    def active_count(self) -> int:
        n = len(self._pending)
        if self._running_id:
            n += 1
        return n

    def running_task(self) -> MediaGenTask | None:
        if self._running_id and self._running_id in self._tasks:
            return self._tasks[self._running_id]
        return None

    def enqueue(self, spec: MediaGenSpec) -> str:
        task = MediaGenTask(spec=spec)
        self._tasks[task.id] = task
        self._order.append(task.id)
        self._pending.append(task.id)
        self.queue_changed.emit()
        if not self._running_id:
            self._start_next()
        return task.id

    def enqueue_many(self, spec: MediaGenSpec, count: int) -> list[str]:
        n = max(1, min(8, int(count)))
        ids: list[str] = []
        for i in range(n):
            copy = replace(spec)
            if n > 1 and copy.label:
                copy.label = f"{copy.label} #{i + 1}"
            ids.append(self.enqueue(copy))
        return ids

    def cancel_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task.status == "pending":
            task.status = "cancelled"
            task.message = "已取消"
            task.indeterminate = False
            try:
                self._pending.remove(task_id)
            except ValueError:
                pass
            self.task_updated.emit(task_id)
            self.queue_changed.emit()
            return
        if task_id == self._running_id and self._worker is not None:
            self._worker.cancel()
            task.message = "正在取消…"
            self.task_updated.emit(task_id)

    def clear_pending(self) -> None:
        for tid in list(self._pending):
            task = self._tasks.get(tid)
            if task and task.status == "pending":
                task.status = "cancelled"
                task.message = "已取消"
                task.indeterminate = False
                self.task_updated.emit(tid)
        self._pending.clear()
        self.queue_changed.emit()

    def clear_finished(self) -> None:
        keep: list[str] = []
        for tid in self._order:
            task = self._tasks.get(tid)
            if not task:
                continue
            if task.status in ("completed", "failed", "cancelled"):
                del self._tasks[tid]
                continue
            keep.append(tid)
        self._order = keep
        self.queue_changed.emit()

    def _start_next(self) -> None:
        while self._pending:
            tid = self._pending.popleft()
            task = self._tasks.get(tid)
            if task is None or task.status != "pending":
                continue
            self._run_task(task)
            return
        self._running_id = None
        self.queue_changed.emit()

    def _run_task(self, task: MediaGenTask) -> None:
        self._running_id = task.id
        task.status = "running"
        task.message = "正在启动…"
        task.progress = 0
        task.indeterminate = True
        self.task_updated.emit(task.id)
        self.queue_changed.emit()

        thread = QThread(self)
        worker = _GenWorker(task.spec)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda msg, pct, ind: self._on_progress(task.id, msg, pct, ind))
        worker.finished_ok.connect(lambda path: self._on_ok(task.id, path))
        worker.failed.connect(lambda msg: self._on_fail(task.id, msg))
        worker.cancelled.connect(lambda: self._on_cancelled(task.id))
        worker.finished_ok.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._on_thread_done(task.id))
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_progress(self, task_id: str, msg: str, pct: int, indeterminate: bool) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.message = msg
        task.indeterminate = indeterminate
        if pct >= 0:
            task.progress = pct
        self.task_updated.emit(task_id)

    def _on_ok(self, task_id: str, path_s: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = "completed"
        task.result_path = path_s
        task.progress = 100
        task.indeterminate = False
        task.message = Path(path_s).name
        self.task_updated.emit(task_id)

    def _on_fail(self, task_id: str, msg: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = "failed"
        task.error = msg
        task.indeterminate = False
        task.message = msg or "生成失败"
        self.task_updated.emit(task_id)

    def _on_cancelled(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = "cancelled"
        task.indeterminate = False
        task.message = "已取消"
        self.task_updated.emit(task_id)

    def _on_thread_done(self, task_id: str) -> None:
        if self._running_id == task_id:
            self._running_id = None
        self._thread = None
        self._worker = None
        self.queue_changed.emit()
        self._start_next()
