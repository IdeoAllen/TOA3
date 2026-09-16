# -*- coding: utf-8 -*-
"""DSH 本机 API Key（.credentials.yaml）。

DeepSeek Harness 凭证优先级（上游 dsh-credentials-local）：
  进程环境变量 > $DSH_HOME/.credentials.yaml > 项目/.env > $DSH_HOME/.env

因此：若本机/ WorkBuddy 注入了错误的 DEEPSEEK_API_KEY，会盖住设置页写入的正确密钥，
历史会话会表现为「接不上大模型」。TOA 启动 Sidecar 时必须清掉冲突 env，再注入文件内密钥。

上游 parseCredentialsDocument 仅允许顶层键：version / refs / records。
误把 EVOLINK_* 等写在顶层会直接 boot 失败（unknown top-level key）。
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
# dsh-credentials-local 仅允许这些顶层键
_TOP_LEVEL_OK = frozenset({"version", "refs", "records"})


def credentials_path() -> Path:
    return dsh_home_path() / ".credentials.yaml"


def credentials_lock_path(home: Path | None = None) -> Path:
    base = Path(home) if home is not None else dsh_home_path()
    return base / ".credentials.yaml.lock"


def clear_stale_credential_locks(home: Path | None = None) -> tuple[bool, str]:
    """清除异常退出留下的凭证写锁。

    dsh atomic-write 若崩溃会留下 ``.credentials.yaml.lock``，下次 boot 会
    ``timed out waiting for the writer lock``。用户看不懂日志——Host 启停/修复时自清。
    锁仍被占用时不硬删，返回失败说明。
    """
    lock = credentials_lock_path(home)
    if not lock.is_file():
        return True, ""
    try:
        lock.unlink()
    except PermissionError:
        return False, "凭证锁仍被占用，请先点「停止服务」再修复"
    except OSError as exc:
        return False, f"无法清除凭证锁：{exc}"
    return True, "已清除异常退出留下的凭证锁"


def _read_raw() -> dict[str, Any]:
    path = credentials_path()
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _write_raw(data: dict[str, Any]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def sanitize_credentials_document() -> tuple[bool, str]:
    """把非法顶层键收进 refs，保证 dsh 能启动。

    上游只认 version / refs / records。EVOLINK_* 等误写在顶层会直接：
    unknown top-level key "EVOLINK_API_KEY" → plugin tree failed to load。
    """
    path = credentials_path()
    if not path.is_file():
        return True, "无凭证文件，跳过"
    data = _read_raw()
    if not data:
        return True, "凭证文件为空，跳过"

    dirty = [k for k in data.keys() if k not in _TOP_LEVEL_OK]
    if not dirty:
        return True, "凭证文件格式正常"

    version = data.get("version") if isinstance(data.get("version"), int) else 1
    refs = dict(_refs_map(data))
    records = data.get("records") if isinstance(data.get("records"), dict) else None
    moved: list[str] = []
    for key in dirty:
        val = data.get(key)
        name = str(key or "").strip()
        if not name or not _REF_OK.match(name):
            continue
        if isinstance(val, (str, int, float)) and str(val).strip():
            if name not in refs:
                refs[name] = str(val).strip()
            moved.append(name)

    clean: dict[str, Any] = {"version": version, "refs": refs}
    if records:
        clean["records"] = records
    try:
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
        _write_raw(clean)
    except OSError as exc:
        return False, f"整理凭证文件失败：{exc}"

    names = "、".join(moved[:6]) + ("…" if len(moved) > 6 else "")
    return True, f"已整理凭证文件：非法顶层键 {len(moved)} 个收进 refs（{names}）"


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
        if key in _TOP_LEVEL_OK:
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
    # 先整理脏顶层键，再写入 DeepSeek Key
    sanitize_credentials_document()
    data = _read_raw()
    # 与上游 dsh-credentials-local 对齐：version + refs（+ 可选 records）
    version = data.get("version") if isinstance(data.get("version"), int) else 1
    refs = dict(_refs_map(data))
    refs["DEEPSEEK_API_KEY"] = k
    for alt in ("deepseek_api_key", "api_key"):
        refs.pop(alt, None)
    records = data.get("records") if isinstance(data.get("records"), dict) else None
    clean: dict[str, Any] = {"version": version, "refs": refs}
    if records:
        clean["records"] = records
    try:
        _write_raw(clean)
    except OSError as exc:
        return False, str(exc)
    return True, "API Key 已保存到本机 DSH 配置目录。"


def ensure_mxapi_image_refs() -> tuple[bool, str]:
    """确保 DSH 凭据含 MXAPI 生图基址（OpenAI 兼容 /v1；余额仍用 /api/v2）。

    不改动已有 MXAPI_API_KEY；仅补齐/纠正 URL 类 refs。
    """
    sanitize_credentials_document()
    data = _read_raw()
    version = data.get("version") if isinstance(data.get("version"), int) else 1
    refs = dict(_refs_map(data))
    changed = False
    openai_base = "https://open.mxapi.org/v1"
    balance_base = "https://open.mxapi.org/api/v2"
    if str(refs.get("MXAPI_OPENAI_BASE_URL") or "").strip().rstrip("/") != openai_base:
        refs["MXAPI_OPENAI_BASE_URL"] = openai_base
        changed = True
    cur_bal = str(refs.get("MXAPI_BASE_URL") or "").strip().rstrip("/")
    # 旧误配成 /api/v1 或空 → 纠正为 v2（余额）；已是 v2/openai 则保留策略：余额固定 v2
    if cur_bal != balance_base:
        refs["MXAPI_BASE_URL"] = balance_base
        changed = True
    if not str(refs.get("MXAPI_API_KEY") or "").strip():
        return False, "DSH 凭据尚无 MXAPI_API_KEY，请先在 Harness 凭据写入。"
    if not changed:
        return True, "MXAPI 生图 refs 已就绪（Key + /v1 + /api/v2）"
    records = data.get("records") if isinstance(data.get("records"), dict) else None
    clean: dict[str, Any] = {"version": version, "refs": refs}
    if records:
        clean["records"] = records
    try:
        _write_raw(clean)
    except OSError as exc:
        return False, str(exc)
    return True, "已写入 MXAPI_OPENAI_BASE_URL=/v1 与 MXAPI_BASE_URL=/api/v2"


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
    """是否需要「接管并重启」才能让历史会话接上本机对话密钥。

    铁律：
    - 服务未在跑时绝不触发——否则用户点「停止」会被「修密钥」又拉起来。
    - **外部占口禁止静默强杀**——须用户在启动/重启确认后再接管。
    - 仅自管进程 + 进程环境变量盖住本机 Key 时，才自动重注。
    """
    if not has_api_key():
        return False, ""
    if not running:
        return False, ""
    if not owned:
        return False, ""
    if process_env_overrides_credentials():
        return True, "本机环境变量与对话密钥不一致，正在重新注入…"
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


def probe_deepseek_balance() -> tuple[bool | None, str]:
    """联网探测 DeepSeek 余额。True=可用；False=不可用；None=跳过/失败。"""
    key = get_api_key()
    if not key:
        return None, ""
    try:
        import json
        import urllib.request

        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == 401:
            return False, f"DeepSeek Key 无效（{mask_api_key(key)}），请到设置页重新保存。"
        return None, ""
    if not isinstance(body, dict):
        return None, ""
    if body.get("is_available") is True:
        return True, "DeepSeek 账户余额可用"
    # 摘一条人话余额，勿堆完整 JSON
    hint = "余额不足或不可用"
    infos = body.get("balance_infos")
    if isinstance(infos, list):
        for row in infos:
            if not isinstance(row, dict):
                continue
            cur = str(row.get("currency") or "").strip()
            total = str(row.get("total_balance") or "").strip()
            if cur and total:
                hint = f"{cur} {total}"
                if cur.upper() == "CNY":
                    break
    return (
        False,
        f"DeepSeek 账户{hint}（API 会报 402 Insufficient Balance / QUOTA）。"
        "请到 platform.deepseek.com 充值后再继续对话；「修一下」无法代充。",
    )


def diagnose_llm_access(*, sidecar_owned: bool = False, probe_balance: bool = False) -> tuple[bool, str]:
    """判断大模型接入是否健康。

    sidecar_owned=True 时：Sidecar 已由 TOA strip+注入，父进程脏 env 可忽略。
    probe_balance=True 时：额外联网查余额（修复/诊断用；进页勿开）。
    """
    if not has_api_key():
        return False, "未配置 DeepSeek 对话密钥，请到编码智能体「更多 → 环境维护」保存。"
    file_key = get_api_key()
    env_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    env_conflict = bool(env_key and env_key != file_key and not sidecar_owned)
    if file_key and not file_key.startswith("sk-"):
        return (
            False,
            f"当前保存的 Key 形如 {mask_api_key(file_key)}，不像官方 DeepSeek Key（通常 sk- 开头）。"
            "请到平台复制正确密钥后重新保存。",
        )
    # 修复路径优先报余额：否则脏 env 会盖住「402 没钱」真因
    if probe_balance:
        bal_ok, bal_msg = probe_deepseek_balance()
        if bal_ok is False:
            if env_conflict:
                return False, bal_msg + " 另：本机环境变量 Key 与设置页不一致，请「重启服务」由 TOA 注入。"
            return False, bal_msg
        if bal_ok is True:
            base = (
                f"API Key 已配置（{mask_api_key(file_key)}）· TOA 托管已注入"
                if sidecar_owned
                else f"API Key 已配置（{mask_api_key(file_key)}）"
            )
            if env_conflict:
                return (
                    False,
                    f"{base} · {bal_msg}。但本机环境变量 DEEPSEEK_API_KEY 与设置页不一致，"
                    "请「重启服务」由 TOA 注入后再用。",
                )
            return True, f"{base} · {bal_msg}"
    if env_conflict:
        return (
            False,
            "检测到本机环境变量 DEEPSEEK_API_KEY 与设置页保存的密钥不一致；"
            "Harness 会优先用环境变量，导致历史会话接不上模型。"
            "请在编码智能体页点「重新启动」或「修一下」后启动，"
            "让 TOA 用正确密钥拉起 Sidecar。",
        )
    if sidecar_owned:
        return True, f"API Key 已配置（{mask_api_key(file_key)}）· TOA 托管已注入"
    return True, f"API Key 已配置（{mask_api_key(file_key)}）"


def open_credentials_hint() -> str:
    return str(credentials_path())
