#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写入演示用授权人格：主理人全功能包 + 关佳伟单机版。

用法（仓库根目录）:
  python scripts/seed_license_personas.py
  python scripts/seed_license_personas.py --cloud   # 同步 toa-cloud 台账（可选）
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 主理人 · 企业全功能包（enterprise = 专业版 + 培训业务 + 文件包）
OWNER = {
    "name": "赵成",
    "phone": "15164390813",
    "role": "user",
    "pack": "enterprise",
}
# 关佳伟 · 单机基础版（local_free）
STANDALONE_USER = {
    "name": "关佳伟",
    "phone": "18544454463",
    "role": "user",
    "pack": "local_free",
}
EXPIRE = "2027-12-31"


def _issue_code_offline(lm, *, name: str, phone: str, role: str, pack: str) -> tuple[str, str]:
    """离线签发 TOA2 码（不依赖 DMS/云服务）。"""
    import secrets
    import time

    from services.license_manager import (
        _CODE_PREFIX,
        _SCHEMA_VER,
        _b64e,
        _canonical_json,
        _hmac_trunc,
    )

    menus_in_code = ["all"] if role == "admin" else [pack]
    exp_d = datetime.datetime.strptime(EXPIRE, "%Y-%m-%d").date()
    payload = {
        "v": _SCHEMA_VER,
        "name": name,
        "phone": phone,
        "role": role,
        "exp": exp_d.strftime("%Y-%m-%d"),
        "iat": int(time.time()),
        "nonce": secrets.token_hex(8),
        "bind": 0,
        "menus": menus_in_code,
    }
    body = _b64e(_canonical_json(payload).encode("utf-8"))
    sig = _b64e(_hmac_trunc(body.encode("ascii"), 16))
    code = f"{_CODE_PREFIX}-{body}.{sig}"
    return code, lm._code_id(code)


def _user_record(
    lm,
    *,
    name: str,
    phone: str,
    role: str,
    pack: str,
    code: str,
    code_id: str,
    activated: bool,
) -> dict:
    from services.feature_packs import expand_features

    now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    features = expand_features([pack])
    if role == "admin" or pack == "all":
        features = ["all"]
    rec = {
        "name": name,
        "phone": phone,
        "role": role,
        "company": "",
        "expire_date": EXPIRE,
        "issue_date": _today_str(),
        "added_date": now_s,
        "updated_date": now_s,
        "code_id": code_id,
        "code_fingerprint": lm._code_fingerprint(code),
        "license_key": code,
        "revoked": False,
        "bind_machine": False,
        "features": list(features),
        "menus": [pack],
        "activated_machine_id": lm_mid() if activated else "",
        "activated_at": now_s if activated else "",
    }
    return rec


def _today_str() -> str:
    return datetime.date.today().strftime("%Y-%m-%d")


def lm_mid() -> str:
    from services.license_manager import global_license_manager

    return global_license_manager.get_machine_id()


def seed_local_license() -> dict[str, str]:
    from services.feature_packs import expand_features
    from services.license_manager import global_license_manager

    lm = global_license_manager
    lm.load_license()

    owner_code, owner_cid = _issue_code_offline(
        lm, name=OWNER["name"], phone=OWNER["phone"], role=OWNER["role"], pack=OWNER["pack"]
    )
    guan_code, guan_cid = _issue_code_offline(
        lm,
        name=STANDALONE_USER["name"],
        phone=STANDALONE_USER["phone"],
        role=STANDALONE_USER["role"],
        pack=STANDALONE_USER["pack"],
    )

    owner_rec = _user_record(
        lm,
        name=OWNER["name"],
        phone=OWNER["phone"],
        role=OWNER["role"],
        pack=OWNER["pack"],
        code=owner_code,
        code_id=owner_cid,
        activated=True,
    )
    guan_rec = _user_record(
        lm,
        name=STANDALONE_USER["name"],
        phone=STANDALONE_USER["phone"],
        role=STANDALONE_USER["role"],
        pack=STANDALONE_USER["pack"],
        code=guan_code,
        code_id=guan_cid,
        activated=False,
    )

    owner_features = expand_features([OWNER["pack"]])
    now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mid = lm.get_machine_id()

    lm.license_info.update(
        {
            "is_licensed": True,
            "license_key": owner_rec["code_fingerprint"],
            "expire_date": EXPIRE,
            "features": list(owner_features),
            "user_name": OWNER["name"],
            "company": "",
            "phone": OWNER["phone"],
            "role": OWNER["role"],
            "machine_id": mid,
            "bound_machine_id": mid,
            "issue_date": _today_str(),
            "license_type": "enterprise",
            "authorized_users": [owner_rec, guan_rec],
            "activated_code_id": owner_cid,
            "runtime_mode": "",
            "plan_id": OWNER["pack"],
            "online_status": "active",
            "last_online_ok_at": now_s,
        }
    )
    if not lm.save_license():
        raise RuntimeError("写入 license.json 失败")

    return {
        "owner": owner_code,
        "guan": guan_code,
        "license_file": str(lm.license_file),
    }


def seed_toa_cloud(codes: dict[str, str]) -> None:
    cloud_root = ROOT.parent / "toa-cloud"
    backend = cloud_root / "backend"
    if not backend.is_dir():
        print("跳过 toa-cloud：目录不存在")
        return
    import importlib.util

    for mod_name, rel in (
        ("toa_cloud_database", "database.py"),
        ("toa_cloud_license_service", "services/toa_license_service.py"),
    ):
        path = backend / rel
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载 {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)

    init_db = sys.modules["toa_cloud_database"].init_db
    SessionLocal = sys.modules["toa_cloud_database"].SessionLocal
    register_signed_license = sys.modules["toa_cloud_license_service"].register_signed_license

    init_db()
    db = SessionLocal()
    try:
        for key, pack, persona in (
            ("owner", OWNER["pack"], OWNER),
            ("guan", STANDALONE_USER["pack"], STANDALONE_USER),
        ):
            code = codes.get(key, "")
            if not code:
                continue
            register_signed_license(db, code)
            print(f"  toa-cloud 已登记: {persona['name']} · {pack}")
        db.commit()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="种子授权人格：赵成全功能 + 关佳伟单机")
    parser.add_argument("--cloud", action="store_true", help="同步 toa-cloud 台账")
    args = parser.parse_args()

    codes = seed_local_license()
    print(f"已写入: {codes['license_file']}")
    print(f"当前激活: {OWNER['name']} · {OWNER['pack']}（企业全功能包）")
    print(f"{OWNER['name']} 授权码:\n  {codes['owner']}")
    print(f"{STANDALONE_USER['name']} 单机版授权码（local_free）:\n  {codes['guan']}")
    print("关佳伟在本机请点「单机体验」，或在其它电脑用上方码激活。")

    if args.cloud:
        print("同步 toa-cloud …")
        seed_toa_cloud(codes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
