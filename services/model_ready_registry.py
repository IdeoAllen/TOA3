# -*- coding: utf-8 -*-
"""模型就绪列表（ComfyUI 式）：Ready / 待密钥 / 待下载 / 待端点。"""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse

from services.config_service import project_root
from services.integrations.secrets import get_profile_secret
from services.model_catalog import list_capabilities, list_profiles

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_WEIGHT_SUFFIXES = (".safetensors", ".ckpt", ".gguf", ".bin", ".pt")
_CLOUD_PROVIDERS = frozenset(
    {
        "openai_compatible",
        "openai_images",
        "evolink_images",
        "volcengine_seedance",
        "evolink_seedance",
    }
)
_LOCAL_PROVIDERS = frozenset({"sd_webui", "comfyui", "ollama", "sdcpp"})

# 本地服务探测缓存（仅模型库「刷新」写入；进页不探测）
_endpoint_probe_cache: dict[str, bool] = {}
_last_probe_at: float = 0.0
_PROBE_MIN_INTERVAL_S = 45.0


class ReadyStatus(StrEnum):
    READY = "ready"
    NEEDS_KEY = "needs_key"
    NEEDS_DOWNLOAD = "needs_download"
    NEEDS_ENDPOINT = "needs_endpoint"


_STATUS_LABELS = {
    ReadyStatus.READY: "可用",
    ReadyStatus.NEEDS_KEY: "待配置密钥",
    ReadyStatus.NEEDS_DOWNLOAD: "待安装本机组件",
    ReadyStatus.NEEDS_ENDPOINT: "待启动或配置",
}


def models_data_root() -> Path:
    return project_root() / "data" / "models"


def _probe_local_endpoint(
    provider: str,
    api_base: str,
    prof: dict[str, Any],
    *,
    deep: bool,
) -> bool:
    base = api_base.strip().rstrip("/")
    ok = False
    try:
        if provider == "comfyui":
            if deep:
                from services.integrations.comfyui_client import workflow_ready

                wf = str(prof.get("workflow") or "sd15_ckpt")
                ok = bool(workflow_ready(base, wf, timeout=2.5))
            else:
                from services.integrations.comfyui_client import health_check

                ok = bool(health_check(base, timeout=0.45))
        elif provider == "sd_webui":
            import httpx

            with httpx.Client(timeout=0.45) as client:
                resp = client.get(base + "/")
                ok = resp.status_code < 500
    except Exception:
        ok = False
    return ok


def refresh_local_endpoint_probes(*, deep: bool = False, force: bool = False) -> None:
    """探测本机 ComfyUI / WebUI。

    - ``deep=False``：仅 ping 是否在线（轻量，切换筛选时可用）
    - ``deep=True``：校验工作流节点与模型目录（仅用户点「刷新」时用）
    """
    global _endpoint_probe_cache, _last_probe_at
    now = time.time()
    if not force and now - _last_probe_at < _PROBE_MIN_INTERVAL_S:
        return
    _last_probe_at = now
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from services.model_catalog import list_profiles

    profiles: list[dict[str, Any]] = []
    for prof in list_profiles("image_gen"):
        provider = str(prof.get("provider") or "").strip()
        base = str(prof.get("api_base") or "").strip().rstrip("/")
        if not base or provider not in ("comfyui", "sd_webui"):
            continue
        profiles.append(prof)
    if not profiles:
        return

    def _run_one(prof: dict[str, Any]) -> list[tuple[str, bool]]:
        provider = str(prof.get("provider") or "").strip()
        pid = str(prof.get("id") or "")
        base = str(prof.get("api_base") or "").strip().rstrip("/")
        ok = _probe_local_endpoint(provider, base, prof, deep=deep)
        keys = [(f"{provider}|{base}", ok)]
        if provider == "comfyui" and pid:
            keys.append((f"comfyui_wf|{pid}|{base}", ok))
        return keys

    workers = min(4, len(profiles))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_one, prof) for prof in profiles]
        for fut in as_completed(futures):
            try:
                for key, ok in fut.result():
                    _endpoint_probe_cache[key] = ok
            except Exception:
                pass


def _local_endpoint_ready(provider: str, api_base: str) -> bool | None:
    """None=尚未刷新探测；True/False=最近一次结果。"""
    key = f"{provider}|{api_base.strip().rstrip('/')}"
    if key not in _endpoint_probe_cache:
        return None
    return bool(_endpoint_probe_cache[key])


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


def _mxapi_key_present() -> bool:
    """任一 MXAPI 图像 profile / 环境 / Harness 凭据有 Key 即视为已配。"""
    shared = (
        "mxapi_nano_banana_2",
        "mxapi_gpt_image_2",
        "mxapi_nano_banana_pro",
    )
    for pid in shared:
        if get_profile_secret("image_gen", pid, "api_key"):
            return True
    import os

    if (os.environ.get("MXAPI_API_KEY") or "").strip():
        return True
    try:
        from services.harness_credentials import load_credential_map

        if str(load_credential_map().get("MXAPI_API_KEY") or "").strip():
            return True
    except Exception:
        pass
    return False


