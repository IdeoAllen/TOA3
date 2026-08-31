# -*- coding: utf-8 -*-
"""
AgentRuntime：扩展开发所用智能体运行时适配层。

v1 唯一实现 = DeepSeek Harness（harness_toolkit）。
远期可接 Codex / Claude Code 等，扩展中心产品路径不变。
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentRuntime(Protocol):
    """扩展生命周期唯一依赖的智能体能力面。"""

    def ensure_workspace(self, path: Path | str, *, title: str = "") -> str:
        """登记工作区，返回 workspace id。"""
        ...

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
        """新建开发会话并可选投喂；返回 workspace id。"""
        ...

    def resume_dev_session(
        self,
        shell,
        root: Path | str,
        *,
        name: str = "",
        plugin_id: str = "",
    ) -> str:
        """回到已有会话（不新建、不重复投喂）。"""
        ...

    def prompt(self, session_id: str, text: str, *, mode: str = "queue") -> bool:
        """向会话投喂文本。"""
        ...

    def unregister_workspace(self, path: Path | str) -> int:
        """按路径清理工作区登记。"""
        ...


_ACTIVE: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    """当前进程使用的运行时（默认 Harness）。"""
    global _ACTIVE
    if _ACTIVE is None:
        from services.agent_runtime.harness_runtime import HarnessAgentRuntime

        _ACTIVE = HarnessAgentRuntime()
    return _ACTIVE


def set_agent_runtime(runtime: AgentRuntime | None) -> None:
    """测试或远期切换驱动时注入。"""
    global _ACTIVE
    _ACTIVE = runtime
