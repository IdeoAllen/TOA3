# -*- coding: utf-8 -*-
"""DSH 本机 API Key（.credentials.yaml）。

DeepSeek Harness 凭证优先级（上游 dsh-credentials-local）：
  进程环境变量 > $DSH_HOME/.credentials.yaml > 项目/.env > $DSH_HOME/.env

因此：若本机/ WorkBuddy 注入了错误的 DEEPSEEK_API_KEY，会盖住设置页写入的正确密钥，
历史会话会表现为「接不上大模型」。TOA 启动 Sidecar 时必须清掉冲突 env，再注入文件内密钥。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from services.harness_config import dsh_home_path

_KEY_NAMES = ("DEEPSEEK_API_KEY", "deepseek_api_key", "api_key")
# 启动 Sidecar 前从环境剥离，避免脏 Key 盖住 .credentials.yaml
_LLM_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "MOONSHOT_API_KEY",
    "MINIMAX_API_KEY",
    "DASHSCOPE_API_KEY",
    "ZHIPU_API_KEY",
)
_REF_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def credentials_path() -> Path:
    return dsh_home_path() / ".credentials.yaml"


def _read_raw() -> dict[str, Any]:
    path = credentials_path()
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _refs_map(data: dict[str, Any]) -> dict[str, Any]:
    """WorkBuddy / 新版 dsh 使用 {version, refs:{NAME: value}}。"""
    refs = data.get("refs")
    return refs if isinstance(refs, dict) else {}


def _extract_key(data: dict[str, Any]) -> str:
    for name in _KEY_NAMES:
        val = data.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    refs = _refs_map(data)
    for name in _KEY_NAMES:
        val = refs.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def get_api_key() -> str:
    """读取 .credentials.yaml 中的 DeepSeek API Key（无则空串）。"""
    return _extract_key(_read_raw())


def has_api_key() -> bool:
    return len(get_api_key()) >= 8


def mask_api_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "（未配置）"
    return k[:4] + "…" + k[-4:]


def masked_status() -> str:
    if not has_api_key():
        return "未配置"
    return mask_api_key(get_api_key())


def load_credential_map() -> dict[str, str]:
    """返回可注入环境的凭证映射（仅合法 CredentialRef 名）。"""
    out: dict[str, str] = {}
    data = _read_raw()
    # 新版 dsh：优先 refs
    for key, val in _refs_map(data).items():
        name = str(key or "").strip()
        if not name or not _REF_OK.match(name):
            continue
        text = str(val or "").strip()
        if len(text) < 8:
            continue
        out[name] = text
    for key, val in data.items():
        if key in ("version", "refs"):
            continue
        name = str(key or "").strip()
        if not name or not _REF_OK.match(name):
            continue
        text = str(val or "").strip()
        if len(text) < 8:
            continue
        out.setdefault(name, text)
    # 统一 DeepSeek 主名
    ds = _extract_key(data)
    if ds:
        out["DEEPSEEK_API_KEY"] = ds
        out.pop("deepseek_api_key", None)
        out.pop("api_key", None)
    return out


def save_api_key(key: str) -> tuple[bool, str]:
    k = (key or "").strip()
    if len(k) < 8:
        return False, "密钥太短，请粘贴完整的 DeepSeek API Key。"
    home = dsh_home_path()
    home.mkdir(parents=True, exist_ok=True)
    path = credentials_path()
    data = _read_raw()
    # 与上游 dsh-credentials-local 对齐：version + refs
    version = data.get("version") if isinstance(data.get("version"), int) else 1
    refs = _refs_map(data)
    refs = dict(refs)
    refs["DEEPSEEK_API_KEY"] = k
    for alt in ("deepseek_api_key", "api_key"):
        refs.pop(alt, None)
    # 清掉旧扁平键，避免双源
    for alt in _KEY_NAMES:
        data.pop(alt, None)
    data = {"version": version, "refs": refs}
    try:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        return False, str(exc)
    return True, "API Key 已保存到本机 DSH 配置目录。"


def strip_llm_env(env: dict[str, str]) -> None:
    """从即将传给 Sidecar 的环境中移除常见 LLM Key，避免盖住凭证文件。"""
    for name in _LLM_ENV_KEYS:
        env.pop(name, None)


def apply_credentials_to_env(env: dict[str, str]) -> list[str]:
    """把 .credentials.yaml 写入 env（dsh 侧 env 优先于文件，故须显式注入）。"""
    applied: list[str] = []
    for name, value in load_credential_map().items():
        env[name] = value
        applied.append(name)
    return applied


def needs_credential_takeover(*, running: bool, owned: bool) -> tuple[bool, str]:
    """是否需要「接管并重启」才能让历史会话接上设置页大模型。"""
    if not has_api_key():
        return False, ""
    # 外部实例（WorkBuddy 等）未走 TOA 注入路径
    if running and not owned:
        return (
            True,
            "当前是外部 Harness（如 WorkBuddy），未注入 TOA 设置页密钥；"
            "历史会话会接不上大模型。",
        )
    # TOA 托管时 Sidecar 启动已 strip+注入，勿因父进程脏 env 反复重启
    if owned:
        return False, ""
    if process_env_overrides_credentials():
        return (
            True,
            "本机环境变量 DEEPSEEK_API_KEY 与设置页保存的密钥不一致，"
            "会盖住凭证文件。",
        )
    return False, ""


def process_env_overrides_credentials() -> bool:
    """当前 TOA 进程环境是否会盖住 .credentials.yaml 中的 DeepSeek Key。"""
    file_key = get_api_key()
    if not file_key:
        return False
    env_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not env_key:
        return False
    return env_key != file_key


def diagnose_llm_access(*, sidecar_owned: bool = False) -> tuple[bool, str]:
    """判断大模型接入是否健康（仅检查密钥冲突，不联网）。

    sidecar_owned=True 时：Sidecar 已由 TOA strip+注入，父进程脏 env 可忽略。
    """
    if not has_api_key():
        return False, "未配置 DeepSeek API Key，请到系统设置 → 能力接入 → Harness 保存。"
    file_key = get_api_key()
    env_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if env_key and env_key != file_key and not sidecar_owned:
        return (
            False,
            "检测到本机环境变量 DEEPSEEK_API_KEY 与设置页保存的密钥不一致；"
            "Harness 会优先用环境变量，导致历史会话接不上模型。"
            "请在编码智能体页点「更多 → 接管并重启」（或「修复运行环境」后启动），"
            "让 TOA 用正确密钥拉起 Sidecar。",
        )
    if file_key and not file_key.startswith("sk-"):
        return (
            False,
            f"当前保存的 Key 形如 {mask_api_key(file_key)}，不像官方 DeepSeek Key（通常 sk- 开头）。"
            "请到平台复制正确密钥后重新保存。",
        )
    if sidecar_owned:
        return True, f"API Key 已配置（{mask_api_key(file_key)}）· TOA 托管已注入"
    return True, f"API Key 已配置（{mask_api_key(file_key)}）"


def open_credentials_hint() -> str:
    return str(credentials_path())
