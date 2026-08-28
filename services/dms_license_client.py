# -*- coding: utf-8 -*-
"""TOA 联网授权客户端。

目标：TOA 云服务（license.service_url）— 授权/试用/订单，与 DMS 无强绑定。
过渡：未配置 service_url 或不可达时 fallback dms_base_url（将删除）。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

# status → 终端必须失效（license_manager 共用）
FAIL_STATUSES = frozenset({"revoked", "expired", "bound_elsewhere", "unknown", "missing"})

_cache_lock = threading.Lock()
_check_cache: Dict[str, Any] = {
    "at": 0.0,
    "code_id": "",
    "machine_id": "",
    "network_ok": False,
    "payload": None,
    "error": "",
}


def _cfg() -> Dict[str, Any]:
    try:
        from services.config_service import get_license_config

        return get_license_config()
    except Exception:
        return {}


def license_service_url() -> str:
    """TOA 云服务展示用地址（与 license_api_base 同源）。"""
    return license_api_base()


def license_api_base() -> str:
    """授权 API 根路径，固定以 /api/toa-license 结尾（无尾斜杠）。"""
    cfg = _cfg()
    url = str(cfg.get("service_url") or "").strip().rstrip("/")
    if url:
        if "/api/toa-license" not in url:
            url = f"{url}/api/toa-license"
        return url
    return f"{dms_base_url().rstrip('/')}/api/toa-license"


def cloud_origin() -> str:
    """云服务站点 origin（用于版本 manifest、健康检查）。"""
    base = license_api_base()
    marker = "/api/toa-license"
    idx = base.find(marker)
    if idx > 0:
        return base[:idx].rstrip("/")
    return base.rstrip("/")


def dms_base_url() -> str:
    """过渡 fallback：旧 DMS 内嵌 toa-license API。"""
    cfg = _cfg()
    url = str(cfg.get("dms_base_url") or "").strip().rstrip("/")
    if url:
        return url
    return "https://dms.yczh.tech"


def is_local_license_service(url: str | None = None) -> bool:
    """本地/测试授权服务，允许激活时补登记（生产禁止）。"""
    u = (url or license_service_url()).lower()
    return any(x in u for x in ("127.0.0.1", "localhost", "[::1]"))


def is_local_dms(url: str | None = None) -> bool:
    """兼容旧名。"""
    return is_local_license_service(url)


def offline_grace_days() -> int:
    """仅用于断网宽限；过期/停用不受此保护。"""
    try:
        return max(0, int((_cfg().get("offline_grace_days") or 2)))
    except Exception:
        return 2


def check_cache_seconds() -> int:
    """联网成功结果的本地缓存秒数；失效类结果最多缓存 60s。"""
    try:
        minutes = int((_cfg().get("check_cache_minutes") or 5))
    except Exception:
        minutes = 5
    return max(30, minutes * 60)


def invalidate_check_cache() -> None:
    with _cache_lock:
        _check_cache["at"] = 0.0
        _check_cache["payload"] = None
        _check_cache["error"] = ""


def license_service_label(url: str | None = None) -> str:
    """用户可见的授权服务名称。"""
    return _service_label(url)


def _service_label(url: str | None = None) -> str:
    u = (url or license_api_base()).lower()
    if is_local_license_service(u):
        return "本地 TOA 云服务"
    if "dms.yczh" in u or "/dms" in u:
        return "DMS 授权服务（过渡）"
    return "TOA 云服务"


def _format_connect_error(exc: BaseException, url: str) -> str:
    """把 urlopen/WinError 译成可读原因，并带上实际地址。"""
    text = str(exc or "")
    low = text.lower()
    label = _service_label(url)
    local = is_local_license_service(url)
    if "10061" in text or "积极拒绝" in text or "refused" in low:
        if local:
            return (
                f"无法连接{label}（{url}）。"
                "请先启动本机 toa-cloud（默认 127.0.0.1:8090），"
                "或检查 config 中 license.service_url。"
            )
        return f"无法连接{label}（{url}），目标未在监听。"
    if "timed out" in low or "timeout" in low:
        return f"连接{label}超时（{url}）。"
    if "11001" in text or "getaddrinfo" in low or "name or service not known" in low:
        return f"无法解析{label}地址（{url}）。"
    return f"无法连接{label}（{url}）：{text}"


def activate_timeout_seconds() -> float:
    try:
        return max(5.0, float((_cfg().get("activate_timeout_seconds") or 15)))
    except Exception:
        return 15.0


def _post_json(action: str, body: dict, timeout: float | None = None) -> Tuple[bool, Dict[str, Any], str]:
    if timeout is None:
        timeout = activate_timeout_seconds()
    base = license_api_base()
    url = f"{base}/{str(action or '').strip().lstrip('/')}"
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:
                payload = {"raw": raw}
            if not isinstance(payload, dict):
                payload = {"data": payload}
            return True, payload, ""
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
            parsed = json.loads(err_body) if err_body else {}
            detail = str(parsed.get("detail") or err_body or e.reason)
        except Exception:
            detail = str(e.reason or e)
        return False, {}, detail or f"HTTP {e.code}"
    except Exception as e:
        return False, {}, _format_connect_error(e, url)


def cloud_health_check(timeout: float = 3.0) -> bool:
    """探测 TOA 云服务 /api/health（设置页短超时）。"""
    origin = cloud_origin()
    if not origin:
        return False
    try:
        import urllib.request

        req = urllib.request.Request(f"{origin}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=min(timeout, 3.0)) as resp:
            return resp.status == 200
    except Exception:
        return False


def activate_on_dms(license_key: str, machine_id: str, app_version: str = "") -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """联网激活：必须已在 TOA 云服务登记。"""
    invalidate_check_cache()
    ok, payload, err = _post_json(
        "activate",
        {
            "license_key": license_key,
            "machine_id": machine_id,
            "app_version": app_version or "",
        },
    )
    if not ok:
        return False, err or "联网激活失败", None
    status = str(payload.get("status") or "")
    if status != "active":
        return False, str(payload.get("message") or "授权未通过联网校验"), payload
    return True, "ok", payload


def register_on_dms(license_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """签发后必须登记到云服务，否则不算发出。"""
    ok, payload, err = _post_json(
        "register",
        {"license_key": license_key},
    )
    if not ok:
        return False, err or "同步到云服务失败", None
    return True, "ok", payload


def sync_roster_on_dms(envelope: dict, timeout: float = 10.0) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """终端增删改签名同步到云服务台账。"""
    ok, payload, err = _post_json("sync", envelope or {}, timeout=timeout)
    if not ok:
        return False, err or "同步到云服务失败", None
    return True, "ok", payload


def reconcile_roster_on_dms(envelope: dict, timeout: float = 10.0) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """以本机名单对账：清掉云服务里已不在名单中的非固定管理员。"""
    ok, payload, err = _post_json("reconcile", envelope or {}, timeout=timeout)
    if not ok:
        return False, err or "对账失败", None
    return True, "ok", payload


_FAIL_CACHE_SECONDS = 8.0
_UI_CHECK_TIMEOUT = 2.5
_bg_refresh_lock = threading.Lock()
_bg_refresh_running = False


def peek_check_cache(code_id: str = "", machine_id: str = "") -> Dict[str, Any]:
    """只读缓存，不访问网络。"""
    cid = (code_id or "").strip()
    mid = (machine_id or "").strip()
    now = time.time()
    with _cache_lock:
        same = (not cid and not mid) or (
            _check_cache.get("code_id") == cid and _check_cache.get("machine_id") == mid
        )
        age = now - float(_check_cache.get("at") or 0)
        ttl = check_cache_seconds()
        return {
            "hit": bool(same and _check_cache.get("at")),
            "fresh": bool(same and age < ttl and _check_cache.get("at")),
            "age": age,
            "network_ok": bool(_check_cache.get("network_ok")),
            "payload": _check_cache.get("payload"),
            "error": str(_check_cache.get("error") or ""),
        }


def check_on_dms(
    code_id: str,
    machine_id: str,
    license_key: str = "",
    *,
    force: bool = False,
    blocking: bool = True,
    timeout: Optional[float] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    返回 (network_ok, message, payload)。
    network_ok=False 表示网络/服务异常（不是授权被停用）。
    blocking=False：只用缓存，缓存过期则后台刷新，UI 线程不得走 HTTP。
    """
    cid = (code_id or "").strip()
    mid = (machine_id or "").strip()
    now = time.time()
    ttl = check_cache_seconds()
    wait = float(timeout) if timeout is not None else _UI_CHECK_TIMEOUT

    if not force:
        stale_payload = None
        with _cache_lock:
            same = _check_cache.get("code_id") == cid and _check_cache.get("machine_id") == mid
            age = now - float(_check_cache.get("at") or 0)
            cached_payload = _check_cache.get("payload")
            network_ok = bool(_check_cache.get("network_ok"))
            if same and age < ttl:
                if network_ok and isinstance(cached_payload, dict):
                    status = str(cached_payload.get("status") or "")
                    if not (status in FAIL_STATUSES and age > 60):
                        return True, str(cached_payload.get("message") or "ok"), cached_payload
                if (not network_ok) and age < _FAIL_CACHE_SECONDS:
                    return False, str(_check_cache.get("error") or "联网校验失败"), None
            if same and isinstance(cached_payload, dict):
                stale_payload = cached_payload
        if not blocking:
            _spawn_bg_check(cid, mid, license_key)
            if stale_payload is not None:
                return True, str(stale_payload.get("message") or "cached"), stale_payload
            return False, "pending", None

    ok, payload, err = _post_json(
        "check",
        {
            "code_id": cid,
            "license_key": license_key or "",
            "machine_id": mid,
        },
        timeout=wait,
    )
    with _cache_lock:
        _check_cache["at"] = now
        _check_cache["code_id"] = cid
        _check_cache["machine_id"] = mid
        _check_cache["network_ok"] = bool(ok)
        _check_cache["payload"] = payload if ok else None
        _check_cache["error"] = "" if ok else (err or "")
    if not ok:
        return False, err or "联网校验失败", None
    return True, str(payload.get("message") or "ok"), payload


