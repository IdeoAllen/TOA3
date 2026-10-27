# -*- coding: utf-8 -*-
"""首次运行目录与资源引导。"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from services.config_service import project_root, resolve_path

logger = logging.getLogger(__name__)


def bootstrap_runtime() -> None:
    root = project_root()
    for key in ("data_dir", "log_dir", "output_dir", "docs_dir", "images_dir"):
        try:
            p = resolve_path(key)
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    _ensure_app_icon(root)
    _ensure_brand_logo(root)
    _ensure_license_stub(root)
    _ensure_storage_tree()


def _ensure_storage_tree() -> None:
    try:
        from services.storage_paths import ensure_storage_tree

        ensure_storage_tree()
    except Exception as e:
        logger.warning("存储目录树创建失败: %s", e)


def _ensure_app_icon(root: Path) -> None:
    dest = root / "resources" / "icons" / "app_logo.ico"
    try:
        from scripts.gen_toa3_brand_icon import generate_toa3_brand_assets

        generate_toa3_brand_assets(root, force=not dest.is_file())
        if dest.is_file():
            return
    except Exception as e:
        logger.warning("生成 TOA3 图标失败，回退复制: %s", e)
    candidates = [
        root.parent / "TOA" / "avatars" / "logo.ico",
        root.parent / "TOA" / "config" / "assets" / "logo.ico",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    for src in candidates:
        if src.is_file():
            shutil.copy2(src, dest)
            logger.info("已复制应用图标: %s", dest)
            return


def _ensure_brand_logo(root: Path) -> None:
    """由 resources/brand 母版生成 TOA3 品牌 Logo / 图标。"""
    try:
        from scripts.gen_toa3_brand_icon import generate_toa3_brand_assets

        # 多尺寸 ICO / PNG；换母版时升 stamp 强制重生
        stamp = root / "resources" / "icons" / ".toa3_brand_v4"
        force = not stamp.is_file()
        generate_toa3_brand_assets(root, force=force)
        if force:
            stamp.write_text("toa3-brand-v4-emblem-master\n", encoding="utf-8")
            logger.info("已由母版生成 TOA3 品牌图标（v4）")
        return
    except Exception as e:
        logger.warning("生成 TOA3 Logo 失败，尝试回退: %s", e)

    avatars = root / "avatars"
    avatars.mkdir(parents=True, exist_ok=True)
    dest_avatar = avatars / "logo.png"
    dest_brand = root / "resources" / "icons" / "brand_logo.png"

    training = root.parent / "Training" / "winform" / "avatars" / "logo.png"
    toa = root.parent / "TOA" / "avatars" / "logo.png"

    src: Path | None = None
    if training.is_file() and training.stat().st_size > 50000:
        src = training
    elif toa.is_file():
        src = toa

    if src is None:
        return

    for dest in (dest_avatar, dest_brand):
        try:
            if not dest.is_file() or dest.stat().st_size < src.stat().st_size:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                logger.info("已同步品牌 Logo: %s", dest)
        except OSError as e:
            logger.warning("同步 Logo 失败 %s: %s", dest, e)


def _ensure_license_stub(root: Path) -> None:
    path = resolve_path("license_file")
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    example = root / "config" / "license.json.example"
    if example.is_file():
        shutil.copy2(example, path)
        logger.info("已从 example 创建 license.json: %s", path)
        return
    # 冻结包：bundled example
    try:
        from services.runtime_paths import get_bundle_root

        bundled = get_bundle_root() / "config" / "license.json.example"
        if bundled.is_file():
            shutil.copy2(bundled, path)
            logger.info("已从安装包创建 license.json: %s", path)
    except Exception as e:
        logger.warning("创建 license.json 失败: %s", e)
