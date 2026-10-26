#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOA3 ↔ TOA Cloud 联调冒烟（无需启动 uvicorn 时用 TestClient）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CLOUD_BACKEND = ROOT / "cloud" / "backend"


def test_toa3_wiring() -> None:
    from services.config_service import load_config
    from services.license_client import default_manifest_url, license_api_base
    from services.update_check import check_for_update

    load_config(force=True)
    base = license_api_base()
    assert "/api/toa-license" in base, base
    manifest = default_manifest_url()
    assert "manifest" in manifest, manifest
    result = check_for_update(timeout_seconds=0.5)
    assert result.current_version
    print("license_api_base:", base)
    print("manifest_url:", manifest)
    print("update:", result.source, result.latest_version, result.error or "ok")


def test_cloud_api() -> None:
    import subprocess

    code = """
from fastapi.testclient import TestClient
from main import app
with TestClient(app) as c:
    h = c.get("/api/health")
    assert h.status_code == 200, h.text
    m = c.get("/api/toa/releases/manifest", params={"product": "TOA3", "channel": "stable"})
    assert m.status_code == 200, m.text
    assert m.json().get("version")
print("cloud api ok")
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(CLOUD_BACKEND),
        check=True,
    )


if __name__ == "__main__":
    test_toa3_wiring()
    test_cloud_api()
    print("e2e_toa_cloud: OK")
