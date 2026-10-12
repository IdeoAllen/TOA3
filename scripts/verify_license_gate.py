# -*- coding: utf-8 -*-
"""License 最小门禁：SKU/单机层/生产禁 DMS fallback/云服务可达。"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def main() -> int:
    errs: list[str] = []

    packs = yaml.safe_load((ROOT / "config" / "feature_packs.yml").read_text(encoding="utf-8")) or {}
    pack_map = packs.get("packs") or {}
    if "tiyan" not in pack_map:
        errs.append("feature_packs 缺少可售 SKU tiyan")
    else:
        tiyan = pack_map["tiyan"] or {}
        if not tiyan.get("sellable"):
            errs.append("tiyan.sellable 应为 true")
        feats = list(tiyan.get("features") or [])
        if "all" not in feats:
            errs.append("tiyan.features 须含 all")
    if "local_free" not in pack_map:
        errs.append("feature_packs 缺少 local_free")
    else:
        lf = pack_map["local_free"] or {}
        if lf.get("sellable"):
            errs.append("local_free.sellable 须为 false")
        feats = set(lf.get("features") or [])
        for must in ("home", "system_settings", "screenshot_tool", "clipboard_history", "quick_notepad"):
            if must not in feats:
                errs.append(f"local_free 缺少基础模块 {must}")

    # 禁售旧 SKU
    for banned in ("starter", "experience_beta", "professional"):
        if banned in pack_map:
            errs.append(f"禁止保留旧 SKU: {banned}")

    release = yaml.safe_load((ROOT / "config" / "app.release.yml").read_text(encoding="utf-8")) or {}
    lic = release.get("license") or {}
    auth = release.get("auth") or {}
    if auth.get("skip_login"):
        errs.append("app.release.yml auth.skip_login 必须为 false")
    if lic.get("dev_grant_all"):
        errs.append("app.release.yml license.dev_grant_all 必须为 false")
    if lic.get("allow_dms_fallback"):
        errs.append("app.release.yml 须 allow_dms_fallback: false")
    svc = str(lic.get("service_url") or "").strip()
    if "toa-service.yczh.tech" not in svc:
        errs.append(f"release service_url 须指向 toa-service，当前={svc!r}")
    if str(lic.get("dms_base_url") or "").strip():
        errs.append("app.release.yml dms_base_url 应为空（禁 fallback）")

    log_cfg = release.get("log_config") or {}
    level = str(log_cfg.get("log_level") or "").upper()
    if level in ("DEBUG", "NOTSET", ""):
        errs.append(f"app.release.yml log_level 须为 INFO/WARNING，当前={level!r}")

    # 运行时：issuer 可被环境覆盖；云健康检查
    from services.license_manager import _issuer_secret

    secret = _issuer_secret()
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
        errs.append("issuer secret 异常")

    skip_net = "--skip-net" in sys.argv or os.environ.get("TOA_VERIFY_LICENSE_SKIP_NET") == "1"
    if not skip_net:
        url = "https://toa-service.yczh.tech/api/health"
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                body = resp.read(200).decode("utf-8", errors="replace")
                if resp.status != 200 or "ok" not in body.lower():
                    errs.append(f"toa-service health 异常: {resp.status} {body[:80]}")
                else:
                    print(f"OK toa-service health: {body.strip()[:80]}")
        except Exception as e:
            errs.append(f"toa-service 不可达: {e}")

    # 空 service_url + 禁 fallback 须报错
    os.environ.setdefault("TOA_ENV", "development")
    from services import dms_license_client as dlc

    old_cfg = dlc._cfg

    def _fake_cfg_no_url():
        return {"service_url": "", "allow_dms_fallback": False, "dms_base_url": ""}

    dlc._cfg = _fake_cfg_no_url  # type: ignore[assignment]
    try:
        try:
            dlc.license_api_base()
            errs.append("allow_dms_fallback=false 且空 service_url 时应抛错")
        except RuntimeError as e:
            print(f"OK fallback guard: {e}")
    finally:
        dlc._cfg = old_cfg  # type: ignore[assignment]

    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 1
    print("LICENSE GATE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
