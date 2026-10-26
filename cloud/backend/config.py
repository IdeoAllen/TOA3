# -*- coding: utf-8 -*-
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("TOA_CLOUD_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("TOA_CLOUD_DATABASE_URL", f"sqlite:///{DATA_DIR / 'toa_cloud.db'}")

JWT_SECRET = os.getenv("TOA_CLOUD_JWT_SECRET", "change-me-in-production")
JWT_EXPIRE_HOURS = int(os.getenv("TOA_CLOUD_JWT_EXPIRE_HOURS", "72"))

ADMIN_USERNAME = os.getenv("TOA_CLOUD_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("TOA_CLOUD_ADMIN_PASSWORD", "admin123")

CORS_ORIGINS = [
    x.strip()
    for x in os.getenv("TOA_CLOUD_CORS_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080").split(",")
    if x.strip()
]

PUBLIC_BASE_URL = os.getenv("TOA_CLOUD_PUBLIC_BASE_URL", "https://toa-service.yczh.tech").rstrip("/")

WEBHOOK_SECRET = os.getenv("TOA_CLOUD_WEBHOOK_SECRET", os.getenv("TOA_CLOUD_PAYMENT_WEBHOOK_SECRET", ""))

# 下载页与安装包同一目录（服务器 /opt/toa-cloud/download/）；全链路只认这里
DOWNLOAD_BASE_URL = f"{PUBLIC_BASE_URL}/download/"
DEFAULT_DOWNLOAD_PAGE = os.getenv("TOA_CLOUD_DOWNLOAD_PAGE", DOWNLOAD_BASE_URL)


def installer_url(version: str) -> str:
    ver = str(version or "").strip().lstrip("vV")
    return f"{DOWNLOAD_BASE_URL}TOA3-Setup-v{ver}.exe"
