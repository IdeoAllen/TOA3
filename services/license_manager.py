# -*- coding: utf-8 -*-
"""
授权管理模块：HMAC 签名授权码。固定保留 1 个管理员账号不可清除，
其他账号可在运营宝或 DMS 新增/清除；DMS 提供联网激活/校验。
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import platform
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from services.config_service import get_path_config, load_config, resolve_path

# 拆开存放的 pepper 片段（避免明文一整段密钥）
_P1 = bytes([0x59, 0x43, 0x5A, 0x48, 0x2D, 0x54, 0x4F, 0x41])  # YCZH-TOA
_P2 = b"YunYingBao"
_P3 = bytes.fromhex("a7c3e91f4b6280d5e2f7a04c91b6d83e")
_P4 = b"license-v2-hmac"
_CODE_PREFIX = "TOA2"
_SCHEMA_VER = 2


def _dev_grant_all_enabled() -> bool:
    """开发态默认全授权：仅 TOA_ENV=development 且未打包，且 license.dev_grant_all。"""
    try:
        from services.runtime_paths import is_frozen

        if is_frozen():
            return False
    except Exception:
        pass
    env = os.environ.get("TOA_ENV", "development").strip().lower()
    if env not in ("", "dev", "development"):
        return False
    try:
        from services.config_service import get_license_config

        return bool(get_license_config().get("dev_grant_all"))
    except Exception:
        return False


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text or "") + pad)


def _issuer_secret() -> bytes:
    material = _P1 + b"|" + _P2 + b"|" + _P3 + b"|" + _P4 + b"|v2"
    return hashlib.sha256(material).digest()


def _hmac_hex(message: bytes) -> str:
    return hmac.new(_issuer_secret(), message, hashlib.sha256).hexdigest()


def _hmac_trunc(message: bytes, n: int = 16) -> bytes:
    return hmac.new(_issuer_secret(), message, hashlib.sha256).digest()[:n]


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _today() -> datetime.date:
    return datetime.datetime.now().date()


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def list_licensable_menus() -> List[Dict[str, str]]:
    """可授权菜单清单（与菜单配置同源，不走当前会话可见性过滤）。"""
    try:
        from services.menu_registry import all_menu_items

        items = all_menu_items()
    except Exception:
        items = []
    out: List[Dict[str, str]] = []
    for it in items:
        mid = str(it.get("id") or "").strip()
        name = str(it.get("name") or "").strip()
        if not mid or not name:
            continue
        out.append({"id": mid, "name": name})
    return out


def normalize_menu_features(menus=None) -> List[str]:
    """规范化菜单授权：支持 pack_id 展开；None/空/全选 → ['all']。"""
    if menus is None:
        return ["all"]
    if isinstance(menus, str):
        menus = [menus]
    cleaned = []
    seen = set()
    for m in list(menus or []):
        mid = str(m or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        cleaned.append(mid)
    if not cleaned:
        return ["all"]
    if "all" in cleaned or "*" in cleaned:
        return ["all"]
    all_ids = [m["id"] for m in list_licensable_menus()]
    # 展开功能包 SKU → 菜单 id
    try:
        from services.feature_packs import expand_features

        cleaned = expand_features(cleaned)
    except Exception:
        pass
    if "all" in cleaned:
        return ["all"]
    # 勾选了全部可授权菜单 → 视为 all
    if all_ids and set(cleaned) >= set(all_ids):
        return ["all"]
    return cleaned


class LicenseManager:
    """授权管理器：发卡、验码、激活、名单与防篡改（进程内单例，禁止双实例互相覆盖写盘）。"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LicenseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self.__class__._initialized:
            return
        self.__class__._initialized = True
        self.path_config = get_path_config()
        self.license_file = str(resolve_path("license_file"))
        self.license_info: Dict[str, Any] = {}
        self.load_license()
        # 首次空库：仅当显式允许时写入默认管理员（不含自动全局放权）
        try:
            self.ensure_bootstrap_admin()
        except Exception:
            pass
        try:
            self.migrate_legacy_license()
        except Exception as e:
            print(f"授权迁移失败: {e}")

    def force_cloud_license_check(self) -> Tuple[bool, str]:
        """设置页「联网校验」：强制向 TOA 云服务 check 并刷新本机 license.json。"""
        self.load_license()
        self._licensed_memo = None
        code_id = str(self.license_info.get("activated_code_id") or "")
        mid = self.get_machine_id()
        if code_id:
            try:
                from services.dms_license_client import check_on_dms

                net_ok, net_msg, _payload = check_on_dms(code_id, mid, blocking=True)
                if not net_ok:
                    return False, net_msg or "无法连接 TOA 云服务，请检查网络后重试"
            except Exception as exc:
                return False, f"联网校验失败：{exc}"
        self._licensed_memo = None
        ok, msg = self._activation_still_valid()
        if ok:
            return True, self.get_validity_text()
        if not code_id and self.is_standalone_mode():
            return True, self.get_validity_text()
        return False, msg or "校验后授权无效或尚未联网激活"

    def reload_from_disk(self) -> bool:
        """从磁盘重新加载授权（激活后/切换账号后调用）。"""
        try:
            self.load_license()
            return True
        except Exception as e:
            print(f"重新加载授权失败: {e}")
            return False

    def migrate_legacy_license(self):
        """旧版 DEMO/无授权码 → 为管理员补发卡；仅当本机仍在有效期内才尝试联网激活。"""
        users = list(self.license_info.get("authorized_users") or [])
        admin = None
        for u in users:
            if not isinstance(u, dict):
                continue
            if str(u.get("role") or "") == "admin" or str(u.get("name") or "") in ("管理员", "admin"):
                admin = u
                break
        if admin is None:
            return

        need_issue = not str(admin.get("code_id") or "")
        if not need_issue:
            return

        old_licensed = bool(self.license_info.get("is_licensed"))
        old_exp = _parse_date(self.license_info.get("expire_date"))
        keep_active = old_licensed and old_exp and old_exp >= _today()
        days = 3650
        if keep_active and old_exp:
            days = max(30, (old_exp - _today()).days)
        ok, _msg, code = self.issue_license_code(
            str(admin.get("name") or "管理员"),
            str(admin.get("phone") or "12345678901"),
            days=days,
            role="admin",
            bind_machine=True,
        )
        if ok and code and keep_active:
            self.activate_with_code(code)
            try:
                tip = os.path.join(os.path.dirname(self.license_file), "admin_bootstrap_code.txt")
                with open(tip, "w", encoding="utf-8") as f:
                    f.write(
                        "运营宝管理员引导授权码（请登录后重新发卡并删除本文件）\n"
                        f"{code}\n"
                        f"有效期至: {(self.license_info or {}).get('expire_date')}\n"
                    )
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 存储与防篡改
    # ------------------------------------------------------------------ #
    def _default_license(self) -> Dict[str, Any]:
        return {
            "is_licensed": False,
            "license_key": "",
            "expire_date": None,
            "features": [],
            "user_name": "",
            "company": "",
            "phone": "",
            "role": "",
            "machine_id": self.get_machine_id(),
            "bound_machine_id": "",
            "issue_date": None,
            "license_type": "unlicensed",
            "authorized_users": [],
            "activated_code_id": "",
            "schema_ver": _SCHEMA_VER,
        }

    def _compute_integrity(self, info: Dict[str, Any]) -> str:
        payload = {k: v for k, v in info.items() if k != "_integrity"}
        return _hmac_hex(_canonical_json(payload).encode("utf-8"))

    def _attach_integrity(self, info: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(info)
        out.pop("_integrity", None)
        out["schema_ver"] = _SCHEMA_VER
        out["_integrity"] = self._compute_integrity(out)
        return out

    def verify_store_integrity(self, info: Optional[Dict[str, Any]] = None) -> bool:
        data = info if isinstance(info, dict) else self.license_info
        if not isinstance(data, dict):
            return False
        sig = str(data.get("_integrity") or "")
        if not sig:
            # 旧文件无指纹：视为待迁移，不直接判死
            return False
        expect = self._compute_integrity(data)
        return hmac.compare_digest(sig, expect)

    def load_license(self):
        self.license_info = self._default_license()
        try:
            if not os.path.exists(self.license_file):
                return
            with open(self.license_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                return
            self.license_info.update(loaded)
            self.license_info.setdefault("authorized_users", [])
            # 迁移旧数据：补指纹（仅当尚未有指纹时）
            if not self.license_info.get("_integrity"):
                self.license_info = self._attach_integrity(self.license_info)
                self.save_license()
            elif not self.verify_store_integrity():
                # 被窜改：降级为未授权，但保留名单供管理员重建
                users = list(self.license_info.get("authorized_users") or [])
                print("[LICENSE] 授权文件完整性校验失败，已降级为未授权（防窜改）")
                self.license_info = self._default_license()
                self.license_info["authorized_users"] = users
                self.license_info = self._attach_integrity(self.license_info)
                self.save_license()
        except Exception as e:
            print(f"加载授权文件失败: {e}")

    def save_license(self) -> bool:
        try:
            config_dir = os.path.dirname(self.license_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)
            self.license_info = self._attach_integrity(self.license_info)
            with open(self.license_file, "w", encoding="utf-8") as f:
                json.dump(self.license_info, f, ensure_ascii=False, indent=4)
            self._licensed_memo = None
            return True
        except Exception as e:
            print(f"保存授权文件失败: {e}")
            return False

    def invalidate_license_cache(self) -> None:
        """强制下次 is_licensed / 联网校验不走 memo。"""
        self._licensed_memo = None
        try:
            from services.access_control import invalidate_can_open_cache

            invalidate_can_open_cache()
        except Exception:
            pass
        try:
            from services.dms_license_client import invalidate_check_cache

            invalidate_check_cache()
        except Exception:
            pass

    def reconcile_after_expiry(self) -> str:
        """到期/停用后持久化降级，单机版回 local_free。"""
        self.invalidate_license_cache()
        ok, msg = self._activation_still_valid_uncached()
        if ok:
            return ""
        try:
            from services.edition_profile import edition_id

            if edition_id() == "standalone":
                self.enter_standalone_mode()
                return "订阅已到期，已恢复单机基础版。可在「系统设置 → 订阅购买」续费。"
        except Exception:
            pass
        if self.license_info.get("is_licensed"):
            self.license_info["is_licensed"] = False
            self.license_info["features"] = []
            if not str(self.license_info.get("online_status") or "").strip():
                self.license_info["online_status"] = "expired"
            try:
                self.save_license()
            except Exception:
                pass
        hint = msg or "授权已失效"
        if "订阅购买" not in hint:
            hint = f"{hint}。请在「系统设置 → 订阅购买」续费。"
        return hint

    def get_machine_id(self) -> str:
        try:
            system_info = platform.system() + platform.node() + platform.machine()
            return hashlib.sha256(system_info.encode("utf-8")).hexdigest()[:32]
        except Exception:
            return "unknown_machine"

    # ------------------------------------------------------------------ #
    # 授权码签发 / 验签
    # ------------------------------------------------------------------ #
    def _code_id(self, license_key: str) -> str:
        return hashlib.sha256((license_key or "").encode("utf-8")).hexdigest()

    def _code_fingerprint(self, license_key: str) -> str:
        key = (license_key or "").strip()
        if len(key) < 12:
            return key
        return f"{key[:10]}…{key[-6:]}"

    def issue_license_code(
        self,
        user_name: str,
        phone: str = "",
        *,
        days: int = 365,
        role: str = "user",
        expire_date: Optional[str] = None,
        bind_machine: bool = False,
        menus=None,
    ) -> Tuple[bool, str, Optional[str]]:
        """签发授权码；联网模式下生成后必须先登记到 DMS，再写本机名单。"""
        name = (user_name or "").strip()
        phone = (phone or "").strip()
        role = (role or "user").strip() or "user"
        features = normalize_menu_features(menus)
        if role == "admin":
            features = ["all"]
        if not name:
            return False, "姓名不能为空", None
        if name in ("管理员", "admin"):
            return False, "「管理员」为系统固定账号，请换一个姓名", None
        if not phone or not (len(phone) == 11 and phone.isdigit()):
            return False, "请填写 11 位手机号", None
        if days is not None and int(days) <= 0 and not expire_date:
            return False, "有效期天数必须大于 0", None

        if expire_date:
            exp_d = _parse_date(expire_date)
            if not exp_d:
                return False, "有效期日期格式错误，应为 YYYY-MM-DD", None
        else:
            exp_d = _today() + datetime.timedelta(days=int(days))

        iat = int(time.time())
        nonce = secrets.token_hex(8)
        payload = {
            "v": _SCHEMA_VER,
            "name": name,
            "phone": phone,
            "role": role,
            "exp": exp_d.strftime("%Y-%m-%d"),
            "iat": iat,
            "nonce": nonce,
            "bind": 1 if bind_machine else 0,
            "menus": features,
        }
        body = _b64e(_canonical_json(payload).encode("utf-8"))
        sig = _b64e(_hmac_trunc(body.encode("ascii"), 16))
        code = f"{_CODE_PREFIX}-{body}.{sig}"

        # 联网：先记到 DMS，失败则不发码（DMS 必须留存授权与授权码）
        try:
            from services.dms_license_client import register_on_dms

            ok_net, net_msg, _ = register_on_dms(code)
            if not ok_net:
                return False, f"同步 DMS 失败：{net_msg}", None
        except Exception as e:
            return False, f"同步 DMS 异常：{e}", None

        user = self.find_authorized_user(name, phone)
        old_cid = str((user or {}).get("code_id") or "").strip()
        now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "name": name,
            "phone": phone,
            "role": role,
            "company": (user or {}).get("company") or "",
            "expire_date": exp_d.strftime("%Y-%m-%d"),
            "issue_date": _today().strftime("%Y-%m-%d"),
            "added_date": (user or {}).get("added_date") or now_s,
            "updated_date": now_s,
            "code_id": self._code_id(code),
            "code_fingerprint": self._code_fingerprint(code),
            "license_key": code,
            "revoked": False,
            "bind_machine": bool(bind_machine),
            "features": list(features),
            "activated_machine_id": "",
            "activated_at": "",
        }
        users = list(self.license_info.get("authorized_users") or [])
        replaced = False
        for i, u in enumerate(users):
            if not isinstance(u, dict):
                continue
            if str(u.get("name") or "").strip() == name and str(u.get("phone") or "").strip() == phone:
                users[i] = record
                replaced = True
                break
        if not replaced:
            users.append(record)
        self.license_info["authorized_users"] = users
        if not self.save_license():
            return False, "已同步 DMS，但本机名单保存失败（授权码仍可用）", code
        if old_cid and old_cid != record["code_id"]:
            self.sync_user_to_dms({"code_id": old_cid, "name": name, "phone": phone}, op="delete", remark="终端换发删除旧码")
        self.sync_user_to_dms(record, op="upsert", license_key=code, remark="终端签发")
        return True, "授权码已生成并同步到 DMS", code

    def _sign_dms_sync(self, envelope: dict) -> dict:
        data = dict(envelope or {})
        sig = _b64e(_hmac_trunc(_canonical_json(data).encode("utf-8"), 16))
        return {"data": data, "sig": sig}

    def sync_user_to_dms(
        self,
        user: dict,
        *,
        op: str = "upsert",
        license_key: str = "",
        remark: str = "",
    ) -> Tuple[bool, str]:
        """把本机名单变更同步到 DMS。"""
        if not isinstance(user, dict):
            return False, "无效的授权账号"
        cid = str(user.get("code_id") or "").strip()
        key = str(license_key or "").strip()
        if not cid and not key:
            return True, "无授权码，跳过 DMS 同步"
        envelope = {
            "v": _SCHEMA_VER,
            "op": str(op or "upsert"),
            "iat": int(time.time()),
            "nonce": secrets.token_hex(8),
            "code_id": cid,
            "code_fingerprint": str(user.get("code_fingerprint") or ""),
            "name": str(user.get("name") or "").strip(),
            "phone": str(user.get("phone") or "").strip(),
            "role": str(user.get("role") or "user").strip() or "user",
            "expire_date": str(user.get("expire_date") or "").strip(),
            "revoked": bool(user.get("revoked")),
            "bind_machine": bool(user.get("bind_machine", True)),
            "features": list(user.get("features") or user.get("menus") or ["all"]),
            "license_key": key,
            "remark": remark or "终端同步",
            "reason": str(user.get("revoke_reason") or ""),
        }
        try:
            from services.dms_license_client import sync_roster_on_dms

            ok, msg, _ = sync_roster_on_dms(self._sign_dms_sync(envelope))
            if not ok:
                return False, msg or "同步 DMS 失败"
            return True, "已同步 DMS"
        except Exception as e:
            return False, f"同步 DMS 异常：{e}"

    def update_authorized_user(
        self,
        name: str,
        phone: str = "",
        *,
        new_name: Optional[str] = None,
        new_phone: Optional[str] = None,
        days: Optional[int] = None,
        expire_date: Optional[str] = None,
        revoked: Optional[bool] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """改本机授权账号并同步 DMS。"""
        user = self.find_authorized_user(name, phone)
        if not user:
            return False, "未找到该授权账号", None
        if str(user.get("role") or "").strip().lower() == "admin":
            if self.is_protected_admin(user):
                return False, "固定管理员账号不可修改", None
        rec = dict(user)
        if new_name is not None:
            nm = str(new_name).strip()
            if not nm:
                return False, "姓名不能为空", None
            rec["name"] = nm
        if new_phone is not None:
            ph = str(new_phone).strip()
            if not ph or not (len(ph) == 11 and ph.isdigit()):
                return False, "请填写 11 位手机号", None
            rec["phone"] = ph
        if expire_date:
            exp_d = _parse_date(expire_date)
            if not exp_d:
                return False, "有效期日期格式错误，应为 YYYY-MM-DD", None
            rec["expire_date"] = exp_d.strftime("%Y-%m-%d")
        elif days is not None:
            try:
                d = int(days)
            except Exception:
                return False, "有效期天数无效", None
            if d <= 0:
                return False, "有效期天数必须大于 0", None
            rec["expire_date"] = (_today() + datetime.timedelta(days=d)).strftime("%Y-%m-%d")
        if revoked is not None:
            rec["revoked"] = bool(revoked)
        rec["updated_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        users = list(self.license_info.get("authorized_users") or [])
        for i, u in enumerate(users):
            if not isinstance(u, dict):
                continue
            if str(u.get("name") or "").strip() == (name or "").strip() and str(u.get("phone") or "").strip() == (
                phone or ""
            ).strip():
                users[i] = rec
                break
        self.license_info["authorized_users"] = users
        if not self.save_license():
            return False, "本机保存失败", None
        ok, msg = self.sync_user_to_dms(rec, op="upsert", remark="终端修改")
        if not ok:
            return False, f"本机已保存，但同步 DMS 失败：{msg}", rec
        return True, "已保存并同步 DMS", rec

    def purge_duplicate_placeholder_admins(self) -> int:
        """只保留一个固定管理员；同名「管理员」占位从本机名单去掉。"""
        prot = self.get_protected_admin()
        prot_phone = str((prot or {}).get("phone") or "12345678901").strip()
        users = list(self.license_info.get("authorized_users") or [])
        kept = []
        removed = 0
        for u in users:
            if not isinstance(u, dict):
                continue
            name = str(u.get("name") or "").strip()
            phone = str(u.get("phone") or "").strip()
            if name in ("管理员", "admin") and phone != prot_phone:
                removed += 1
                continue
            kept.append(u)
        if removed:
            self.license_info["authorized_users"] = kept
            self.save_license()
        return removed

    def sync_all_authorized_users_to_dms(self) -> Tuple[int, int, str]:
        """以本机名单为准同步 DMS：推送普通账号，并清掉 DMS 里已不在本机的多余记录。"""
        try:
            self.purge_duplicate_placeholder_admins()
        except Exception:
            pass
        ok_n = fail_n = skip_n = 0
        errors: List[str] = []
        keep_cids: List[str] = []
        keep_phones: List[str] = []
        for u in self.get_authorized_users():
            if not isinstance(u, dict):
                continue
            name = str(u.get("name") or "").strip() or "未命名"
            cid = str(u.get("code_id") or "").strip()
            phone = str(u.get("phone") or "").strip()
            if cid:
                keep_cids.append(cid)
            if phone:
                keep_phones.append(phone)
            if self.is_protected_admin(u):
                skip_n += 1
                continue
            if not cid and not str(u.get("license_key") or "").strip():
                fail_n += 1
                errors.append(f"{name}：无授权码，请重新签发")
                continue
            op = "revoke" if u.get("revoked") else "upsert"
            ok, msg = self.sync_user_to_dms(
                u,
                op=op,
                license_key=str(u.get("license_key") or ""),
                remark="终端全量同步",
            )
            if ok:
                ok_n += 1
            else:
                fail_n += 1
                errors.append(f"{name}：{msg}")
        rec_ok, rec_msg, rec_n = self.sync_roster_reconcile_to_dms(keep_cids, keep_phones)
        if not rec_ok:
            fail_n += 1
            errors.append(f"清多余：{rec_msg}")
        summary = f"成功 {ok_n} 条"
        if skip_n:
            summary += f"，固定管理员已跳过 {skip_n} 条"
        if rec_ok and rec_n:
            summary += f"，已从 DMS 清除多余 {rec_n} 条"
        if fail_n:
            summary += f"，失败 {fail_n} 条"
            if errors:
                summary += "\n" + "\n".join(errors[:8])
        return ok_n, fail_n, summary

    def sync_roster_reconcile_to_dms(self, keep_code_ids: List[str], keep_phones: List[str]) -> Tuple[bool, str, int]:
        envelope = {
            "v": _SCHEMA_VER,
            "op": "reconcile",
            "iat": int(time.time()),
            "nonce": secrets.token_hex(8),
            "keep_code_ids": list(keep_code_ids or []),
            "keep_phones": list(keep_phones or []),
            "remark": "终端名单对账",
        }
        try:
            from services.dms_license_client import reconcile_roster_on_dms

            ok, msg, payload = reconcile_roster_on_dms(self._sign_dms_sync(envelope))
            if not ok:
                return False, msg or "对账失败", 0
            deleted = 0
            if isinstance(payload, dict):
                try:
                    deleted = int(payload.get("deleted") or 0)
                except Exception:
                    deleted = 0
            return True, "ok", deleted
        except Exception as e:
            return False, f"对账异常：{e}", 0

    def search_authorized_users(self, keyword: str = "") -> List[Dict[str, Any]]:
        q = str(keyword or "").strip().lower()
        users = [u for u in self.get_authorized_users() if isinstance(u, dict)]
        if not q:
            return users
        out = []
        for u in users:
            blob = " ".join(
                [
                    str(u.get("name") or ""),
                    str(u.get("phone") or ""),
                    str(u.get("role") or ""),
                    str(u.get("expire_date") or ""),
                    str(u.get("code_fingerprint") or ""),
                ]
            ).lower()
            if q in blob:
                out.append(u)
        return out

    def verify_license_code(self, license_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """验签授权码（不写盘）。返回 (ok, message, payload)。"""
        key = (license_key or "").strip().replace(" ", "")
        if not key:
            return False, "请输入授权码", None
        if not key.startswith(f"{_CODE_PREFIX}-"):
            return False, "授权码格式无效（需管理员新签发的 TOA2 授权码）", None
        try:
            rest = key[len(_CODE_PREFIX) + 1 :]
            body, sig = rest.rsplit(".", 1)
        except Exception:
            return False, "授权码格式无效", None
        try:
            expect = _b64e(_hmac_trunc(body.encode("ascii"), 16))
            if not hmac.compare_digest(sig, expect):
                return False, "授权码签名校验失败（可能被窜改或伪造）", None
            payload = json.loads(_b64d(body).decode("utf-8"))
        except Exception:
            return False, "授权码无法解析", None
        if int(payload.get("v") or 0) != _SCHEMA_VER:
            return False, "授权码版本不兼容，请联系管理员重新签发", None

        exp_d = _parse_date(payload.get("exp"))
        if not exp_d:
            return False, "授权码缺少有效期", None
        if exp_d < _today():
            return False, "授权已到期。请在「系统设置 → 订阅购买」续费，或联系管理员。", None

        name = str(payload.get("name") or "").strip()
        phone = str(payload.get("phone") or "").strip()
        if not name:
            return False, "授权码载荷无效", None

        # 名单校验：已登记则校验 code_id / 吊销；未登记则凭有效签名首次登记
        role = str(payload.get("role") or "user").strip() or "user"
        user = self.find_authorized_user(name, phone)
        if user is None:
            user = {
                "name": name,
                "phone": phone,
                "role": role,
                "company": "",
                "expire_date": exp_d.strftime("%Y-%m-%d"),
                "issue_date": _today().strftime("%Y-%m-%d"),
                "added_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "code_id": self._code_id(key),
                "code_fingerprint": self._code_fingerprint(key),
                "revoked": False,
                "bind_machine": bool(int(payload.get("bind") or 0)),
                "features": normalize_menu_features(payload.get("menus")),
                "activated_machine_id": "",
                "activated_at": "",
            }
            payload["_auto_register"] = True
        else:
            if user.get("revoked"):
                return False, "该授权已被管理员吊销，请联系管理员", None
            code_id = self._code_id(key)
            stored_id = str(user.get("code_id") or "")
            if stored_id and not hmac.compare_digest(stored_id, code_id):
                return False, "授权码已失效（管理员已重新发卡），请使用最新授权码", None
            user_exp = _parse_date(user.get("expire_date")) or exp_d
            if user_exp < _today():
                return False, "授权已到期。请在「系统设置 → 订阅购买」续费，或联系管理员。", None
            payload["_auto_register"] = False

        code_id = self._code_id(key)
        user_exp = _parse_date(user.get("expire_date")) or exp_d

        # 机器绑定
        if int(payload.get("bind") or 0) == 1 or user.get("bind_machine"):
            bound = str(user.get("activated_machine_id") or "")
            mid = self.get_machine_id()
            if bound and bound != mid:
                return False, "该授权码已绑定其它电脑，请联系管理员重新授权", None

        # 菜单权限：码内 menus 与名单 features 取规范结果（名单优先，防旧码扩大权限）
        code_menus = normalize_menu_features(payload.get("menus"))
        roster_menus = normalize_menu_features(user.get("features") or user.get("menus") or code_menus)
        if "all" in roster_menus:
            features = ["all"]
        elif "all" in code_menus:
            features = roster_menus if not payload.get("_auto_register") else ["all"]
        else:
            features = sorted(set(code_menus) & set(roster_menus)) or roster_menus

        payload["_user_record"] = user
        payload["_code_id"] = code_id
        payload["_expire_date"] = user_exp.strftime("%Y-%m-%d")
        payload["_features"] = features
        return True, "授权码有效", payload

    def activate_with_code(self, license_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """验码并激活本机。联网模式下必须先通过 DMS，再写本地。"""
        ok, msg, payload = self.verify_license_code(license_key)
        if not ok or not payload:
            return False, msg, None

        name = str(payload.get("name") or "").strip()
        phone = str(payload.get("phone") or "").strip()
        role = str(payload.get("role") or "user").strip() or "user"
        exp = str(payload.get("_expire_date") or payload.get("exp"))
        features = normalize_menu_features(payload.get("_features") or payload.get("menus"))
        if role == "admin":
            features = ["all"]
        mid = self.get_machine_id()
        now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        code_id = str(payload.get("_code_id") or self._code_id(license_key))

        # 1) 先联网：DMS 为权威源；失败则本机保持未激活
        net_payload: Optional[Dict[str, Any]] = None
        try:
            from services.dms_license_client import (
                activate_on_dms,
                invalidate_check_cache,
                is_local_dms,
                register_on_dms,
            )

            from app.version import APP_VERSION

            net_ok, net_msg, net_payload = activate_on_dms(license_key, mid, APP_VERSION)
            if (not net_ok) and is_local_dms() and "未在" in (net_msg or "") and "登记" in (net_msg or ""):
                ok_reg, reg_msg, _ = register_on_dms(license_key)
                if ok_reg:
                    net_ok, net_msg, net_payload = activate_on_dms(license_key, mid, APP_VERSION)
                else:
                    return False, f"联网激活失败：{net_msg}（本地补登记失败：{reg_msg}）", None
            if not net_ok:
                return False, f"联网激活失败：{net_msg}", None
            if net_payload and str(net_payload.get("expire_date") or "").strip():
                exp = str(net_payload.get("expire_date")).strip()
            if net_payload and net_payload.get("code_id"):
                code_id = str(net_payload.get("code_id"))
            if net_payload and isinstance(net_payload.get("features"), list):
                features = normalize_menu_features(net_payload.get("features"))
                if role == "admin":
                    features = ["all"]
            if net_payload and net_payload.get("role"):
                role = str(net_payload.get("role") or role)
            if net_payload and net_payload.get("name"):
                name = str(net_payload.get("name") or name)
            if net_payload and net_payload.get("phone") is not None:
                phone = str(net_payload.get("phone") or phone)
            invalidate_check_cache()
        except Exception as e:
            return False, f"联网激活异常：{e}", None

        # 2) 再写本地名单 + 激活态
        users = list(self.license_info.get("authorized_users") or [])
        replaced = False
        for i, u in enumerate(users):
            if not isinstance(u, dict):
                continue
            if str(u.get("name") or "").strip() == name and str(u.get("phone") or "").strip() == phone:
                u = dict(u)
                u["activated_machine_id"] = mid
                u["activated_at"] = now_s
                u["revoked"] = False
                u["features"] = list(features)
                u["role"] = role
                u["expire_date"] = exp
                u["code_id"] = code_id
                u["code_fingerprint"] = self._code_fingerprint(license_key)
                users[i] = u
                replaced = True
                break
        if not replaced:
            rec = dict(payload.get("_user_record") or {})
            rec.update(
                {
                    "name": name,
                    "phone": phone,
                    "activated_machine_id": mid,
                    "activated_at": now_s,
                    "revoked": False,
                    "features": list(features),
                    "role": role,
                    "expire_date": exp,
                    "code_id": code_id,
                    "code_fingerprint": self._code_fingerprint(license_key),
                }
            )
            users.append(rec)
        self.license_info["authorized_users"] = users

        self.license_info.update(
            {
                "is_licensed": True,
                "license_key": self._code_fingerprint(license_key),
                "expire_date": exp,
                "features": list(features),
                "user_name": name,
                "company": "",
                "phone": phone,
                "role": role,
                "machine_id": mid,
                "bound_machine_id": mid,
                "issue_date": _today().strftime("%Y-%m-%d"),
                "license_type": "admin" if role == "admin" else "professional",
                "activated_code_id": code_id,
                "activated_at": now_s,
                "last_online_ok_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "online_status": "active",
                "runtime_mode": "network",
                "plan_id": "all" if "all" in features else str(features[0] if features else ""),
            }
        )
        if not self.save_license():
            return False, "激活成功但保存失败", None

        # 回读磁盘，确认激活身份已落盘（防止旧实例/缓存导致“激活成功但重启变管理员”）
        try:
            self.load_license()
            disk_name = str(self.license_info.get("user_name") or "").strip()
            if name and disk_name and disk_name != name:
                return False, f"激活写入校验失败（磁盘仍为「{disk_name}」）", None
        except Exception as e:
            return False, f"激活后校验失败：{e}", None

        return True, "授权激活成功", {
            "name": name,
            "phone": phone,
            "role": role,
            "expire_date": exp,
            "features": list(features),
            "permissions": ["all"] if role == "admin" or "all" in features else list(features),
        }

    def validate_license_key(self, license_key: str) -> Tuple[bool, str]:
        """兼容旧接口：激活授权码。"""
        ok, msg, _ = self.activate_with_code(license_key)
        return ok, msg

    def generate_license_key(self, user_name, phone, days: int = 365, role: str = "user", menus=None):
        """兼容旧接口：签发授权码（不再偷偷激活本机）。"""
        ok, _msg, code = self.issue_license_code(
            user_name,
            phone or "",
            days=int(days or 365),
            role=role or "user",
            menus=menus,
        )
        return code if ok else None

    # ------------------------------------------------------------------ #
    # 状态查询
    # ------------------------------------------------------------------ #
    def _activation_still_valid(self) -> Tuple[bool, str]:
        now = time.time()
        memo = getattr(self, "_licensed_memo", None)
        if isinstance(memo, tuple) and len(memo) == 3 and (now - float(memo[0])) < 2.0:
            return bool(memo[1]), str(memo[2] or "")
        ok, msg = self._activation_still_valid_uncached()
        self._licensed_memo = (now, ok, msg)
        return ok, msg

    def _activation_still_valid_uncached(self) -> Tuple[bool, str]:
        if _dev_grant_all_enabled():
            return True, "ok"
        if not self.verify_store_integrity():
            return False, "授权数据完整性校验失败，可能已被窜改"
        if not self.license_info.get("is_licensed"):
            return False, "当前未授权"
        exp = _parse_date(self.license_info.get("expire_date"))
        if exp is None:
            return False, "授权缺少有效期"
        if exp < _today():
            return False, "授权已到期。请在「系统设置 → 订阅购买」续费，或联系管理员。"
        # 若有激活码记录，核对名单未吊销
        code_id = str(self.license_info.get("activated_code_id") or "")
        name = str(self.license_info.get("user_name") or "").strip()
        phone = str(self.license_info.get("phone") or "").strip()
        if name:
            user = self.find_authorized_user(name, phone)
            if user is None:
                return False, "当前用户不在授权名单中"
            if user.get("revoked"):
                return False, "授权已被管理员吊销，请联系管理员"
            if code_id and user.get("code_id") and not hmac.compare_digest(str(user.get("code_id")), code_id):
                return False, "授权码已更换，请使用新授权码重新登录"
            user_exp = _parse_date(user.get("expire_date"))
            if user_exp and user_exp < _today():
                return False, "授权已到期。请在「系统设置 → 订阅购买」续费，或联系管理员。"
            # 同步名单中的菜单权限（管理员改授权后即时生效）
            try:
                roster_feat = normalize_menu_features(user.get("features") or user.get("menus"))
                if self.license_info.get("role") == "admin":
                    roster_feat = ["all"]
                if list(self.license_info.get("features") or []) != list(roster_feat):
                    self.license_info["features"] = list(roster_feat)
                    self.save_license()
            except Exception:
                pass
        bound = str(self.license_info.get("bound_machine_id") or "")
        if bound and bound != self.get_machine_id():
            return False, "授权已绑定其它电脑"

        # DMS：UI 路径禁止同步 HTTP。用缓存；过期则后台刷新，本机按上次有效+宽限。
        try:
            from services.dms_license_client import (
                FAIL_STATUSES,
                apply_dms_identity,
                check_on_dms,
                peek_check_cache,
                within_grace,
            )

            code_id = str(self.license_info.get("activated_code_id") or "")
            if not code_id:
                return False, "缺少联网授权标识，请使用 TOA 运营台签发的授权码重新激活"
            mid = self.get_machine_id()
            peeked = peek_check_cache(code_id, mid)
            net_ok, _net_msg, payload = check_on_dms(code_id, mid, blocking=False)
            from_network = bool(peeked.get("fresh") and peeked.get("network_ok"))
            if net_ok and isinstance(payload, dict):
                status = str(payload.get("status") or "")
                if status in FAIL_STATUSES:
                    try:
                        apply_dms_identity(self.license_info, payload)
                    except Exception:
                        pass
                    self.license_info["is_licensed"] = False
                    self.license_info["online_status"] = status
                    try:
                        self.save_license()
                    except Exception:
                        pass
                    messages = {
                        "expired": "授权已到期。请在「系统设置 → 订阅购买」续费。",
                        "revoked": "授权已停用，无法登录",
                        "bound_elsewhere": "授权已绑定其它电脑，请联系管理员在运营宝换机解绑",
                        "unknown": "授权码已更换或未在 TOA 云服务登记，请从运营台获取新码",
                        "missing": "授权码已更换或未在 TOA 云服务登记，请从运营台获取新码",
                    }
                    return False, messages.get(status) or str(
                        payload.get("message") or "授权已失效，请联系管理员"
                    )
                if status == "active":
                    dirty = False
                    if self.license_info.get("online_status") != "active":
                        self.license_info["online_status"] = "active"
                        dirty = True
                    try:
                        if apply_dms_identity(self.license_info, payload):
                            dirty = True
                            uname = str(self.license_info.get("user_name") or "").strip()
                            uphone = str(self.license_info.get("phone") or "").strip()
                            users = list(self.license_info.get("authorized_users") or [])
                            for i, u in enumerate(users):
                                if not isinstance(u, dict):
                                    continue
                                if (
                                    str(u.get("name") or "").strip() == uname
                                    and str(u.get("phone") or "").strip() == uphone
                                ):
                                    u = dict(u)
                                    u["expire_date"] = self.license_info.get("expire_date")
                                    u["role"] = self.license_info.get("role")
                                    u["features"] = list(self.license_info.get("features") or [])
                                    u["revoked"] = False
                                    users[i] = u
                                    break
                            self.license_info["authorized_users"] = users
                    except Exception:
                        pass
                    if from_network:
                        last = str(self.license_info.get("last_online_ok_at") or "")
                        bump = True
                        try:
                            if last:
                                prev = datetime.datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
                                bump = (datetime.datetime.now() - prev).total_seconds() > 1800
                        except Exception:
                            bump = True
                        if bump:
                            self.license_info["last_online_ok_at"] = datetime.datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                            dirty = True
                    if dirty:
                        try:
                            self.save_license()
                        except Exception:
                            pass
                else:
                    return False, f"授权状态异常（{status or 'empty'}），请联系管理员"
            elif not net_ok:
                last_status = str(self.license_info.get("online_status") or "")
                if last_status in FAIL_STATUSES:
                    return False, "授权已失效（上次联网校验），无法登录"
                if last_status == "active" or within_grace(
                    str(self.license_info.get("last_online_ok_at") or "")
                ):
                    pass
                else:
                    return False, "需联网校验 DMS 授权，请连接网络后重试"
        except Exception as e:
            last_status = str(self.license_info.get("online_status") or "")
            try:
                from services.dms_license_client import FAIL_STATUSES, within_grace
            except Exception:
                FAIL_STATUSES = frozenset()
                within_grace = lambda *_a, **_k: False  # noqa: E731
            if last_status in FAIL_STATUSES:
                return False, f"授权已失效且联网校验异常：{e}"
            if last_status == "active":
                return True, "ok"
            if not within_grace(str(self.license_info.get("last_online_ok_at") or "")):
                return False, f"需联网校验 DMS 授权：{e}"

        return True, "ok"

    def is_licensed(self) -> bool:
        ok, _ = self._activation_still_valid()
        return ok

    def is_admin_user(self) -> bool:
        """当前会话是否为管理员（默认开放全部菜单与功能）。"""
        if _dev_grant_all_enabled():
            return True
        if not self.license_info:
            self.load_license()
        role = str(self.license_info.get("role") or "").strip().lower()
        if role == "admin":
            return True
        name = str(self.license_info.get("user_name") or "").strip()
        phone = str(self.license_info.get("phone") or "").strip()
        if name:
            user = self.find_authorized_user(name, phone)
            if user and str(user.get("role") or "").strip().lower() == "admin":
                return True
        try:
            from app.app_state import AppState

            st = AppState.get()
            if st.is_authenticated and str(getattr(st, "role", "") or "").strip().lower() == "admin":
                return True
        except Exception:
            pass
        return False

    def has_full_menu_access(self) -> bool:
        """全功能包 / 管理员：侧栏展示全部菜单（含 show:false 与 manifest 未开放项）。"""
        if self.is_admin_user():
            return True
        if not self.license_info:
            self.load_license()
        feats = normalize_menu_features(self.license_info.get("features") or [])
        if "all" in feats:
            return True
        plan = str(self.license_info.get("plan_id") or "").strip().lower()
        if plan in ("enterprise", "all"):
            return True
        return False

    def is_standalone_mode(self) -> bool:
        if not self.license_info:
            self.load_license()
        from services.runtime_mode import is_standalone_record

        if bool(self.license_info.get("is_licensed")):
            return False
        return is_standalone_record(self.license_info)

    def enter_standalone_mode(self) -> bool:
        """单机版：local_free 功能，不联网、不冒充完整授权。"""
        from services.feature_packs import expand_features
        from services.runtime_mode import LOCAL_FREE_PLAN, STANDALONE, standalone_display_name

        features = expand_features([LOCAL_FREE_PLAN])
        name = standalone_display_name()
        self.license_info.update(
            {
                "is_licensed": False,
                "runtime_mode": STANDALONE,
                "plan_id": LOCAL_FREE_PLAN,
                "license_type": STANDALONE,
                "license_key": "",
                "expire_date": None,
                "features": features,
                "user_name": name,
                "phone": "",
                "role": "user",
                "company": "",
                "bound_machine_id": "",
                "activated_code_id": "",
                "online_status": "",
                "last_online_ok_at": "",
            }
        )
        return self.save_license()

    def is_license_valid(self) -> bool:
        return self.is_licensed()

    def get_license_status_message(self) -> str:
        ok, msg = self._activation_still_valid()
        return "已授权" if ok else msg

    def has_feature_access(self, feature_name) -> bool:
        if _dev_grant_all_enabled() or self.is_admin_user() or self.has_full_menu_access():
            return True
        if not self.is_licensed():
            return False
        features = normalize_menu_features(self.license_info.get("features") or [])
        if "all" in features:
            return True
        name = str(feature_name or "").strip()
        if not name:
            return False
        if name in features:
            return True
        # 兼容按中文菜单名查询
        try:
            from services.menu_registry import get_menu_item_by_name, get_menu_item_by_id

            item = get_menu_item_by_id(name) or get_menu_item_by_name(name)
            if item and str(item.get("id") or "") in features:
                return True
        except Exception:
            pass
        return False

    def get_authorized_menu_ids(self) -> List[str]:
        """当前激活用户可用的菜单 id；含 all 时返回 ['all']。"""
        if _dev_grant_all_enabled() or self.is_admin_user() or self.has_full_menu_access():
            return ["all"]
        if not self.is_licensed():
            return []
        return normalize_menu_features(self.license_info.get("features") or [])

    def format_features_summary(self, features=None) -> str:
        if _dev_grant_all_enabled():
            return "全部菜单（开发默认）"
        feats = normalize_menu_features(features if features is not None else self.license_info.get("features"))
        if "all" in feats:
            return "全部菜单"
        if not feats:
            return "无菜单"
        names = []
        try:
            from services.menu_registry import get_menu_item_by_id

            for mid in feats:
                item = get_menu_item_by_id(mid)
                names.append(str((item or {}).get("name") or mid))
        except Exception:
            names = list(feats)
        if len(names) <= 3:
            return "、".join(names)
        return f"{'、'.join(names[:3])} 等{len(names)}项"

    def get_license_info(self) -> Dict[str, Any]:
        if not self.license_info:
            self.load_license()
        return dict(self.license_info)

    def get_validity_text(self) -> str:
        """主页/状态栏展示用。"""
        if _dev_grant_all_enabled():
            return "开发模式 · 已默认授权全部菜单"
        if self.is_standalone_mode():
            return "单机基础版 · 离线可用（完整版请用授权码激活）"
        ok, msg = self._activation_still_valid()
        if not ok:
            if msg and msg not in ("ok", "当前未授权"):
                return msg
            return "未授权 · 请输入授权码并联网激活"
        exp = str(self.license_info.get("expire_date") or "")
        days = self.get_remaining_days()
        name = str(self.license_info.get("user_name") or "").strip()
        who = f"{name} · " if name else ""
        online = ""
        try:
            if str(self.license_info.get("online_status") or "") == "active":
                online = " · 云服务已确认"
        except Exception:
            pass
        if days == float("inf"):
            return f"{who}产品有效期：永久{online}"
        return f"{who}有效期至 {exp}（剩余 {int(days)} 天）{online}"

    def get_remaining_days(self):
        if _dev_grant_all_enabled():
            return float("inf")
        if not self.license_info.get("is_licensed"):
            return 0
        expire_date = self.license_info.get("expire_date")
        if not expire_date:
            return 0
        try:
            expire_dt = datetime.datetime.strptime(str(expire_date)[:10], "%Y-%m-%d")
            remaining = (expire_dt.date() - _today()).days
            return max(0, remaining)
        except ValueError:
            return 0

    def deactivate_local(self) -> bool:
        """退出登录时清除本机激活态，保留名单。"""
        users = list(self.license_info.get("authorized_users") or [])
        self.license_info.update(
            {
                "is_licensed": False,
                "license_key": "",
                "expire_date": None,
                "features": [],
                "user_name": "",
                "phone": "",
                "role": "",
                "bound_machine_id": "",
                "activated_code_id": "",
                "activated_at": "",
                "license_type": "unlicensed",
                "issue_date": None,
                "online_status": "",
                "last_online_ok_at": "",
            }
        )
        self.license_info["authorized_users"] = users
        return self.save_license()

    # ------------------------------------------------------------------ #
    # 名单 CRUD
    # ------------------------------------------------------------------ #
    def remove_authorized_user(self, user_name, user_phone=None) -> bool:
        try:
            name = str(user_name or "").strip()
            phone = None if user_phone is None else str(user_phone or "").strip()
            authorized_users = self.license_info.get("authorized_users", [])
            filtered = []
            removed = False
            victim = None
            for user in authorized_users:
                if not isinstance(user, dict):
                    continue
                un = str(user.get("name") or "").strip()
                up = str(user.get("phone") or "").strip()
                matched = (up == phone) if phone else (un == name)
                if not matched:
                    filtered.append(user)
                    continue
                if self.is_protected_admin(user):
                    print("拒绝移除固定管理员账号（防锁死）")
                    return False
                victim = dict(user)
                removed = True
            if removed:
                self.license_info["authorized_users"] = filtered
                if (
                    str(self.license_info.get("user_name") or "").strip() == name
                    and (phone is None or str(self.license_info.get("phone") or "").strip() == phone)
                ):
                    self.license_info["is_licensed"] = False
                if not self.save_license():
                    return False
                ok, msg = self.sync_user_to_dms(
                    victim or {"name": name, "phone": phone or ""},
                    op="delete",
                    remark="终端删除",
                )
                if not ok:
                    print(f"本机已删除，但同步 DMS 删除失败：{msg}")
                return True
            return False
        except Exception as e:
            print(f"移除已授权用户失败: {e}")
            return False

    def revoke_authorized_user(self, user_name: str, user_phone: str = "") -> bool:
        user = self.find_authorized_user(user_name, user_phone)
        if not user:
            return False
        if self.is_protected_admin(user):
            print("拒绝停用固定管理员账号（防锁死）")
            return False
        users = list(self.license_info.get("authorized_users") or [])
        for i, u in enumerate(users):
            if u is user or (
                str(u.get("name") or "").strip() == (user_name or "").strip()
                and str(u.get("phone") or "").strip() == (user_phone or "").strip()
            ):
                u = dict(u)
                u["revoked"] = True
                users[i] = u
                break
        self.license_info["authorized_users"] = users
        if (
            str(self.license_info.get("user_name") or "").strip() == (user_name or "").strip()
            and str(self.license_info.get("phone") or "").strip() == (user_phone or "").strip()
        ):
            self.license_info["is_licensed"] = False
        if not self.save_license():
            return False
        rec = self.find_authorized_user(user_name, user_phone) or {"name": user_name, "phone": user_phone, "revoked": True}
        self.sync_user_to_dms(rec, op="revoke", remark="终端停用")
        return True

    def unbind_authorized_user(self, user_name: str, user_phone: str = "") -> Tuple[bool, str]:
        """清除机器绑定并同步 DMS，便于换机激活。"""
        user = self.find_authorized_user(user_name, user_phone)
        if not user:
            return False, "未找到该授权账号"
        if self.is_protected_admin(user):
            return False, "固定管理员账号不可解绑"
        rec = dict(user)
        rec["activated_machine_id"] = ""
        rec["activated_at"] = ""
        rec["updated_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        users = list(self.license_info.get("authorized_users") or [])
        for i, u in enumerate(users):
            if not isinstance(u, dict):
                continue
            if str(u.get("name") or "").strip() == (user_name or "").strip() and str(u.get("phone") or "").strip() == (
                user_phone or ""
            ).strip():
                users[i] = rec
                break
        self.license_info["authorized_users"] = users
        if not self.save_license():
            return False, "本机保存失败"
        ok, msg = self.sync_user_to_dms(rec, op="unbind", remark="终端解绑")
        if not ok:
            return False, f"本机已保存，但同步 DMS 失败：{msg}"
        return True, "已解绑并同步 DMS"

    def get_authorized_users(self) -> List[Dict[str, Any]]:
        return list(self.license_info.get("authorized_users") or [])

    def format_authorized_user(self, user: dict) -> str:
        if not isinstance(user, dict):
            return str(user)
        name = str(user.get("name") or "").strip() or "未命名"
        phone = str(user.get("phone") or "").strip()
        role = str(user.get("role") or "").strip()
        exp = str(user.get("expire_date") or "").strip() or "未发卡"
        revoked = bool(user.get("revoked"))
        fp = str(user.get("code_fingerprint") or "")
        base = f"{name}（{phone}）" if phone else name
        if role == "admin":
            base = f"{base} [管理员]"
            if self.is_protected_admin(user):
                base = f"{base} [固定]"
        status = "已吊销" if revoked else ("已发卡" if user.get("code_id") else "待发卡")
        menu_txt = self.format_features_summary(user.get("features") or user.get("menus"))
        extra = f" · 有效期 {exp} · {status} · {menu_txt}"
        if fp:
            extra += f" · {fp}"
        return base + extra

    def find_authorized_user(self, name: str, phone: str = ""):
        name = (name or "").strip()
        phone = (phone or "").strip()
        for user in self.get_authorized_users():
            if not isinstance(user, dict):
                continue
            if str(user.get("name") or "").strip() != name:
                continue
            stored_phone = str(user.get("phone") or "").strip()
            if not phone or not stored_phone or stored_phone == phone:
                return user
        return None

    def get_protected_admin(self) -> Optional[Dict[str, Any]]:
        """唯一不可清除的管理员：优先「管理员」占位，否则名单里第一条 admin。"""
        admins = [
            u
            for u in self.get_authorized_users()
            if isinstance(u, dict) and str(u.get("role") or "").strip().lower() == "admin"
        ]
        if not admins:
            return None
        for u in admins:
            name = str(u.get("name") or "").strip()
            phone = str(u.get("phone") or "").strip()
            if name in ("管理员", "admin") and phone == "12345678901":
                return u
        for u in admins:
            if str(u.get("name") or "").strip() in ("管理员", "admin"):
                return u
        return admins[0]

    def is_protected_admin(self, user: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(user, dict):
            return False
        prot = self.get_protected_admin()
        if not prot:
            return False
        return str(prot.get("name") or "").strip() == str(user.get("name") or "").strip() and str(
            prot.get("phone") or ""
        ).strip() == str(user.get("phone") or "").strip()

    def ensure_bootstrap_admin(self, name: str = "管理员", phone: str = "12345678901") -> bool:
        """仅开发环境自动写入空管理员占位；发版包禁止自动引导。"""
        try:
            users = self.license_info.get("authorized_users") or []
            if users:
                return True
            # 发版 / 正式安装：不得自动造管理员，必须用授权码激活
            allow = os.environ.get("TOA_ALLOW_BOOTSTRAP_ADMIN", "").strip() == "1"
            if not allow:
                try:
                    from services.runtime_paths import is_frozen

                    if is_frozen():
                        return False
                except Exception:
                    pass
                # 开发态默认也不自动造管理员，除非显式打开
                return False
            admin = {
                "name": name,
                "phone": phone,
                "role": "admin",
                "features": ["all"],
                "company": "系统管理员",
                "expire_date": "",
                "issue_date": "",
                "added_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "code_id": "",
                "code_fingerprint": "",
                "revoked": False,
                "bind_machine": False,
                "activated_machine_id": "",
                "activated_at": "",
            }
            self.license_info["authorized_users"] = [admin]
            return self.save_license()
        except Exception as e:
            print(f"写入默认管理员失败: {e}")
            return False

    def grant_admin_full_access(self):
        """开发急救：仅当 TOA_ALLOW_BOOTSTRAP_ADMIN=1 时可为管理员签发并激活。发版禁用。"""
        if os.environ.get("TOA_ALLOW_BOOTSTRAP_ADMIN", "").strip() != "1":
            return False, "已禁用本地绕过授权（需 TOA_ALLOW_BOOTSTRAP_ADMIN=1）", None
        try:
            from services.runtime_paths import is_frozen

            if is_frozen():
                return False, "发版包禁止本地绕过授权", None
        except Exception:
            pass
        self.ensure_bootstrap_admin()
        ok, msg, code = self.issue_license_code(
            "管理员", "12345678901", days=3650, role="admin", bind_machine=True
        )
        if ok and code:
            return self.activate_with_code(code)
        return False, msg, None


global_license_manager = LicenseManager()


def main():
    import sys

    if len(sys.argv) > 1:
        license_key = sys.argv[1]
        print(f"尝试使用授权码激活系统: {license_key}")
        success, message = global_license_manager.validate_license_key(license_key)
        print(("激活成功: " if success else "激活失败: ") + message)
        return
    print("已授权" if global_license_manager.is_licensed() else "未授权")
    print(f"机器ID: {global_license_manager.get_machine_id()}")
    print(f"状态: {global_license_manager.get_validity_text()}")


if __name__ == "__main__":
    main()
