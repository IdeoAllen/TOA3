# -*- coding: utf-8 -*-
"""引擎管家自测：登记 / 目录 / Comfy 同构 / 切页 / 生命周期只读路径。"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def test_registry() -> None:
    from services.menu_registry import MIGRATED_MODULES, all_menu_items, is_migrated

    assert "engine_host_hub" in MIGRATED_MODULES
    assert is_migrated("engine_host_hub")
    items = {i.get("id"): i for i in all_menu_items()}
    hub = items.get("engine_host_hub")
    assert hub is not None, "menu item engine_host_hub must remain registered"
    # 主理人裁定 Hold：侧栏关闭，代码保留
    assert hub.get("show") is False, "engine_host_hub must stay hidden until 无感方案就绪"
    assert hub.get("group") == "engines"


def test_catalog() -> None:
    from services.engine_host.catalog import list_catalog_entries, status_badge

    entries = list_catalog_entries()
    assert len(entries) >= 3
    ids = [e.engine_id for e in entries]
    assert ids[0] == "harness_agent", "Harness should be first"
    assert "comfyui_web" in ids
    assert not any(i.startswith("demo_") for i in ids)
    for e in entries:
        badge = status_badge(e)
        assert badge in ("未装", "已停", "运行中", "—"), badge


def test_lifecycle_readonly() -> None:
    from services.engine_host.lifecycle import backup_dir, log_path_for, open_log

    d = backup_dir()
    assert d.is_dir()
    for eid in ("open_pencil", "drawio_web", "comfyui_web", "harness_agent"):
        ok, msg, path = open_log(eid)
        assert ok, f"{eid}: {msg}"
        assert path is not None
        # 路径应可解析
        assert path.exists() or path.parent.exists()
        lp = log_path_for(eid)
        assert lp is not None


def test_comfy_inheritance() -> None:
    from modules.engine_host_hub.hub_local_web_host import HubLocalWebHost
    from modules.local_web_host.local_web_host_page import LocalWebHostPage

    assert issubclass(HubLocalWebHost, LocalWebHostPage)


def test_ui_smoke() -> None:
    from PySide6.QtWidgets import QApplication, QStackedWidget

    app = QApplication.instance() or QApplication(sys.argv)

    from modules.engine_host_hub.engine_host_hub_page import EngineHostHubPage
    from modules.engine_host_hub.hub_harness_host import HubHarnessHost
    from modules.engine_host_hub.hub_local_web_host import HubLocalWebHost
    from services.engine_host.catalog import list_catalog_entries

    page = EngineHostHubPage()
    assert page.page_id == "engine_host_hub"
    assert isinstance(page._stack, QStackedWidget)
    assert page._list.count() == len(list_catalog_entries())

    seen: list[str] = []
    for row in range(page._list.count()):
        page._list.setCurrentRow(row)
        app.processEvents()
        eid = page._current_id
        assert eid, f"row {row} no current"
        seen.append(eid)
        host = page._hosts.get(eid)
        assert host is not None
        assert page._stack.currentWidget() is host
        if eid == "harness_agent":
            assert isinstance(host, HubHarnessHost)
        else:
            assert isinstance(host, HubLocalWebHost)
            assert host.page_id == "engine_host_hub"
            assert host.engine_id == eid
            assert hasattr(host, "_btn_open_bench")
            texts = [a.text() for a in host._more_menu.actions() if a.text()]
            for need in ("打开日志", "一键修复", "版本备份", "一键卸载"):
                assert any(need in t for t in texts), f"{eid} missing {need}: {texts}"

        if hasattr(host, "on_enter"):
            host.on_enter()
        app.processEvents()
        if hasattr(host, "soft_leave"):
            host.soft_leave()
        app.processEvents()

    # 切到非首项后 on_enter 刷新目录，应保持选中
    if page._list.count() >= 2:
        page._list.setCurrentRow(1)
        app.processEvents()
        keep = page._current_id
        page.on_enter()
        app.processEvents()
        assert page._current_id == keep, f"on_enter reset selection {keep} -> {page._current_id}"

    # 仅一个 Host 可见于 stack current
    assert page._stack.count() == 1 + len(seen)  # placeholder + hosts
    page.on_leave()
    app.processEvents()
    page.close()
    page.deleteLater()
    app.processEvents()


def test_uninstall_clear_registration_only() -> None:
    """不删文件：清除不存在的假根登记不应抛错。"""
    from services.engine_host.lifecycle import uninstall_engine

    ok, msg = uninstall_engine("__nonexistent_engine_xyz__", delete_files=False)
    # 未知引擎走 local_web 路径：stop 无害，清 roots 无害
    assert ok, msg


def test_ocp_old_pages_untouched_import() -> None:
    """旧引擎页仍可导入（开闭：未删未改注册）。"""
    from modules.comfyui_web.comfyui_web_page import ComfyUiWebPage
    from modules.drawio_web.drawio_web_page import DrawioWebPage
    from modules.harness_agent.harness_agent_page import HarnessAgentPage
    from modules.open_pencil.open_pencil_page import OpenPencilPage

    assert ComfyUiWebPage.engine_id == "comfyui_web"
    assert DrawioWebPage.engine_id == "drawio_web"
    assert OpenPencilPage.engine_id == "open_pencil"
    assert HarnessAgentPage.page_id == "harness_agent"


def test_no_stylesheet_in_hub() -> None:
    root = ROOT / "modules" / "engine_host_hub"
    for p in root.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "setStyleSheet" not in text, f"{p.name} uses setStyleSheet"


def test_shell_can_ensure_page() -> None:
    """不启完整壳：module_loader 路径可解析。"""
    from services.menu_registry import MIGRATED_MODULES

    path = MIGRATED_MODULES["engine_host_hub"]
    mod_path, _, cls_name = path.rpartition(".")
    import importlib

    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    assert cls.page_id == "engine_host_hub"


def main() -> int:
    tests = [
        ("registry", test_registry),
        ("catalog", test_catalog),
        ("lifecycle_readonly", test_lifecycle_readonly),
        ("comfy_inheritance", test_comfy_inheritance),
        ("ocp_imports", test_ocp_old_pages_untouched_import),
        ("no_stylesheet", test_no_stylesheet_in_hub),
        ("shell_resolve", test_shell_can_ensure_page),
        ("uninstall_safe", test_uninstall_clear_registration_only),
        ("ui_smoke", test_ui_smoke),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL {name}")
            traceback.print_exc()
    if failed:
        return _fail(f"{failed}/{len(tests)} tests failed")
    print(f"verify_engine_host_hub: ALL {len(tests)} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