def _spawn_bg_check(code_id: str, machine_id: str, license_key: str = "") -> None:
    global _bg_refresh_running
    with _bg_refresh_lock:
        if _bg_refresh_running:
            return
        _bg_refresh_running = True

    def _run():
        global _bg_refresh_running
        try:
            check_on_dms(code_id, machine_id, license_key, force=True, blocking=True, timeout=4.0)
        except Exception:
            pass
        finally:
            with _bg_refresh_lock:
                _bg_refresh_running = False

    threading.Thread(target=_run, name="toa-cloud-check", daemon=True).start()


def within_grace(last_ok_at: str, grace_days: Optional[int] = None) -> bool:
    days = offline_grace_days() if grace_days is None else grace_days
    if days <= 0:
        return False
    if not last_ok_at:
        return False
    try:
        ts = datetime.fromisoformat(str(last_ok_at).replace("Z", "+00:00"))
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
    except Exception:
        try:
            ts = datetime.strptime(str(last_ok_at)[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False
    return datetime.now() - ts <= timedelta(days=days)


def apply_dms_identity(local: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """把 DMS 返回的姓名/手机/到期/角色写回本地，保持信息一致。返回是否有变更。"""
    if not isinstance(local, dict) or not isinstance(payload, dict):
        return False
    changed = False
    mapping = (
        ("expire_date", "expire_date"),
        ("user_name", "name"),
        ("phone", "phone"),
        ("role", "role"),
    )
    for local_key, remote_key in mapping:
        if payload.get(remote_key) is None:
            continue
        new_v = str(payload.get(remote_key) or "")
        if local_key != "phone":
            new_v = new_v.strip()
        old_v = str(local.get(local_key) or "")
        if new_v != "" and new_v != old_v:
            local[local_key] = new_v
            changed = True
    if isinstance(payload.get("features"), list):
        feat = list(payload.get("features") or [])
        if str(local.get("role") or "") == "admin":
            feat = ["all"]
        if list(local.get("features") or []) != feat:
            local["features"] = feat
            changed = True
    return changed


# 新名别名（逐步替换 dms_* 调用方）
activate_on_cloud = activate_on_dms
register_on_cloud = register_on_dms
sync_roster_on_cloud = sync_roster_on_dms
reconcile_roster_on_cloud = reconcile_roster_on_dms
check_on_cloud = check_on_dms
apply_cloud_identity = apply_dms_identity
