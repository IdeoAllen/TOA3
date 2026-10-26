# -*- coding: utf-8 -*-
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(100), default="")
    role = Column(String(20), default="admin")
    can_read = Column(Boolean, default=True, nullable=False)
    can_write = Column(Boolean, default=True, nullable=False)
    can_delete = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ToaLicense(Base):
    __tablename__ = "toa_licenses"
    __table_args__ = (
        Index("ix_toa_licenses_code_id", "code_id", unique=True),
        Index("ix_toa_licenses_status", "status"),
        Index("ix_toa_licenses_phone", "phone"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code_id = Column(String(64), nullable=False, unique=True)
    code_fingerprint = Column(String(40), default="")
    license_key = Column(Text, nullable=False, default="")
    name = Column(String(100), nullable=False, default="")
    phone = Column(String(20), nullable=False, default="")
    role = Column(String(20), nullable=False, default="user")
    menus_json = Column(Text, default='["all"]')
    expire_date = Column(String(10), nullable=False, default="")
    status = Column(String(20), nullable=False, default="active")
    bind_machine = Column(Integer, nullable=False, default=1)
    activated_machine_id = Column(String(64), default="")
    activated_at = Column(DateTime, nullable=True)
    remark = Column(String(500), default="")
    entitlement = Column(String(20), nullable=False, default="")  # trial | paid | admin
    plan_id = Column(String(64), default="")
    order_no = Column(String(64), default="")
    issued_by_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    revoked_by_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String(500), default="")
    last_check_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ToaRelease(Base):
    """TOA 桌面版本发布（供终端 update manifest 与运营台管理）。"""

    __tablename__ = "toa_releases"
    __table_args__ = (Index("ix_toa_releases_product_channel", "product", "channel"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    product = Column(String(32), nullable=False, default="TOA3")
    channel = Column(String(32), nullable=False, default="stable")
    version = Column(String(32), nullable=False)
    download_url = Column(String(500), default="")
    download_page = Column(String(500), default="")
    release_notes = Column(Text, default="")
    min_version = Column(String(32), default="")
    is_current = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    published_by_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ToaOrder(Base):
    """假订单：选 pack → 待付款 → 模拟付款 → 自动签发授权码。"""

    __tablename__ = "toa_orders"
    __table_args__ = (Index("ix_toa_orders_order_no", "order_no", unique=True),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(32), nullable=False, unique=True)
    pack_id = Column(String(64), nullable=False, default="")
    pack_name = Column(String(100), default="")
    customer_name = Column(String(100), nullable=False, default="")
    phone = Column(String(20), nullable=False, default="")
    amount_yuan = Column(Integer, nullable=False, default=0)
    license_days = Column(Integer, nullable=False, default=365)
    status = Column(String(20), nullable=False, default="pending")
    payment_channel = Column(String(20), default="mock")
    license_id = Column(Integer, ForeignKey("toa_licenses.id"), nullable=True)
    machine_id = Column(String(64), default="")
    payment_provider = Column(String(32), default="")
    payment_ref = Column(String(128), default="")
    remark = Column(String(500), default="")
    created_by_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ToaMenuModule(Base):
    """终端管理员发布的菜单 module 目录（运营台组包唯一可选池）。"""

    __tablename__ = "toa_menu_modules"
    __table_args__ = (Index("ix_toa_menu_modules_active", "is_active"),)

    id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False, default="")
    group_id = Column(String(32), default="")
    group_label = Column(String(64), default="")
    sort_order = Column(Integer, default=0, nullable=False)
    group_order = Column(Integer, default=99, nullable=False)
    show_in_menu = Column(Boolean, default=True, nullable=False)
    requires_license = Column(Boolean, default=False, nullable=False)
    feature_id = Column(String(64), default="")
    migration_status = Column(String(20), default="")
    app_version = Column(String(32), default="")
    is_active = Column(Boolean, default=True, nullable=False)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    published_by = Column(String(100), default="")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ToaFeaturePack(Base):
    """运营台维护的产品方案（功能选配 + 有效期 + 定价；表名保留 feature_packs 兼容）。"""

    __tablename__ = "toa_feature_packs"
    __table_args__ = (Index("ix_toa_feature_packs_sellable", "sellable", "is_active"),)

    id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False, default="")
    desc = Column(String(500), default="")
    sellable = Column(Boolean, default=True, nullable=False)
    price_yuan = Column(Integer, nullable=False, default=0)
    validity_days = Column(Integer, nullable=False, default=365)
    features_json = Column(Text, default="[]")
    includes_json = Column(Text, default="[]")
    is_active = Column(Boolean, default=True, nullable=False)
    catalog_version = Column(Integer, default=1, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ToaCustomer(Base):
    """终端社区用户（投稿/下载归因；可启用停用）。"""

    __tablename__ = "toa_customers"
    __table_args__ = (
        Index("ix_toa_customers_phone", "phone"),
        Index("ix_toa_customers_code_id", "code_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), nullable=False, default="")
    display_name = Column(String(100), nullable=False, default="")
    code_id = Column(String(64), default="")
    license_id = Column(Integer, ForeignKey("toa_licenses.id"), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    remark = Column(String(500), default="")
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ToaSoftAsset(Base):
    """办公插件 / 软资产（extension.pack）；无偿流通，审核后公示。"""

    __tablename__ = "toa_soft_assets"
    __table_args__ = (
        Index("ix_toa_soft_assets_plugin", "plugin_id"),
        Index("ix_toa_soft_assets_status", "review_status", "enabled", "listed"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_kind = Column(String(32), nullable=False, default="extension.pack")
    plugin_id = Column(String(64), nullable=False, default="")
    name = Column(String(100), nullable=False, default="")
    description = Column(String(500), default="")
    version = Column(String(32), nullable=False, default="0.1.0")
    group_id = Column(String(32), default="business")
    author = Column(String(100), default="")
    capabilities_json = Column(Text, default='["l1"]')
    integrations_json = Column(Text, default="[]")
    content_sha256 = Column(String(64), default="")
    audit_ok = Column(Boolean, default=False, nullable=False)
    audit_summary = Column(Text, default="")
    review_status = Column(String(20), nullable=False, default="submitted")
    reject_reason = Column(String(500), default="")
    listed = Column(Boolean, default=False, nullable=False)  # 上架公示
    enabled = Column(Boolean, default=True, nullable=False)  # 紧急冻结
    recommended = Column(Boolean, default=False, nullable=False)  # 运营台推荐
    storage_path = Column(String(500), default="")
    customer_id = Column(Integer, ForeignKey("toa_customers.id"), nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ToaSoftAssetEvent(Base):
    """上传/下载流水（无偿·不计费）。"""

    __tablename__ = "toa_soft_asset_events"
    __table_args__ = (
        Index("ix_toa_soft_asset_events_kind_at", "event_kind", "created_at"),
        Index("ix_toa_soft_asset_events_customer", "customer_id"),
        Index("ix_toa_soft_asset_events_asset", "asset_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_kind = Column(String(20), nullable=False, default="upload")  # upload | download
    asset_id = Column(Integer, ForeignKey("toa_soft_assets.id"), nullable=True)
    plugin_id = Column(String(64), default="")
    version = Column(String(32), default="")
    customer_id = Column(Integer, ForeignKey("toa_customers.id"), nullable=True)
    machine_id = Column(String(64), default="")
    result = Column(String(40), default="ok")
    detail = Column(String(500), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
