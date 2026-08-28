# -*- coding: utf-8 -*-
"""模型就绪列表（ComfyUI 式）：Ready / 待密钥 / 待下载 / 待端点。"""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.config_service import project_root
from services.integrations.secrets import get_profile_secret
from services.model_catalog import list_capabilities, list_profiles

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_WEIGHT_SUFFIXES = (".safetensors", ".ckpt", ".gguf", ".bin", ".pt")
_CLOUD_PROVIDERS = frozenset({"openai_compatible", "openai_images"})
_LOCAL_PROVIDERS = frozenset({"sd_webui", "comfyui", "ollama"})


class ReadyStatus(StrEnum):
    READY = "ready"
    NEEDS_KEY = "needs_key"
    NEEDS_DOWNLOAD = "needs_download"
    NEEDS_ENDPOINT = "needs_endpoint"


_STATUS_LABELS = {
    ReadyStatus.READY: "可用",
    ReadyStatus.NEEDS_KEY: "待配置密钥",
    ReadyStatus.NEEDS_DOWNLOAD: "待下载权重",
    ReadyStatus.NEEDS_ENDPOINT: "待配置端点",
}


def models_data_root() -> Path:
    return project_root() / "data" / "models"


def scan_local_weight_files() -> list[dict[str, Any]]:
    """扫描 data/models 下已下载权重（不进安装包）。"""
    root = models_data_root()
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _WEIGHT_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        kind = rel.split("/", 1)[0] if "/" in rel else "weights"
        out.append(
            {
                "id": f"local:{rel}",
                "label": path.name,
                "capability": "image_gen",
                "provider": "local_weight",
                "status": ReadyStatus.READY,
                "status_label": _STATUS_LABELS[ReadyStatus.READY],
                "hint": f"本机文件：data/models/{rel}",
                "local_path": str(path.resolve()),
                "kind": kind,
            }
        )
    return out


def _is_local_endpoint(api_base: str) -> bool:
    raw = (api_base or "").strip()
    if not raw:
        return False
    try:
        host = (urlparse(raw).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS or host.endswith(".local")


def _needs_cloud_key(capability: str, profile_id: str, prof: dict[str, Any]) -> bool:
    if get_profile_secret(capability, profile_id, "api_key"):
        return False
    if capability == "text_llm" and profile_id == "moonshot_kimi":
        from services.integrations.secrets import get_secret

        if get_secret("llm", "api_key"):
            return False
    return True


def _local_weight_missing(prof: dict[str, Any]) -> bool:
    rel = str(prof.get("local_weight") or prof.get("weight_path") or "").strip()
    if not rel:
        return False
    p = Path(rel)
    if not p.is_absolute():
        p = models_data_root() / rel
    return not p.is_file()


def evaluate_profile(capability: str, profile_id: str, prof: dict[str, Any]) -> dict[str, Any]:
    """单条 catalog profile 的就绪状态。"""
    provider = str(prof.get("provider") or "").strip()
    api_base = str(prof.get("api_base") or "").strip()
    label = str(prof.get("label") or profile_id)
    status = ReadyStatus.READY
    hint = ""

    if _local_weight_missing(prof):
        status = ReadyStatus.NEEDS_DOWNLOAD
        hint = "运行 scripts/model_hub_comfyui.py 查看下载指引，或放入 data/models/"
    elif provider in _CLOUD_PROVIDERS or (
        provider == "openai_compatible" and api_base and not _is_local_endpoint(api_base)
    ):
        if not api_base:
            status = ReadyStatus.NEEDS_ENDPOINT
            hint = "系统设置 → 能力接入 → 填写 API 地址"
        elif _needs_cloud_key(capability, profile_id, prof):
            status = ReadyStatus.NEEDS_KEY
            hint = "系统设置 → 能力接入 → 保存 API Key"
    elif provider in _LOCAL_PROVIDERS or (
        provider == "openai_compatible" and _is_local_endpoint(api_base)
    ):
        if not api_base:
            status = ReadyStatus.NEEDS_ENDPOINT
            if provider == "comfyui":
                hint = "启动 ComfyUI（默认 http://127.0.0.1:8188），见 scripts/model_hub_comfyui.py"
            elif provider == "sd_webui":
                hint = "启动 SD WebUI/Forge 并加 --api"
            else:
                hint = "填写本地服务地址（如 Ollama http://127.0.0.1:11434/v1）"
    elif not api_base and provider not in ("local_weight",):
        status = ReadyStatus.NEEDS_ENDPOINT
        hint = "系统设置 → 模型库 / 能力接入"

    return {
        "id": profile_id,
        "label": label,
        "capability": capability,
        "provider": provider,
        "api_base": api_base,
        "model": str(prof.get("model") or ""),
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "hint": hint,
        "source": "catalog",
    }


def list_ready(
    capability: str | None = None,
    *,
    ready_only: bool = False,
    include_local_files: bool = True,
) -> list[dict[str, Any]]:
    """合并 catalog 配置与本地下载权重。"""
    caps = [capability] if capability else list_capabilities()
    rows: list[dict[str, Any]] = []
    for cap in caps:
        for prof in list_profiles(cap):
            pid = str(prof.get("id") or "")
            if not pid:
                continue
            row = evaluate_profile(cap, pid, prof)
            if ready_only and row["status"] != ReadyStatus.READY:
                continue
            rows.append(row)
    if include_local_files and (capability is None or capability == "image_gen"):
        for row in scan_local_weight_files():
            if ready_only and row["status"] != ReadyStatus.READY:
                continue
            rows.append(row)
    return rows


def list_all_grouped() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for cap in list_capabilities():
        out[cap] = list_ready(cap, ready_only=False, include_local_files=(cap == "image_gen"))
    return out


def ready_profile_ids(capability: str) -> list[str]:
    return [str(r["id"]) for r in list_ready(capability, ready_only=True) if r.get("source") == "catalog"]
