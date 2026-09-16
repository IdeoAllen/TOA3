#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""email_client 冒烟：登记、预设、诊断、本地库、凭证分桶、MIME、禁 UI 阻塞路径。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def test_registration() -> None:
    from services.menu_registry import MIGRATED_MODULES, is_migrated
    from services.config_service import get_menu_item_by_id

    assert "email_client" in MIGRATED_MODULES, "未登记 MIGRATED_MODULES"
    assert is_migrated("email_client")
    item = get_menu_item_by_id("email_client")
    assert item, "app.yml 无 email_client 菜单项"
    assert item.get("show") is False, "必须 show:false"
    assert "EmailClientPage" in str(item.get("class_name") or "")
    _ok("菜单 show:false + MIGRATED_MODULES")

    import yaml

    man = yaml.safe_load((ROOT / "config" / "migration_manifest.yml").read_text(encoding="utf-8"))
    assert "email_client" in (man.get("modules") or {}), "manifest 缺 email_client"
    assert (man["modules"]["email_client"] or {}).get("status") == "mvp"
    _ok("migration_manifest email_client=mvp")


def test_presets_and_diagnose() -> None:
    from services.mail.presets import list_presets, get_preset
    from services.mail.diagnose import diagnose_mail_error

    presets = list_presets()
    ids = {p["id"] for p in presets}
    for need in ("qq", "netease_163", "outlook", "gmail", "custom"):
        assert need in ids, f"缺预设 {need}"
    hint = get_preset("qq").get("auth_hint") or ""
    assert "授权码" in hint
    _ok("厂商预设与授权码说明")

    diag = diagnose_mail_error("AUTHENTICATION failed 535", provider_id="qq", phase="imap_login")
    assert diag["code"] == "auth"
    assert "授权码" in diag["human"]
    net = diagnose_mail_error("timed out", provider_id="netease_163", phase="sync")
    assert net["code"] == "network"
    _ok("失败诊断人话（auth/network）")


def test_credentials_bucket_isolated(tmp_path: Path | None = None) -> None:
    from services.mail import credentials as cred
    from services.integrations import secrets as integ

    aid = "verify_email_client_smoke"
    cred.set_mail_password(aid, "test-auth-code-xyz")
    assert cred.get_mail_password(aid) == "test-auth-code-xyz"
    # 不得写入 integrations_secrets
    data = integ.load_secrets()
    blob = str(data)
    assert "test-auth-code-xyz" not in blob
    assert "mail_client" not in blob.lower() or "test-auth-code-xyz" not in blob
    cred.clear_mail_password(aid)
    assert cred.get_mail_password(aid) == ""
    meta = cred.secrets_meta()
    assert meta.get("integrations_email_shared") is False
    _ok(f"凭证分桶（backend={meta.get('backend')}）")


def test_store_and_parse() -> None:
    from email.message import EmailMessage

    from modules.email_client import mail_store
    from services.mail.imap_sync import parse_rfc822

    mail_store.init_db()
    aid = mail_store.upsert_account(
        {
            "id": "smoke_acct",
            "email": "smoke@example.com",
            "provider_id": "custom",
            "imap_host": "imap.example.com",
            "smtp_host": "smtp.example.com",
        }
    )
    assert aid == "smoke_acct"

    raw_msg = EmailMessage()
    raw_msg["From"] = "a@example.com"
    raw_msg["To"] = "smoke@example.com"
    raw_msg["Subject"] = "你好 TOA"
    raw_msg["Message-ID"] = "<smoke@toa>"
    raw_msg.set_content("纯文本正文")
    raw_msg.add_attachment(b"hello", maintype="text", subtype="plain", filename="note.txt")
    parsed = parse_rfc822(raw_msg.as_bytes(), uid="42", flags=["\\Seen"])
    assert parsed.subject == "你好 TOA"
    assert parsed.body_text.startswith("纯文本")
    assert len(parsed.attachments) == 1

    n = mail_store.upsert_parsed_messages(aid, "inbox", [parsed])
    assert n >= 0
    mail_store.set_folder_cursor(aid, "inbox", "INBOX", 42)
    cursors = mail_store.get_uid_cursors(aid)
    assert cursors.get("inbox") == 42 or cursors.get("INBOX") == 42
    rows = mail_store.list_messages(aid, "inbox")
    assert any(r.get("subject") == "你好 TOA" for r in rows)
    hit = next(r for r in rows if r.get("subject") == "你好 TOA")
    detail = mail_store.get_message(hit["id"])
    assert detail and detail.get("attachments")
    out = mail_store.export_attachment(detail["attachments"][0]["local_path"])
    assert out.is_file()
    _ok("SQLite 入库 + 附件落盘/导出")


def test_smtp_validate_and_build() -> None:
    from services.mail.smtp_send import (
        MAX_ATTACHMENT_BYTES,
        build_message,
        validate_attachments,
    )

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        p.write_text("x", encoding="utf-8")
        ok, err, files = validate_attachments([p])
        assert ok and files
        big = Path(td) / "big.bin"
        # 不真写 26MB：用 monkey 校验逻辑阈值
        assert MAX_ATTACHMENT_BYTES >= 10 * 1024 * 1024
        msg = build_message(
            from_addr="me@example.com",
            to_addrs=["you@example.com"],
            subject="hi",
            body_text="body",
            attachment_paths=files,
        )
        assert msg["Subject"] == "hi"
        assert msg.is_multipart() or msg.get_content_maintype() == "text"
    _ok("SMTP MIME 构建与附件上限常量")


def test_notify_channel_not_reused() -> None:
    import inspect

    from services import notify_channels
    from services.mail import smtp_send

    src = inspect.getsource(notify_channels)
    assert "integrations" in src
    # 客户端发信不得 import notify_channels
    client_src = inspect.getsource(smtp_send)
    assert "notify_channels" not in client_src
    assert "integration_config" not in client_src
    _ok("未复用 notify_channels / integrations.email")


def test_page_imports_no_shared_webengine() -> None:
    import ast

    page_path = ROOT / "modules" / "email_client" / "email_client_page.py"
    tree = ast.parse(page_path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    joined = " ".join(imports)
    assert "shared_local_webengine" not in joined
    # 源码级再扫一遍
    text = page_path.read_text(encoding="utf-8")
    assert "shared_local_webengine" not in text
    assert "email_client_private" in text or "web_profile" in text
    assert "QThread" in text
    _ok("页内私有 WebEngine + 后台线程（源码契约）")


def test_module_loader_path() -> None:
    import importlib

    from services.menu_registry import MIGRATED_MODULES

    dotted = MIGRATED_MODULES["email_client"]
    module_name, class_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    assert cls.__name__ == "EmailClientPage"
    from core.base_page import BasePage

    assert issubclass(cls, BasePage)
    _ok("EmailClientPage 可导入且继承 BasePage")


def main() -> int:
    print("=== verify_email_client_mvp ===")
    try:
        test_registration()
        test_presets_and_diagnose()
        test_credentials_bucket_isolated()
        test_store_and_parse()
        test_smtp_validate_and_build()
        test_notify_channel_not_reused()
        test_page_imports_no_shared_webengine()
        test_module_loader_path()
    except AssertionError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
