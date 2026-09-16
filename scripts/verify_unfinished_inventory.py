# -*- coding: utf-8 -*-
"""一次性核实：manifest 状态 vs 菜单 show vs 页面文件 vs MIGRATED_MODULES。"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    man = yaml.safe_load((ROOT / "config/migration_manifest.yml").read_text(encoding="utf-8"))
    mods = man.get("modules") or {}
    app = yaml.safe_load((ROOT / "config/app.yml").read_text(encoding="utf-8"))

    menu_items = ((app.get("menu") or {}).get("menu_items")) or []
    menu = {
        str(i["id"]): i
        for i in menu_items
        if isinstance(i, dict) and i.get("id") is not None
    }
    text = (ROOT / "services/menu_registry.py").read_text(encoding="utf-8")
    # 取到配对的大括号
    start = text.find("MIGRATED_MODULES")
    brace = text.find("{", start)
    depth = 0
    end = brace
    for i, ch in enumerate(text[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    migrated = set(re.findall(r"['\"]([a-z0-9_]+)['\"]\s*:", text[brace : end + 1]))

    # intentional no sidebar
    no_menu_ok = {"screenshot_translate", "__about__"}

    print("=== 计数 ===")
    from collections import Counter

    c = Counter(v.get("status") for v in mods.values())
    print(dict(c))
    print(f"menu_items={len(menu)} migrated={len(migrated)}")

    issues = []
    print("\n=== 异常（需改口径或配置）===")
    for mid, mdef in sorted(mods.items()):
        st = mdef.get("status")
        mi = menu.get(mid)
        show = None if not mi else mi.get("show")
        path = None if not mi else mi.get("module_path")
        page_ok = None
        if path:
            parts = path.split(".")
            cand = ROOT.joinpath(*parts[:-1], parts[-1] + ".py")
            page_ok = cand.exists()

        if st in ("Hold", "stub") and show is True:
            issues.append((mid, f"{st} 但菜单 show:true → 应隐藏或改状态"))
        if st == "done" and show is False and mid not in no_menu_ok:
            issues.append((mid, "done 但 show:false（可能故意）"))
        if mid not in menu and mid not in no_menu_ok and st not in ("missing",):
            # missing may hang elsewhere
            if st == "mvp":
                issues.append((mid, "mvp 无 menu_items（audit 会失败）"))
        if path and page_ok is False:
            issues.append((mid, f"module_path 文件不存在: {path}"))
        if mi and mid not in migrated and mid != "__about__":
            issues.append((mid, "有菜单但未入 MIGRATED_MODULES"))

    # special: screenshot_translate
    st = mods.get("screenshot_translate", {}).get("status")
    if st == "mvp" and "screenshot_translate" not in menu:
        issues.append(
            (
                "screenshot_translate",
                "故意无侧栏（挂截图工具栏）；audit_migration 已豁免 menu/storage",
            )
        )

    for mid, msg in issues:
        print(f"- {mid}: {msg}")

    print("\n=== 未完成清单核实（非 done）===")
    for st in ("missing", "stub", "Hold", "mvp"):
        rows = [(k, v) for k, v in mods.items() if v.get("status") == st]
        print(f"\n## {st} × {len(rows)}")
        for mid, v in sorted(rows):
            mi = menu.get(mid)
            show = "—" if not mi else ("开" if mi.get("show") else "隐")
            gaps = [
                g
                for g in (v.get("gaps") or [])
                if g
                and "已剔除" not in str(g)
                and "（暂停）" not in str(g)
                and not str(g).strip().startswith("#")
            ]
            gap_n = len(gaps)
            print(f"  {mid:28} 菜单:{show:1}  gaps:{gap_n}")

    print("\n=== 关键路径冒烟 ===")
    checks = [
        ("email_client", "modules/email_client/email_client_page.py"),
        ("services/mail", "services/mail/imap_sync.py"),
        ("screenshot_translate", "services/screenshot_translate.py"),
        ("verify_email", "scripts/verify_email_client_mvp.py"),
        ("verify_clipboard", "scripts/verify_clipboard_history.py"),
        ("verify_screenshot_tr", "scripts/verify_screenshot_translate.py"),
    ]
    for name, rel in checks:
        ok = (ROOT / rel).exists()
        print(f"  {'OK' if ok else 'MISSING'}  {rel}")

    print("\n=== 与专家组 Hold 对照 ===")
    expect_hidden = [
        "pomodoro",
        "image_adjust",
        "image_creator",
        "comfyui_web",
        "engine_host_hub",
        "generic_generator",
        "email_client",
        "excel_cleaner",
    ]
    for mid in expect_hidden:
        mi = menu.get(mid)
        st = mods.get(mid, {}).get("status")
        show = None if not mi else mi.get("show")
        ok = show is False or show is None
        mark = "OK" if ok else "FAIL应隐藏"
        print(f"  {mark}  {mid:24} status={st} show={show}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
