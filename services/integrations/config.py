# -*- coding: utf-8 -*-
"""三方对接配置加载。"""
from __future__ import annotations

from pathlib import Path

import yaml

from services.config_service import load_config, project_root

_CACHE: dict | None = None


def load_integrations_config(force: bool = False) -> dict:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    path = project_root() / "config" / "integrations.yml"
    merged: dict = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            merged.update(data)
    # app.yml 覆盖（license.dms_base_url 等）
    cfg = load_config()
    license_cfg = cfg.get("license") or {}
    if isinstance(license_cfg, dict) and license_cfg.get("dms_base_url"):
        dms = dict(merged.get("dms") or {})
        dms["base_url"] = license_cfg["dms_base_url"]
        merged["dms"] = dms
    ocr_cfg = cfg.get("ocr") or {}
    if isinstance(ocr_cfg, dict) and ocr_cfg.get("tesseract_path"):
        ocr = dict(merged.get("ocr") or {})
        ocr["tesseract_path"] = ocr_cfg["tesseract_path"]
        merged["ocr"] = ocr
    email_cfg = cfg.get("email") or {}
    if isinstance(email_cfg, dict):
        email = dict(merged.get("email") or {})
        for k in ("smtp_server", "port", "sender_email", "recipient_email"):
            if email_cfg.get(k):
                email[k] = email_cfg[k]
        merged["email"] = email
    _CACHE = merged
    return _CACHE


def integration_enabled(name: str) -> bool:
    block = load_integrations_config().get(name) or {}
    return bool(block.get("enabled"))


def integration_config(name: str) -> dict:
    block = load_integrations_config().get(name) or {}
    return dict(block) if isinstance(block, dict) else {}


def save_integrations_config(updates: dict[str, dict], *, merge: bool = True) -> Path:
    """写回 config/integrations.yml（仅非密钥字段）；force 刷新缓存。"""
    path = project_root() / "config" / "integrations.yml"
    current = load_integrations_config(force=True)
    # 去掉由 app.yml 注入的临时合并痕迹：以磁盘文件为底
    base: dict = {}
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            base = dict(raw)
    else:
        base = {k: dict(v) for k, v in current.items() if isinstance(v, dict)}

    for name, patch in (updates or {}).items():
        if not isinstance(patch, dict):
            continue
        if merge:
            block = dict(base.get(name) or {})
            block.update(patch)
            # 禁止把 api_key 写进 yml
            block.pop("api_key", None)
            base[name] = block
        else:
            clean = dict(patch)
            clean.pop("api_key", None)
            base[name] = clean

    text = yaml.safe_dump(base, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    load_integrations_config(force=True)
    return path
