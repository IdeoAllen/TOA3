# -*- coding: utf-8 -*-
"""
Harness 统一工具类 —— TOA 业务侧唯一推荐入口。

覆盖：状态 / 启停 / 工作区登记 / 投喂 / 内嵌页桥接（切工作区→新会话→填入）。
底层仍落在 harness_* 模块；本类只做编排与稳定 API，避免各处散落 import。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class FeedPayload:
    text: str = ""
    title: str = ""
    source: str = ""
    workspace_title: str = ""
    workspace_path: str = ""
    auto_prepare: bool = False
    need_reload: bool = False
    plugin_id: str = ""
    session_id: str = ""
    already_prompted: bool = False
    session_title: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "title": self.title,
            "source": self.source,
            "workspace_title": self.workspace_title,
            "workspace_path": self.workspace_path,
            "auto_prepare": "1" if self.auto_prepare else "",
            "need_reload": "1" if self.need_reload else "",
            "plugin_id": self.plugin_id,
            "session_id": self.session_id,
            "already_prompted": "1" if self.already_prompted else "",
            "session_title": self.session_title,
        }


@dataclass
class PrepareResult:
    """内嵌页准备会话的结果摘要。"""

    ok: bool = False
    workspace: str = ""
    chat: str = ""
    inject: str = ""
    raw: str = ""
    steps: list[str] = field(default_factory=list)

    @classmethod
    def from_summary(cls, summary: str) -> "PrepareResult":
        raw = str(summary or "")
        steps = [s for s in raw.split("|") if s]
        ws = chat = inj = ""
        for s in steps:
            if s.startswith("ws:"):
                ws = s[3:]
            elif s.startswith("chat:"):
                chat = s[5:]
            elif s.startswith("inject:"):
                inj = s[7:]
        ok = inj == "ok" or "inject:ok" in raw
        return cls(ok=ok, workspace=ws, chat=chat, inject=inj, raw=raw, steps=steps)


class HarnessToolkit:
    """业务代码请优先：`from services.harness_toolkit import harness`。"""

    # ── 配置 / 路径 ──────────────────────────────────────────

    def web_url(self) -> str:
        from services.harness_config import web_url

        return web_url()

    def dsh_home(self) -> Path:
        from services.harness_config import dsh_home_path

        return Path(dsh_home_path())

    def workspace_json_path(self) -> Path:
        return self.dsh_home() / "storages" / "workspace.json"

    # ── 状态 / 启停 ──────────────────────────────────────────

    def read_status(self):
        from services.harness_status import read_harness_status

        return read_harness_status()

    def start_service(self) -> tuple[bool, str]:
        from services.harness_sidecar import start

        return start()

    def stop_service(self) -> tuple[bool, str]:
        from services.harness_sidecar import stop

        return stop()

    def restart_service(self) -> tuple[bool, str]:
        from services.harness_sidecar import restart

        return restart()

    def open_dsh_home(self) -> Path:
        from services.harness_sidecar import open_config_dir
        from services.os_open import open_in_file_manager

        path = open_config_dir()
        open_in_file_manager(path)
        return Path(path)

    # ── 工作区 ───────────────────────────────────────────────

    def list_workspaces(self) -> list[dict[str, Any]]:
        try:
            from services.harness_host_rpc import host_reachable, list_workspaces_live

            if host_reachable():
                items = list_workspaces_live()
                out = []
                for row in items:
                    out.append(
                        {
                            "id": row.get("workspaceId") or row.get("id") or "",
                            "title": row.get("title") or "",
                            "path": row.get("path") or "",
                            "sessionCount": len(row.get("sessionIds") or []),
                        }
                    )
                return out
        except Exception:
            logger.debug("live list_workspaces failed", exc_info=True)
        from services.harness_workspaces import list_workspaces_from_store

        return list_workspaces_from_store()

    def ensure_workspace(self, path: Path | str, *, title: str = "") -> str:
        """
        登记工作区。优先走 Host RPC（外部实例侧栏立刻可见），
        失败再回退写 workspace.json。返回 workspace id。
        """
        from services.harness_workspaces import ensure_workspace_registered

        display = (title or Path(path).name).strip()
        try:
            from services.harness_host_rpc import ensure_workspace_live, host_reachable

            if host_reachable():
                ws = ensure_workspace_live(path, title=display)
                wid = str(ws.get("workspaceId") or "")
                # 同步落盘，便于 dshm / 离线工具读取
                try:
                    ensure_workspace_registered(path, title=display)
                except Exception:
                    logger.debug("mirror workspace.json failed", exc_info=True)
                if wid:
                    return wid
        except Exception as exc:
            logger.warning("Host workspace.create failed, fallback json: %s", exc)
        return ensure_workspace_registered(path, title=display)

    def create_session(
        self,
        workspace_id: str,
        *,
        title: str = "",
    ) -> str:
        """在工作区新建会话（Host RPC）。返回 sessionId。"""
        from services.harness_host_rpc import create_session_live

        value = create_session_live(workspace_id, title=title)
        return str(value.get("sessionId") or "")

    def prompt_session(self, session_id: str, text: str, *, mode: str = "queue") -> bool:
        """真正投喂：session.prompt 入队。"""
        from services.harness_host_rpc import prompt_session_live

        return prompt_session_live(session_id, text, mode=mode)

    def unregister_workspace(self, path: Path | str) -> int:
        from services.harness_workspaces import unregister_workspace_by_path

        return unregister_workspace_by_path(path)

    def open_folder(self, path: Path | str) -> None:
        from services.os_open import open_in_file_manager

        open_in_file_manager(Path(path).expanduser().resolve())

    def workspace_visible_in_store(self, path: Path | str) -> bool:
        root = Path(path).expanduser().resolve()
        for row in self.list_workspaces():
            try:
                if Path(str(row.get("path") or "")).resolve() == root:
                    return True
            except OSError:
                continue
        return False

    # ── 投喂 / 导航 ──────────────────────────────────────────

    def stash_feed(self, payload: FeedPayload | None = None, **kwargs) -> None:
        from services.harness_feed import stash_feed

        if payload is None:
            payload = FeedPayload(**kwargs)
        stash_feed(
            payload.text,
            title=payload.title,
            source=payload.source,
            workspace_title=payload.workspace_title,
            workspace_path=payload.workspace_path,
            auto_prepare=payload.auto_prepare,
            plugin_id=payload.plugin_id,
            need_reload=payload.need_reload,
            session_id=payload.session_id,
            already_prompted=payload.already_prompted,
            session_title=payload.session_title,
        )

    def peek_feed(self) -> dict[str, str]:
        from services.harness_feed import peek_feed

        return peek_feed()

    def pop_feed(self) -> dict[str, str]:
        from services.harness_feed import pop_feed

        return pop_feed()

    def format_feed(self, feed: dict[str, str] | None = None) -> str:
        from services.harness_feed import format_feed_message, peek_feed

        return format_feed_message(feed if feed is not None else peek_feed())

    def copy_text(self, text: str) -> bool:
        from services.harness_feed import copy_to_clipboard

        return copy_to_clipboard(text)

    def navigate_to_agent(
        self,
        shell,
        text: str,
        *,
        title: str = "",
        source: str = "",
        workspace_title: str = "",
        workspace_path: str = "",
        auto_prepare: bool = False,
        need_reload: bool = False,
        plugin_id: str = "",
        session_id: str = "",
        already_prompted: bool = False,
        session_title: str = "",
    ) -> None:
        """投喂并跳转 harness_agent 页。"""
        from services.harness_feed import navigate_to_harness

        navigate_to_harness(
            shell,
            text,
            title=title,
            source=source,
            workspace_title=workspace_title,
            workspace_path=workspace_path,
            auto_prepare=auto_prepare,
            need_reload=need_reload,
            plugin_id=plugin_id,
            session_id=session_id,
            already_prompted=already_prompted,
            session_title=session_title,
        )

    # ── 内嵌 Web 桥 ──────────────────────────────────────────

    def select_workspace(
        self,
        view: Any,
        *,
        title: str = "",
        path: str = "",
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        from services.harness_web_bridge import select_workspace

        select_workspace(view, title=title, path=path, on_result=on_result)

    def click_new_chat(
        self,
        view: Any,
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        from services.harness_web_bridge import click_new_chat

        click_new_chat(view, on_result=on_result)

    def inject_prompt(
        self,
        view: Any,
        text: str,
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        from services.harness_web_bridge import inject_prompt

        inject_prompt(view, text, on_result=on_result)

    def prepare_session(
        self,
        view: Any,
        *,
        title: str,
        path: str,
        prompt: str,
        on_done: Callable[[PrepareResult], None] | None = None,
    ) -> None:
        """切工作区 → 新会话 → 填入任务（假定侧栏已能看到该工作区）。"""
        from services.harness_web_bridge import prepare_extension_session

        def _wrap(summary: str) -> None:
            if on_done:
                on_done(PrepareResult.from_summary(summary))

        prepare_extension_session(
            view,
            title=title,
            path=path,
            prompt=prompt,
            on_done=_wrap if on_done else None,
        )

    # ── 扩展开发一站式 ───────────────────────────────────────

    def latest_session_for_workspace(
        self,
        workspace_id: str,
        *,
        plugin_id: str = "",
    ) -> str:
        """优先登记表 last_session_id，否则取 Host 工作区 sessionIds[0]。"""
        pid = str(plugin_id or "").strip()
        if pid:
            try:
                from services.plugin_registry import get_plugin_record

                rec = get_plugin_record(pid) or {}
                sid = str(rec.get("last_session_id") or "").strip()
                if sid:
                    return sid
            except Exception:
                logger.debug("read last_session_id failed", exc_info=True)
        wid = str(workspace_id or "").strip()
        if not wid:
            return ""
        try:
            from services.harness_host_rpc import list_workspaces_live

            for row in list_workspaces_live():
                if str(row.get("workspaceId") or "") != wid:
                    continue
                ids = row.get("sessionIds") or []
                if isinstance(ids, list) and ids:
                    return str(ids[0] or "").strip()
        except Exception:
            logger.debug("latest session lookup failed", exc_info=True)
        return ""

    def _remember_session(self, plugin_id: str, session_id: str, workspace_id: str = "") -> None:
        pid = str(plugin_id or "").strip()
        sid = str(session_id or "").strip()
        if not pid or not sid:
            return
        try:
            from services.plugin_registry import set_plugin_field

            fields: dict[str, Any] = {"last_session_id": sid}
            wid = str(workspace_id or "").strip()
            if wid:
                fields["last_workspace_id"] = wid
            set_plugin_field(pid, **fields)
        except Exception:
            logger.debug("persist last_session_id failed", exc_info=True)

    def resume_extension_dev(
        self,
        shell,
        root: Path | str,
        *,
        name: str = "",
        plugin_id: str = "",
    ) -> str:
        """回到已有工作区/会话（不新建会话、不重复投喂）。"""
        path = Path(root).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"扩展目录不存在：{path}")
        display = (name or path.name).strip() or path.name
        wid = self.ensure_workspace(path, title=display)
        sid = self.latest_session_for_workspace(wid, plugin_id=plugin_id)
        sess_title = f"开发 · {display}"
        if not sid:
            # 尚无会话时才新建，且不自动投喂（避免「继续开发」又开干一遍）
            try:
                sid = self.create_session(wid, title=sess_title)
            except Exception as exc:
                logger.warning("resume: create_session fallback failed: %s", exc)
        if sid:
            self._remember_session(plugin_id, sid, wid)
            try:
                from services.extension_sandbox_watchdog import (
                    start_extension_sandbox_watch,
                )

                start_extension_sandbox_watch(
                    session_id=sid,
                    extension_root=path,
                    plugin_id=plugin_id or path.name,
                    parent=shell if isinstance(shell, object) else None,
                )
            except Exception as exc:
                logger.warning("sandbox watch start failed: %s", exc)

        note = f"已回到「{display}」开发会话（未新建）。可直接继续改，或再发一句补充需求。"
        self.navigate_to_agent(
            shell,
            note,
            title=f"继续开发 · {display}",
            source="系统·扩展",
            workspace_title=display,
            workspace_path=str(path),
            auto_prepare=True,
            need_reload=False,
            plugin_id=plugin_id,
            session_id=sid,
            already_prompted=True,
            session_title=sess_title,
        )
        logger.info(
            "resume_extension_dev: %s wid=%s sid=%s path=%s",
            display,
            wid,
            sid,
            path,
        )
        return wid

    def open_extension_dev(
        self,
        shell,
        root: Path | str,
        *,
        name: str = "",
        description: str = "",
        plugin_id: str = "",
        prompt: str = "",
        auto_send: bool = True,
    ) -> str:
        """
        Host RPC：登记工作区 → 新会话 →（可选）真正投喂 → 跳转智能体页并点选。

        返回 workspace id。侧栏由 Harness Host 推送，不依赖手写 workspace.json。
        """
        path = Path(root).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"扩展目录不存在：{path}")
        display = (name or path.name).strip() or path.name
        if not prompt:
            from services.extension_lifecycle import build_dev_task_prompt

            prompt = build_dev_task_prompt(
                root=path, name=display, description=description
            )

        wid = self.ensure_workspace(path, title=display)
        sid = ""
        prompted = False
        sess_title = f"开发 · {display}"
        try:
            sid = self.create_session(wid, title=sess_title)
            if auto_send and sid:
                prompted = self.prompt_session(sid, prompt, mode="queue")
        except Exception as exc:
            logger.warning("Host session/prompt failed: %s", exc)

        if sid:
            self._remember_session(plugin_id, sid, wid)
            try:
                from services.extension_sandbox_watchdog import (
                    start_extension_sandbox_watch,
                )

                start_extension_sandbox_watch(
                    session_id=sid,
                    extension_root=path,
                    plugin_id=plugin_id or path.name,
                    parent=shell if isinstance(shell, object) else None,
                )
            except Exception as exc:
                logger.warning("sandbox watch start failed: %s", exc)

        self.navigate_to_agent(
            shell,
            prompt,
            title=f"开发扩展 · {display}",
            source="系统·扩展",
            workspace_title=display,
            workspace_path=str(path),
            auto_prepare=True,
            need_reload=False,
            plugin_id=plugin_id,
            session_id=sid,
            already_prompted=prompted,
            session_title=sess_title,
        )
        logger.info(
            "open_extension_dev: %s wid=%s sid=%s prompted=%s path=%s",
            display,
            wid,
            sid,
            prompted,
            path,
        )
        return wid


# 单例：业务侧统一调用
harness = HarnessToolkit()