def _needs_cloud_key(capability: str, profile_id: str, prof: dict[str, Any]) -> bool:
    if get_profile_secret(capability, profile_id, "api_key"):
        return False
    if capability == "image_gen" and str(profile_id).startswith("mxapi_"):
        if _mxapi_key_present():
            return False
    if capability == "image_gen" and profile_id == "evolink_grok_imagine":
        if get_profile_secret("video_gen", "evolink_seedance_2", "api_key"):
            return False
    if capability == "video_gen" and profile_id == "evolink_seedance_2":
        if get_profile_secret("image_gen", "evolink_grok_imagine", "api_key"):
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

    if provider == "sdcpp":
        from services.local_image_runtime import install_status

        st = install_status()
        if st.get("ready"):
            status = ReadyStatus.READY
            hint = str(st.get("user_hint") or "")
        else:
            status = ReadyStatus.NEEDS_DOWNLOAD
            miss = "、".join(st.get("missing") or []) or "运行时或模型"
            hint = f"缺{miss} → 点「安装本机生图」一键下载"
    elif _local_weight_missing(prof):
        status = ReadyStatus.NEEDS_DOWNLOAD
        hint = "放入 data/models/，或运行 scripts/setup_local_image_gen.py"
    elif provider in _CLOUD_PROVIDERS or (
        provider == "openai_compatible" and api_base and not _is_local_endpoint(api_base)
    ):
        if not api_base:
            status = ReadyStatus.NEEDS_ENDPOINT
            hint = "系统设置 → 模型管理 → 填写 API 地址"
        elif _needs_cloud_key(capability, profile_id, prof):
            status = ReadyStatus.NEEDS_KEY
            hint = "系统设置 → 模型管理 → 保存 API Key"
    elif provider in _LOCAL_PROVIDERS or (
        provider == "openai_compatible" and _is_local_endpoint(api_base)
    ):
        if provider == "sdcpp":
            pass  # 已在上方处理
        elif not api_base:
            status = ReadyStatus.NEEDS_ENDPOINT
            if provider == "comfyui":
                hint = "填写 ComfyUI 地址（默认 http://127.0.0.1:8188）"
            elif provider == "sd_webui":
                hint = "启动 SD WebUI/Forge 并加 --api"
            else:
                hint = "填写本地服务地址（如 Ollama http://127.0.0.1:11434/v1）"
        elif provider in ("comfyui", "sd_webui"):
            probed = _local_endpoint_ready(provider, api_base)
            if provider == "comfyui":
                wf_key = f"comfyui_wf|{profile_id}|{api_base.strip().rstrip('/')}"
                wf_ok = _endpoint_probe_cache.get(wf_key)
                probed = _local_endpoint_ready(provider, api_base)
                if wf_ok is True:
                    status = ReadyStatus.READY
                    hint = ""
                elif probed is True:
                    # 仅 ping 通过：列表/进页不阻塞 UI，运行时再校验工作流
                    status = ReadyStatus.READY
                    hint = ""
                elif probed is False:
                    status = ReadyStatus.NEEDS_ENDPOINT
                    wf = str(prof.get("workflow") or "sd15_ckpt").strip().lower()
                    if wf in ("z_image_turbo_gguf", "z_image_gguf"):
                        hint = (
                            "ComfyUI 已启动，但缺少 GGUF 模型/节点。"
                            "若本机是 safetensors 版 Z-Image，请改用「Z-Image / 自动匹配」；"
                            "普通用户也可点「安装本机生图」。"
                        )
                    elif wf in ("z_image_turbo", "z_image", "zimage", "z_image_unet", "auto"):
                        hint = (
                            "ComfyUI 已启动，但未找到 Z-Image 模型文件"
                            "（diffusion_models / text_encoders / vae）。"
                            "请确认 ComfyUI 界面能出图后再到模型库点「刷新」。"
                        )
                    else:
                        hint = (
                            "ComfyUI 未就绪或缺少工作流节点/模型。"
                            "请先启动服务并确认界面能出图，再到模型库点「刷新」。"
                            "普通用户请优先「安装本机生图」。"
                        )
                else:
                    status = ReadyStatus.NEEDS_ENDPOINT
                    hint = "ComfyUI 尚未检测 → 模型库点「刷新」"
            elif probed is True:
                status = ReadyStatus.READY
                hint = ""
            else:
                status = ReadyStatus.NEEDS_ENDPOINT
                hint = (
                    "请先启动服务，再到模型库点「刷新」。"
                    "普通用户请优先「安装本机生图」。"
                    if probed is False or probed is None
                    else ""
                )
        elif provider == "ollama" or (
            provider == "openai_compatible" and _is_local_endpoint(api_base)
        ):
            status = ReadyStatus.READY
    elif not api_base and provider not in ("local_weight", "sdcpp"):
        status = ReadyStatus.NEEDS_ENDPOINT
        hint = "系统设置 → 模型库 / 模型管理"

    return {
        "id": profile_id,
        "label": label,
        "capability": capability,
        "provider": provider,
        "api_base": api_base,
        "model": str(prof.get("model") or ""),
        "tier": str(prof.get("tier") or ""),
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "hint": hint,
        "note": str(prof.get("note") or ""),
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
