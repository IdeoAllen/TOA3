# -*- coding: utf-8 -*-
"""授权验收夹具：生成 / 切换不同档位 license.json，便于主理人点验 UI。

用法：
  python scripts/apply_license_fixture.py --list
  python scripts/apply_license_fixture.py --apply 01_trial_standalone_active
  python scripts/apply_license_fixture.py --status
  python scripts/apply_license_fixture.py --restore
  python scripts/apply_license_fixture.py --export-all
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_DIR = ROOT / "assets" / "samples" / "license_acceptance"
BACKUP_SUFFIX = ".bak.acceptance"


def _today() -> date:
    return date.today()


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _base_network_user(
    *,
    name: str,
    phone: str,
    code_id: str,
    expire: date,
    role: str = "user",
    features: list[str] | None = None,
) -> dict[str, Any]:
    feats = list(features or ["local_free"])
    return {
        "name": name,
        "phone": phone,
        "role": role,
        "company": "",
        "expire_date": _fmt(expire),
        "issue_date": _fmt(_today()),
        "added_date": _now_str(),
        "updated_date": _now_str(),
        "code_id": code_id,
        "code_fingerprint": f"ACCEPT-{code_id[:8]}",
        "license_key": "",
        "revoked": False,
        "bind_machine": False,
        "features": feats,
        "menus": feats,
        "activated_at": _now_str(),
    }


def _network_shell(
    *,
    name: str,
    phone: str,
    code_id: str,
    expire: date,
    entitlement: str,
    features: list[str],
    role: str = "user",
    order_no: str = "",
    plan_id: str = "",
) -> dict[str, Any]:
    user = _base_network_user(
        name=name,
        phone=phone,
        code_id=code_id,
        expire=expire,
        role=role,
        features=features,
    )
    return {
        "is_licensed": True,
        "license_key": "",
        "expire_date": _fmt(expire),
        "features": list(features),
        "user_name": name,
        "company": "",
        "phone": phone,
        "role": role,
        "bound_machine_id": "",
        "issue_date": _fmt(_today()),
        "license_type": entitlement,
        "authorized_users": [user],
        "activated_code_id": code_id,
        "runtime_mode": "network",
        "plan_id": plan_id or ("all" if "all" in features else "local_free"),
        "online_status": "active",
        "last_online_ok_at": _now_str(),
        "activated_at": _now_str(),
        "entitlement": entitlement,
        "order_no": order_no,
    }


def _build_fixtures(lm) -> dict[str, dict[str, Any]]:
    """返回 {id: {meta + payload}}。"""
    from services.feature_packs import expand_features

    local_free = expand_features(["local_free"])
    all_feats = ["all"]
    t = _today()

    fixtures: dict[str, dict[str, Any]] = {}

    fixtures["01_trial_standalone_active"] = {
        "title": "基础版 · 单机体验中",
        "chip": "基础版",
        "chip_kind": "info",
        "pack": "基础功能",
        "login": "启动后点登录窗「进入软件」或自动恢复会话",
        "paid_module": "batch_rename 应拦截并引导升级",
        "basic_module": "quick_notepad 可用",
        "payload": {
            "is_licensed": False,
            "license_key": "",
            "expire_date": _fmt(t + timedelta(days=15)),
            "features": local_free,
            "user_name": "验收员·单机体验",
            "company": "",
            "phone": "",
            "role": "user",
            "bound_machine_id": "",
            "issue_date": _fmt(t),
            "license_type": "standalone",
            "authorized_users": [],
            "activated_code_id": "",
            "runtime_mode": "standalone",
            "plan_id": "local_free",
            "entitlement": "standalone",
            "online_status": "",
            "last_online_ok_at": "",
            "order_no": "",
        },
    }

    fixtures["02_trial_standalone_expired"] = {
        "title": "基础版 · 单机体验已到期",
        "chip": "续费",
        "chip_kind": "warning",
        "pack": "基础功能",
        "login": "点「进入软件」；付费模块统一引导购买",
        "paid_module": "watermark_remover 不可打开",
        "basic_module": "screenshot_tool 仍可用",
        "payload": {
            **deepcopy(fixtures["01_trial_standalone_active"]["payload"]),
            "user_name": "验收员·单机到期",
            "expire_date": _fmt(t - timedelta(days=3)),
        },
    }

    fixtures["03_unlicensed_fresh"] = {
        "title": "基础版 · 未激活（出厂空授权）",
        "chip": "基础版",
        "chip_kind": "info",
        "pack": "基础功能",
        "login": "需手动选「进入软件」或粘贴授权码",
        "paid_module": "directory_generator 不可打开",
        "basic_module": "home 可用",
        "payload": {
            "is_licensed": False,
            "license_key": "",
            "expire_date": None,
            "features": [],
            "user_name": "",
            "company": "",
            "phone": "",
            "role": "",
            "bound_machine_id": "",
            "issue_date": None,
            "license_type": "unlicensed",
            "authorized_users": [],
            "activated_code_id": "",
            "runtime_mode": "",
            "plan_id": "",
            "entitlement": "",
            "online_status": "",
            "last_online_ok_at": "",
            "order_no": "",
        },
    }

    fixtures["04_auth_trial_active"] = {
        "title": "授权版 · 体验码有效",
        "chip": "授权版",
        "chip_kind": "success",
        "pack": "基础版 / 体验授权",
        "login": "重启后应自动恢复「验收员·体验授权」",
        "paid_module": "若 features 不含 all，付费模块仍拦截",
        "basic_module": "local_free 模块可用",
        "payload": _network_shell(
            name="验收员·体验授权",
            phone="13800000004",
            code_id="acceptance_trial_active",
            expire=t + timedelta(days=30),
            entitlement="trial",
            features=local_free,
            plan_id="tiyan",
        ),
    }

    fixtures["05_auth_trial_expired"] = {
        "title": "授权版 · 体验码已到期",
        "chip": "续费",
        "chip_kind": "warning",
        "pack": "体验授权",
        "login": "自动恢复会话；顶栏 Chip 为续费",
        "paid_module": "image_watermark 引导升级正式版",
        "basic_module": "clipboard_history 可用",
        "payload": _network_shell(
            name="验收员·体验到期",
            phone="13800000005",
            code_id="acceptance_trial_expired",
            expire=t - timedelta(days=5),
            entitlement="trial",
            features=local_free,
            plan_id="tiyan",
        ),
    }

    fixtures["06_auth_admin"] = {
        "title": "授权版 · 管理员授权",
        "chip": "授权版",
        "chip_kind": "success",
        "pack": "管理员授权",
        "login": "自动恢复「验收员·管理员」",
        "paid_module": "全部模块可打开",
        "basic_module": "全部模块可打开",
        "payload": _network_shell(
            name="验收员·管理员",
            phone="13800000006",
            code_id="acceptance_admin",
            expire=t + timedelta(days=3650),
            entitlement="admin",
            features=all_feats,
            role="admin",
            plan_id="all",
        ),
    }

    fixtures["07_official_paid_active"] = {
        "title": "正式版 · 套餐有效",
        "chip": "正式版",
        "chip_kind": "success",
        "pack": "体验版（订单履约）",
        "login": "自动恢复「验收员·正式版」",
        "paid_module": "全部付费模块可打开",
        "basic_module": "全部模块可打开",
        "payload": _network_shell(
            name="验收员·正式版",
            phone="13800000007",
            code_id="acceptance_paid_active",
            expire=t + timedelta(days=365),
            entitlement="paid",
            features=all_feats,
            role="user",
            order_no="ACCEPT-ORDER-20260830",
            plan_id="tiyan",
        ),
    }

    fixtures["08_official_paid_expired"] = {
        "title": "正式版 · 套餐已到期",
        "chip": "续费",
        "chip_kind": "warning",
        "pack": "体验版（已到期）",
        "login": "自动恢复「验收员·正式到期」",
        "paid_module": "batch_rename 不可打开",
        "basic_module": "quick_notepad 仍可用",
        "payload": _network_shell(
            name="验收员·正式到期",
            phone="13800000008",
            code_id="acceptance_paid_expired",
            expire=t - timedelta(days=7),
            entitlement="paid",
            features=all_feats,
            role="user",
            order_no="ACCEPT-ORDER-EXPIRED",
            plan_id="tiyan",
        ),
    }

    mid = lm.get_machine_id()
    for meta in fixtures.values():
        payload = meta["payload"]
        payload["machine_id"] = mid
        payload.setdefault("schema_ver", 2)
        meta["payload"] = lm._attach_integrity(payload)

    return fixtures


def _license_path() -> Path:
    from services.config_service import resolve_path

    return Path(resolve_path("license_file"))


def _backup_path() -> Path:
    return _license_path().with_suffix(_license_path().suffix + BACKUP_SUFFIX)


def backup_current() -> Path | None:
    src = _license_path()
    if not src.is_file():
        return None
    dst = _backup_path()
    shutil.copy2(src, dst)
    return dst


def restore_backup() -> bool:
    src = _backup_path()
    dst = _license_path()
    if not src.is_file():
        print("无备份可恢复：", src)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    _invalidate()
    print("已恢复备份 →", dst)
    return True


def _invalidate() -> None:
    try:
        import services.config_service as cs

        cs._CONFIG_CACHE = None
    except Exception:
        pass
    try:
        from services.license_manager import global_license_manager

        global_license_manager.invalidate_license_cache()
        global_license_manager.reload_from_disk()
    except Exception:
        pass
    try:
        from services.access_control import invalidate_can_open_cache

        invalidate_can_open_cache()
    except Exception:
        pass


def apply_fixture(fixture_id: str, *, skip_backup: bool = False) -> int:
    from services.license_manager import global_license_manager

    lm = global_license_manager
    fixtures = _build_fixtures(lm)
    if fixture_id not in fixtures:
        print(f"未知夹具：{fixture_id}")
        print("可用：", ", ".join(sorted(fixtures)))
        return 1

    meta = fixtures[fixture_id]
    path = _license_path()
    if not skip_backup:
        bak = backup_current()
        if bak:
            print("已备份当前授权 →", bak)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(meta["payload"], ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    _invalidate()

    print()
    print("=" * 60)
    print(f"已应用夹具：{fixture_id}")
    print(f"场景：{meta['title']}")
    print(f"文件：{path}")
    print("-" * 60)
    print(f"预期顶栏 Chip：{meta['chip']} ({meta['chip_kind']})")
    print(f"预期套餐/身份：{meta['pack']}")
    print(f"登录：{meta['login']}")
    print(f"点验付费模块：{meta['paid_module']}")
    print(f"点验基础模块：{meta['basic_module']}")
    print("-" * 60)
    _print_runtime_status()
    print("请重启：python -m app.main")
    print("=" * 60)
    return 0


def _print_runtime_status() -> None:
    try:
        from services.user_plan_presentation import (
            user_chip_display,
            user_plan_tier,
            user_product_pack_label,
            user_validity_line,
        )

        chip, kind, tip = user_chip_display()
        print(f"运行时档位：{user_plan_tier()} · {user_product_pack_label()}")
        print(f"运行时 Chip：{chip} ({kind})")
        print(f"有效期摘要：{user_validity_line()}")
        print(f"Chip tooltip 首行：{tip.splitlines()[0] if tip else '—'}")
    except Exception as exc:
        print(f"（运行时摘要读取失败：{exc}）")


def export_all() -> int:
    from services.license_manager import global_license_manager

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = _build_fixtures(global_license_manager)
    index: list[dict[str, str]] = []
    for fid, meta in fixtures.items():
        out = FIXTURE_DIR / f"{fid}.json"
        out.write_text(
            json.dumps(meta["payload"], ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        index.append(
            {
                "id": fid,
                "title": meta["title"],
                "chip": meta["chip"],
                "pack": meta["pack"],
            }
        )
    readme = FIXTURE_DIR / "INDEX.json"
    readme.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已导出 {len(fixtures)} 个夹具 → {FIXTURE_DIR}")
    return 0


def list_fixtures() -> int:
    from services.license_manager import global_license_manager

    fixtures = _build_fixtures(global_license_manager)
    print("授权验收夹具（python scripts/apply_license_fixture.py --apply <id>）\n")
    for fid, meta in fixtures.items():
        print(f"  {fid}")
        print(f"    {meta['title']}")
        print(f"    Chip={meta['chip']} · {meta['pack']}")
        print()
    print("切换后请重启 app；恢复现场：--restore")
    return 0


def status_only() -> int:
    path = _license_path()
    print("当前授权文件：", path)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ent = data.get("entitlement") or "—"
            licensed = data.get("is_licensed")
            exp = data.get("expire_date") or "—"
            user = data.get("user_name") or "—"
            print(f"文件摘要：user={user} licensed={licensed} entitlement={ent} expire={exp}")
        except Exception as exc:
            print(f"读取失败：{exc}")
    else:
        print("（文件不存在）")
    print()
    _print_runtime_status()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TOA3 授权验收夹具切换")
    parser.add_argument("--list", action="store_true", help="列出全部夹具")
    parser.add_argument("--apply", metavar="ID", help="应用指定夹具")
    parser.add_argument("--status", action="store_true", help="查看当前档位摘要")
    parser.add_argument("--restore", action="store_true", help="恢复应用夹具前的备份")
    parser.add_argument("--export-all", action="store_true", help="导出 JSON 到 assets/samples/license_acceptance/")
    parser.add_argument("--no-backup", action="store_true", help="应用时不备份当前 license.json")
    args = parser.parse_args()

    if args.list:
        return list_fixtures()
    if args.apply:
        return apply_fixture(args.apply, skip_backup=args.no_backup)
    if args.restore:
        return 0 if restore_backup() else 1
    if args.export_all:
        return export_all()
    if args.status:
        return status_only()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
