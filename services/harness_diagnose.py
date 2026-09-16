# -*- coding: utf-8 -*-
"""Harness 诊断包：脱敏状态 + 日志尾 + MANIFEST，供远程排错（不依赖三方 Agent）。"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_output_dir


def _safe_read_text(path: Path, *, limit: int = 80_000) -> str:
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()
        if len(data) > limit:
            data = data[-limit:]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _redacted_config() -> dict[str, Any]:
    from services.harness_config import load_harness_config

    cfg = dict(load_harness_config(force=True))
    for key in ("api_key", "deepseek_api_key", "DEEPSEEK_API_KEY"):
        cfg.pop(key, None)
    # 路径保留；密钥类字段绝不写入
    return {
        "enabled": cfg.get("enabled"),
        "auto_start": cfg.get("auto_start"),
        "stop_on_app_exit": cfg.get("stop_on_app_exit"),
        "surface_mode": cfg.get("surface_mode"),
        "web_port": cfg.get("web_port"),
        "official_bundle_version": cfg.get("official_bundle_version"),
        "prefab_bundle_version": cfg.get("prefab_bundle_version"),
        "node_exe_set": bool(str(cfg.get("node_exe") or "").strip()),
        "dsh_bin_set": bool(str(cfg.get("dsh_bin") or "").strip()),
        "dsh_home_set": bool(str(cfg.get("dsh_home") or "").strip()),
    }


def _status_payload() -> dict[str, Any]:
    from services.harness_status import read_harness_status

    st = read_harness_status(probe_http=True, http_timeout=0.8)
    return {
        "install": str(st.install),
        "service": str(st.service),
        "summary": st.summary,
        "detail": st.detail,
        "port": st.port,
        "node_ok": st.node_ok,
        "dsh_ok": st.dsh_ok,
        "home_ok": st.home_ok,
        "has_key": st.has_key,
        "owned": st.owned,
        "http_ok": st.http_ok,
        "port_busy": st.port_busy,
        "url_has_token": ("?token=" in (st.url or "")),
        # 禁止落完整 URL（含 token）
    }


def _plugin_names() -> list[str]:
    try:
        from services.harness_plugins import list_plugins

        rows = list_plugins()
        names: list[str] = []
        for row in rows[:200]:
            if isinstance(row, dict):
                names.append(str(row.get("name") or row.get("id") or row))
            else:
                names.append(str(row))
        return names
    except Exception:
        return []


def export_diagnostic_pack(*, out_dir: Path | None = None) -> tuple[bool, str, Path | None]:
    """打包脱敏诊断 zip。成功返回 (True, 人话, path)。"""
    from services.harness_prefab import read_installed_manifest
    from services.harness_setup import default_install_root
    from services.harness_sidecar import diagnose_start_log, sidecar_log_path

    root = out_dir or (module_output_dir("harness_agent") / "diagnostics")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = root / f"harness_diag_{stamp}.zip"

    install_root = default_install_root()
    manifest = read_installed_manifest(install_root)
    log_tail = _safe_read_text(sidecar_log_path())
    cause = diagnose_start_log() or ""

    files: dict[str, str] = {
        "README.txt": (
            "运营宝 · 编码智能体诊断包（已脱敏）\n"
            "不含 API Key / credentials。\n"
            "把本 zip 发给客服或研发即可，无需打开 WorkBuddy。\n"
        ),
        "status.json": json.dumps(_status_payload(), ensure_ascii=False, indent=2),
        "config_redacted.json": json.dumps(_redacted_config(), ensure_ascii=False, indent=2),
        "manifest.json": json.dumps(manifest or {}, ensure_ascii=False, indent=2),
        "plugins.json": json.dumps({"plugins": _plugin_names()}, ensure_ascii=False, indent=2),
        "start_cause.txt": cause or "(无)",
        "sidecar_log_tail.txt": log_tail or "(无启动记录)",
    }

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, body in files.items():
                zf.writestr(name, body)
    except OSError as exc:
        return False, f"无法写出诊断包：{exc}", None

    return True, "已导出诊断包（不含密钥）", zip_path
