# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import ADMIN_PASSWORD, ADMIN_USERNAME, CORS_ORIGINS, DEFAULT_DOWNLOAD_PAGE
from database import SessionLocal, init_db
from routers import (
    auth,
    customers,
    menu_catalog,
    orders,
    packs,
    payments,
    plans,
    releases,
    soft_assets,
    toa_license,
)
from services import auth_service, product_catalog_service, release_service

ADMIN_DIR = Path(__file__).resolve().parent.parent / "admin"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        auth_service.ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        from services import toa_license_service as lic_svc

        lic_svc.ensure_bootstrap_admin_license(db)
        lic_svc.sync_all_licenses_to_customers(db)
        if not release_service.get_current_release(db, product="TOA3", channel="stable"):
            release_service.publish_release(
                db,
                {
                    "product": "TOA3",
                    "channel": "stable",
                    "version": "3.0.0",
                    "download_url": "",
                    "download_page": DEFAULT_DOWNLOAD_PAGE,
                    "release_notes": "TOA3 初始发布。请上传安装包后在此更新 download_url。",
                    "is_current": True,
                },
            )
        product_catalog_service.seed_from_yaml_files(db)
    finally:
        db.close()
    yield


app = FastAPI(title="TOA Cloud", description="TOA 授权与版本服务", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # 明确域名；勿用 "*" 搭配 allow_credentials=True（浏览器会拒）
    allow_origins=CORS_ORIGINS
    or [
        "https://toa-service.yczh.tech",
        "https://www.yczh.tech",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(toa_license.router)
app.include_router(releases.router)
app.include_router(packs.router)
app.include_router(plans.router)
app.include_router(menu_catalog.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(customers.router)
app.include_router(soft_assets.router)

if ADMIN_DIR.is_dir():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "toa-cloud"}
