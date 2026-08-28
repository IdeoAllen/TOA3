# -*- coding: utf-8 -*-
"""TOA 云服务 · 产品方案订阅与订单客户端（pack_id 为兼容别名 = plan_id）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Tuple

from services.dms_license_client import _format_connect_error, cloud_origin


def commerce_api_base() -> str:
    origin = cloud_origin()
    if not origin:
        return ""
    return f"{origin.rstrip('/')}/api/toa"


def _get_json(path: str, *, query: dict | None = None, timeout: float = 12.0) -> Tuple[bool, dict, str]:
    base = commerce_api_base()
    if not base:
        return False, {}, "未配置 TOA 云服务地址"
    url = f"{base}/{path.lstrip('/')}"
    if query:
        qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        if qs:
            url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return True, data if isinstance(data, dict) else {"data": data}, ""
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


def _post_json(path: str, body: dict, *, timeout: float = 15.0) -> Tuple[bool, dict, str]:
    base = commerce_api_base()
    if not base:
        return False, {}, "未配置 TOA 云服务地址"
    url = f"{base}/{path.lstrip('/')}"
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
            payload = json.loads(raw) if raw else {}
            return True, payload if isinstance(payload, dict) else {"data": payload}, ""
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


def list_sellable_packs() -> Tuple[bool, list[dict], dict, str]:
    ok, data, err = _get_json("plans", query={"sellable": "true"})
    if not ok:
        ok, data, err = _get_json("packs", query={"sellable": "true"})
    if not ok:
        return False, [], {}, err
    packs = data.get("plans") or data.get("packs") or []
    commerce = data.get("commerce") or {}
    return True, packs if isinstance(packs, list) else [], commerce, ""


def list_sellable_plans() -> Tuple[bool, list[dict], dict, str]:
    """产品方案列表（与 list_sellable_packs 同源）。"""
    return list_sellable_packs()


def create_order(
    *,
    pack_id: str = "",
    plan_id: str = "",
    customer_name: str,
    phone: str,
    machine_id: str = "",
    license_days: int | None = None,
) -> Tuple[bool, dict, str]:
    pid = str(plan_id or pack_id or "").strip()
    body: dict[str, Any] = {
        "plan_id": pid,
        "pack_id": pid,
        "customer_name": customer_name,
        "phone": phone,
        "machine_id": machine_id,
        "remark": "TOA3 终端订阅",
    }
    if license_days is not None:
        body["license_days"] = license_days
    ok, data, err = _post_json("orders", body)
    return ok, data, err


def pay_order(*, order_no: str, phone: str, machine_id: str = "") -> Tuple[bool, dict, str]:
    ok, data, err = _post_json(
        f"orders/by-no/{urllib.parse.quote(order_no)}/pay",
        {"phone": phone, "machine_id": machine_id},
    )
    return ok, data, err


def order_status(*, order_no: str, phone: str, include_key: bool = False) -> Tuple[bool, dict, str]:
    ok, data, err = _get_json(
        f"orders/by-no/{urllib.parse.quote(order_no)}",
        query={"phone": phone, "include_key": "true" if include_key else "false"},
    )
    return ok, data, err


def upgrade_from_order(*, order_no: str, phone: str, machine_id: str = "") -> Tuple[bool, dict, str]:
    """已支付订单拉取授权码（Portal 支付回跳 / 轮询后激活）。"""
    from services.dms_license_client import _post_json, license_api_base

    base = license_api_base()
    url = f"{base.rstrip('/')}/upgrade"
    data = json.dumps(
        {"order_no": order_no, "phone": phone, "machine_id": machine_id},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw else {}
            return True, payload if isinstance(payload, dict) else {"data": payload}, ""
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
