# -*- coding: utf-8 -*-
"""AgentRuntime v1：委托 harness_toolkit。"""
from __future__ import annotations

from pathlib import Path

from services.harness_toolkit import harness


class HarnessAgentRuntime:
    """DeepSeek Harness 驱动（Host RPC + 壳内定位）。"""

    def ensure_workspace(self, path: Path | str, *, title: str = "") -> str:
        return harness.ensure_workspace(path, title=title)

    def open_dev_session(
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
        return harness.open_extension_dev(
            shell,
            root,
            name=name,
            description=description,
            plugin_id=plugin_id,
            prompt=prompt,
            auto_send=auto_send,
        )

    def resume_dev_session(
        self,
        shell,
        root: Path | str,
        *,
        name: str = "",
        plugin_id: str = "",
    ) -> str:
        return harness.resume_extension_dev(
            shell,
            root,
            name=name,
            plugin_id=plugin_id,
        )

    def prompt(self, session_id: str, text: str, *, mode: str = "queue") -> bool:
        return harness.prompt_session(session_id, text, mode=mode)

    def unregister_workspace(self, path: Path | str) -> int:
        return harness.unregister_workspace(path)
