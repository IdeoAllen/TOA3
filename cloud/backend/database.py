# -*- coding: utf-8 -*-
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite():
    """轻量列迁移（SQLite 无 Alembic 时补字段）。"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    alters = [
        "ALTER TABLE toa_orders ADD COLUMN machine_id VARCHAR(64) DEFAULT ''",
        "ALTER TABLE toa_orders ADD COLUMN payment_provider VARCHAR(32) DEFAULT ''",
        "ALTER TABLE toa_orders ADD COLUMN payment_ref VARCHAR(128) DEFAULT ''",
        "ALTER TABLE toa_feature_packs ADD COLUMN validity_days INTEGER DEFAULT 365",
        "ALTER TABLE toa_licenses ADD COLUMN entitlement VARCHAR(20) DEFAULT ''",
        "ALTER TABLE toa_licenses ADD COLUMN plan_id VARCHAR(64) DEFAULT ''",
        "ALTER TABLE toa_licenses ADD COLUMN order_no VARCHAR(64) DEFAULT ''",
        "ALTER TABLE toa_soft_assets ADD COLUMN recommended BOOLEAN DEFAULT 0",
        "ALTER TABLE toa_menu_modules ADD COLUMN sort_order INTEGER DEFAULT 0",
        "ALTER TABLE toa_menu_modules ADD COLUMN group_order INTEGER DEFAULT 99",
        "ALTER TABLE toa_licenses ADD COLUMN platform_user_id VARCHAR(64) DEFAULT ''",
    ]
    with engine.begin() as conn:
        for sql in alters:
            try:
                conn.execute(text(sql))
            except Exception:
                pass
