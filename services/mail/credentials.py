# -*- coding: utf-8 -*-
"""邮箱客户端凭证桶（A10.5 · 与 integrations_secrets / Harness 分轨）。

优先 Windows Credential Manager / keyring；否则 DPAPI 保护本地文件。
禁止写入 config yaml / integrations.email。
"""
from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path
from typing import Any

from services.config_service import project_root

logger = logging.getLogger("TOA3.mail.credentials")

_SERVICE = "TOA3.mail_client"
_BUCKET_FILE = "mail_client_secrets.bin"


def _bucket_path() -> Path:
    path = project_root() / "data" / "user" / _BUCKET_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _account_key(account_id: str) -> str:
    return f"account:{str(account_id or '').strip()}"


def _try_keyring_get(account_id: str) -> str | None:
    try:
        import keyring  # type: ignore

        val = keyring.get_password(_SERVICE, _account_key(account_id))
        return str(val) if val else None
    except Exception:
        return None


def _try_keyring_set(account_id: str, password: str) -> bool:
    try:
        import keyring  # type: ignore

        if password:
            keyring.set_password(_SERVICE, _account_key(account_id), password)
        else:
            try:
                keyring.delete_password(_SERVICE, _account_key(account_id))
            except Exception:
                pass
        return True
    except Exception:
        return False


def _dpapi_protect(raw: bytes) -> bytes:
    if sys.platform != "win32":
        raise OSError("DPAPI only on Windows")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = DATA_BLOB(len(raw), ctypes.create_string_buffer(raw, len(raw)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "TOA3 mail",
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(protected: bytes) -> bytes:
    if sys.platform != "win32":
        raise OSError("DPAPI only on Windows")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = DATA_BLOB(len(protected), ctypes.create_string_buffer(protected, len(protected)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _load_file_bucket() -> dict[str, str]:
    path = _bucket_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_bytes()
        if sys.platform == "win32":
            plain = _dpapi_unprotect(raw)
        else:
            plain = base64.urlsafe_b64decode(raw)
        data = json.loads(plain.decode("utf-8"))
        return {str(k): str(v) for k, v in (data or {}).items() if v}
    except Exception:
        logger.debug("load mail secrets bucket failed", exc_info=True)
        return {}


def _save_file_bucket(data: dict[str, str]) -> None:
    path = _bucket_path()
    plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if sys.platform == "win32":
        blob = _dpapi_protect(plain)
    else:
        blob = base64.urlsafe_b64encode(plain)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob)
    tmp.replace(path)


def get_mail_password(account_id: str) -> str:
    aid = str(account_id or "").strip()
    if not aid:
        return ""
    via_keyring = _try_keyring_get(aid)
    if via_keyring is not None:
        return via_keyring.strip()
    return str(_load_file_bucket().get(_account_key(aid)) or "").strip()


def set_mail_password(account_id: str, password: str) -> None:
    aid = str(account_id or "").strip()
    if not aid:
        raise ValueError("account_id required")
    pwd = str(password or "").strip()
    if _try_keyring_set(aid, pwd):
        # 清理文件桶残留
        bucket = _load_file_bucket()
        key = _account_key(aid)
        if key in bucket:
            bucket.pop(key, None)
            _save_file_bucket(bucket)
        return
    bucket = _load_file_bucket()
    key = _account_key(aid)
    if pwd:
        bucket[key] = pwd
    else:
        bucket.pop(key, None)
    _save_file_bucket(bucket)


def clear_mail_password(account_id: str) -> None:
    set_mail_password(account_id, "")


def credential_backend_label() -> str:
    """供诊断展示：当前凭证落点。"""
    try:
        import keyring  # type: ignore

        _ = keyring.get_keyring()
        return "OS keyring"
    except Exception:
        pass
    if sys.platform == "win32":
        return "Windows DPAPI 本地桶"
    return "本地受控文件桶"


def secrets_meta() -> dict[str, Any]:
    return {
        "service": _SERVICE,
        "bucket_file": _BUCKET_FILE,
        "backend": credential_backend_label(),
        "integrations_email_shared": False,
    }
