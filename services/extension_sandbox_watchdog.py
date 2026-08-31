# -*- coding: utf-8 -*-
"""扩展开发运行时沙箱围栏：越界 Read/Grep/Shell → cancel + 纠偏投喂。"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger("TOA3.extension_sandbox")

_POLL_MS = 1200
_COOLDOWN_S = 6.0
_MAX_TRIPS = 8


class ExtensionSandboxWatchdog(QObject):
    """监视扩展开发会话；工具路径逃出扩展根则硬中断。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._tick)
        self._session_id = ""
        self._extension_root = Path()
        self._plugin_id = ""
        self._skip_lines = 0
        self._trips = 0
        self._last_trip_at = 0.0
        self._seen_paths: set[str] = set()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def watch(
        self,
        *,
        session_id: str,
        extension_root: Path | str,
        plugin_id: str = "",
    ) -> None:
        sid = str(session_id or "").strip()
        root = Path(extension_root).expanduser().resolve()
        if not sid or not root.is_dir():
            logger.warning("sandbox watch skipped: sid=%s root=%s", sid, root)
            return
        self._session_id = sid
        self._extension_root = root
        self._plugin_id = str(plugin_id or root.name).strip()
        self._skip_lines = 0
        self._trips = 0
        self._last_trip_at = 0.0
        self._seen_paths.clear()
        self._active = True
        # 从当前日志末尾开始盯，避免历史越界反复触发
        try:
            from services.extension_sandbox_fence import (
                find_session_dir_by_id,
                load_session_log_bytes,
            )

            sdir = find_session_dir_by_id(sid)
            if sdir is not None:
                raw = load_session_log_bytes(sdir)
                if raw:
                    self._skip_lines = raw.decode("utf-8", errors="replace").count("\n")
                    if raw and not raw.endswith(b"\n"):
                        self._skip_lines += 1
        except Exception as exc:
            logger.debug("baseline skip failed: %s", exc)
        # 钉写沙箱（上游只锁写）
        try:
            from services.harness_host_rpc import pin_workspace_write_live

            pin_workspace_write_live(sid)
        except Exception as exc:
            logger.debug("pin sandbox failed: %s", exc)
        if not self._timer.isActive():
            self._timer.start()
        logger.info(
            "extension sandbox watch on sid=%s root=%s skip_lines=%s",
            sid,
            root,
            self._skip_lines,
        )

    def stop(self) -> None:
        self._active = False
        self._timer.stop()
        self._session_id = ""
        logger.debug("extension sandbox watch stopped")

    def _tick(self) -> None:
        if not self._active or not self._session_id:
            return
        try:
            self._scan_once()
        except Exception as exc:
            logger.debug("sandbox tick failed: %s", exc)

    def _scan_once(self) -> None:
        from services.extension_sandbox_fence import (
            find_session_dir_by_id,
            load_session_log_bytes,
            scan_session_log_bytes,
        )

        sdir = find_session_dir_by_id(self._session_id)
        if sdir is None:
            return
        raw = load_session_log_bytes(sdir)
        if not raw:
            return
        breaches, nlines = scan_session_log_bytes(
            raw,
            extension_root=self._extension_root,
            plugin_id=self._plugin_id,
            skip_lines=self._skip_lines,
        )
        self._skip_lines = nlines
        if not breaches:
            return
        fresh = []
        reads = []
        for b in breaches:
            key = f"{b.kind}|{b.path}".lower()
            if key in self._seen_paths:
                continue
            self._seen_paths.add(key)
            if b.kind == "read_outside":
                reads.append(b)
            else:
                # write_outside / shell_escape：硬闸
                fresh.append(b)
        if reads and not fresh:
            # 越界只读：DSH workspace-write 已禁写；不打断，仅提示一次
            sample = reads[0]
            logger.info(
                "sandbox read-outside (allowed read-only): %s %s",
                sample.tool,
                sample.path,
            )
            try:
                from core.status_service import StatusLevel, report_status
                from app.app_state import AppState

                shell = getattr(AppState.get(), "shell", None)
                if shell is not None:
                    report_status(
                        shell,
                        "沙箱：扩展外只读（不可写入宿主）",
                        level=StatusLevel.INFO,
                    )
            except Exception:
                pass
            return
        if not fresh:
            return
        self._trip(fresh)

    def _trip(self, breaches: list) -> None:
        now = time.monotonic()
        if now - self._last_trip_at < _COOLDOWN_S:
            return
        if self._trips >= _MAX_TRIPS:
            logger.warning(
                "sandbox trips exhausted for %s — stop auto-steer",
                self._session_id,
            )
            return
        self._last_trip_at = now
        self._trips += 1
        sample = breaches[0]
        paths = "；".join(b.path for b in breaches[:3])
        logger.warning(
            "SANDBOX TRIP #%s kind=%s tool=%s paths=%s",
            self._trips,
            sample.kind,
            sample.tool,
            paths,
        )
        try:
            from services.harness_host_rpc import (
                cancel_session_live,
                prompt_session_live,
            )

            cancel_session_live(self._session_id)
            msg = (
                "【沙箱硬闸·已中断本回合】\n"
                f"检测到扩展目录外的写入/危险操作：{paths}\n"
                f"唯一可写目录：{self._extension_root}\n"
                "（扩展外仅允许只读；API 见本目录 HOST_API.md）\n"
                "立刻只在本扩展目录改入口页，继续实现业务主路径。"
            )
            prompt_session_live(self._session_id, msg, mode="steer")
        except Exception as exc:
            logger.warning("sandbox enforce failed: %s", exc)
        try:
            from core.status_service import StatusLevel, report_status

            shell = None
            try:
                from app.app_state import AppState

                shell = getattr(AppState.get(), "shell", None)
            except Exception:
                shell = None
            if shell is not None:
                report_status(
                    shell,
                    f"沙箱拦截：禁止写入扩展外（{sample.tool}）",
                    level=StatusLevel.WARNING,
                )
        except Exception:
            pass


_WATCHDOG: ExtensionSandboxWatchdog | None = None


def get_extension_sandbox_watchdog(parent=None) -> ExtensionSandboxWatchdog:
    global _WATCHDOG
    if _WATCHDOG is None:
        _WATCHDOG = ExtensionSandboxWatchdog(parent)
    return _WATCHDOG


def start_extension_sandbox_watch(
    *,
    session_id: str,
    extension_root: Path | str,
    plugin_id: str = "",
    parent=None,
) -> ExtensionSandboxWatchdog:
    wd = get_extension_sandbox_watchdog(parent)
    wd.watch(
        session_id=session_id,
        extension_root=extension_root,
        plugin_id=plugin_id,
    )
    return wd
