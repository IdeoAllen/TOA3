# -*- coding: utf-8 -*-
"""应用内下载 TOA3 Setup（异步、落盘到 module_output）。"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal

from services.storage_paths import module_output_dir

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int], None]

_FILENAME_RE = re.compile(r"TOA3-Setup-v[\d.]+\.exe", re.I)
_CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.I)


@dataclass(frozen=True)
class SetupDownloadResult:
    ok: bool
    path: Path | None
    error: str | None = None
    bytes_done: int = 0


def setup_download_dir(*, create: bool = True) -> Path:
    return module_output_dir("app_update", create=create)


def resolve_setup_filename(*, download_url: str, version: str | None = None) -> str:
    url = (download_url or "").strip().split("?")[0].rstrip("/")
    name = url.rsplit("/", 1)[-1] if url else ""
    if name.lower().endswith(".exe") and _FILENAME_RE.search(name):
        return name
    ver = (version or "").strip().lstrip("vV")
    if ver and re.fullmatch(r"\d+\.\d+\.\d+", ver):
        return f"TOA3-Setup-v{ver}.exe"
    return name if name.lower().endswith(".exe") else "TOA3-Setup.exe"


def _fmt_mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


def _fmt_speed(bps: float) -> str:
    if bps <= 0:
        return ""
    if bps >= 1024 * 1024:
        return f" · {bps / (1024 * 1024):.1f} MB/s"
    if bps >= 1024:
        return f" · {bps / 1024:.0f} KB/s"
    return f" · {bps:.0f} B/s"


def download_setup_file(
    download_url: str,
    *,
    version: str | None = None,
    progress: ProgressFn | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = 60.0,
) -> SetupDownloadResult:
    """同步下载（须在工作线程调用）。支持 .part 断点续传（HTTP Range）。"""
    url = (download_url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return SetupDownloadResult(False, None, "无效的下载地址")
    filename = resolve_setup_filename(download_url=url, version=version)
    dest = setup_download_dir(create=True) / filename
    tmp = dest.with_suffix(dest.suffix + ".part")
    prog = progress or (lambda *_a: None)
    cancel = cancel_event or threading.Event()

    def _cancelled() -> bool:
        return cancel.is_set()

    try:
        existing = tmp.stat().st_size if tmp.is_file() else 0
        # 已有完整文件则直接复用
        if dest.is_file() and dest.stat().st_size >= 1024 * 1024:
            if not tmp.is_file():
                size = dest.stat().st_size
                prog(f"已有安装包 {_fmt_mb(size)}", size, size)
                return SetupDownloadResult(True, dest, None, size)

        headers = {
            "User-Agent": "TOA3-setup-download/1.0",
            "Accept": "*/*",
        }
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"
            prog(f"续传中… 已有 {_fmt_mb(existing)}", existing, 0)
        else:
            prog(f"正在连接… {filename}", 0, 0)

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            content_len = int(resp.headers.get("Content-Length") or 0)
            total = 0
            done = 0
            append = False

            if status == 206 and existing > 0:
                append = True
                done = existing
                m = _CONTENT_RANGE_RE.search(resp.headers.get("Content-Range") or "")
                if m and m.group(3) != "*":
                    total = int(m.group(3))
                elif content_len > 0:
                    total = existing + content_len
                prog(f"续传已连接 {_fmt_mb(done)}" + (f" / {_fmt_mb(total)}" if total else ""), done, total)
            elif status == 200:
                # 服务器不支持 Range 或完整响应：重头写
                if existing > 0:
                    logger.info("服务器未返回 206，重新完整下载")
                append = False
                done = 0
                total = content_len
                existing = 0
                if total > 0:
                    prog(f"已连接，开始下载 {_fmt_mb(total)}…", 0, total)
                else:
                    prog("已连接，开始下载…", 0, 0)
            else:
                return SetupDownloadResult(False, None, f"HTTP {status}")

            chunk = 256 * 1024
            last_emit_at = 0.0
            last_emit_done = done
            speed_mark_at = time.monotonic()
            speed_mark_done = done
            mode = "ab" if append else "wb"
            with tmp.open(mode) as out:
                while True:
                    if _cancelled():
                        # 保留 .part 以便下次续传
                        return SetupDownloadResult(False, None, "已取消下载", done)
                    block = resp.read(chunk)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    now = time.monotonic()
                    if (
                        (total > 0 and done >= total)
                        or done - last_emit_done >= 512 * 1024
                        or now - last_emit_at >= 0.35
                    ):
                        dt = max(0.001, now - speed_mark_at)
                        bps = (done - speed_mark_done) / dt
                        speed_mark_at = now
                        speed_mark_done = done
                        spd = _fmt_speed(bps)
                        if total > 0:
                            msg = f"正在下载  {_fmt_mb(done)} / {_fmt_mb(total)}{spd}"
                        else:
                            msg = f"正在下载  {_fmt_mb(done)}{spd}"
                        prog(msg, done, total)
                        last_emit_at = now
                        last_emit_done = done

        if _cancelled():
            return SetupDownloadResult(False, None, "已取消下载", done)

        size = tmp.stat().st_size if tmp.is_file() else 0
        if size < 1024 * 1024:
            tmp.unlink(missing_ok=True)
            return SetupDownloadResult(False, None, f"下载文件过小（{size} 字节），请改用下载页")
        tmp.replace(dest)
        prog(f"下载完成 {_fmt_mb(size)}", size, size)
        return SetupDownloadResult(True, dest, None, size)
    except urllib.error.HTTPError as e:
        # 416 Range Not Satisfiable → 完整文件已下完或 part 损坏
        if e.code == 416 and tmp.is_file() and tmp.stat().st_size >= 1024 * 1024:
            size = tmp.stat().st_size
            tmp.replace(dest)
            prog(f"下载完成 {_fmt_mb(size)}", size, size)
            return SetupDownloadResult(True, dest, None, size)
        logger.info("Setup 下载失败 HTTP %s: %s", e.code, e)
        return SetupDownloadResult(False, None, f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        logger.info("Setup 下载失败: %s", e)
        # 网络中断保留 .part
        return SetupDownloadResult(False, None, str(e))


def launch_setup_installer(setup_path: Path) -> None:
    """启动安装包（交互安装；Inno 会关闭正在运行的 TOA3）。"""
    path = Path(setup_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(path)],
        cwd=str(path.parent),
        close_fds=True,
        creationflags=creationflags or 0,
    )


class _SetupDownloadWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(object)

    def __init__(
        self, url: str, version: str | None, cancel_event: threading.Event
    ) -> None:
        super().__init__()
        self._url = url
        self._version = version
        self._cancel = cancel_event

    def run(self) -> None:
        def _prog(msg: str, done: int, total: int) -> None:
            self.progress.emit(msg, done, total)

        try:
            result = download_setup_file(
                self._url,
                version=self._version,
                progress=_prog,
                cancel_event=self._cancel,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.finished.emit(SetupDownloadResult(False, None, str(exc)))


class SetupDownloadHub(QObject):
    """单次下载任务；避免重复启动。"""

    progress = Signal(str, int, int)
    finished = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._busy = False
        self._thread: QThread | None = None
        self._worker: _SetupDownloadWorker | None = None
        self._cancel = threading.Event()

    def is_busy(self) -> bool:
        return self._busy

    def cancel(self) -> None:
        self._cancel.set()

    def start(self, download_url: str, *, version: str | None = None) -> bool:
        if self._busy:
            return False
        url = (download_url or "").strip()
        if not url:
            return False
        self._cancel = threading.Event()
        self._busy = True
        self.busy_changed.emit(True)
        self.progress.emit("正在连接服务器…", 0, 0)
        self._thread = QThread(self)
        self._worker = _SetupDownloadWorker(url, version, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress, Qt.ConnectionType.QueuedConnection)

        def _done(result: object) -> None:
            self._busy = False
            self.busy_changed.emit(False)
            self.finished.emit(result)
            if self._thread is not None:
                self._thread.quit()

        self._worker.finished.connect(_done, Qt.ConnectionType.QueuedConnection)
        self._thread.start()
        return True


_SETUP_HUB: SetupDownloadHub | None = None


def get_setup_download_hub() -> SetupDownloadHub:
    global _SETUP_HUB
    if _SETUP_HUB is None:
        from PySide6.QtWidgets import QApplication

        _SETUP_HUB = SetupDownloadHub(QApplication.instance())
    return _SETUP_HUB
