#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness 干净机沙箱自验（隔离目录 · 隔离端口 · 不碰用户 3082 服务）。

策略（不影响用户）：
- 不 stop/restart 用户 3082
- 不改 data/user/harness.yml、不写用户 credentials
- 安装树：默认从本机已有 runtime **只读复制**到 output/_harness_sandbox_clean/
  （CDN 可达/sha 另由 verify_harness_cdn 覆盖；加 --from-cdn 才下 zip）
- 启停只打端口 13082

用法：
  python scripts/verify_harness_sandbox_clean.py
  python scripts/verify_harness_sandbox_clean.py --no-start
  python scripts/verify_harness_sandbox_clean.py --from-cdn   # 慢：拉 zip 到缓存再装
"""
from __future__ import annotations

import shutil
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SANDBOX = ROOT / "output" / "_harness_sandbox_clean"
CACHE = ROOT / "output" / "_harness_cdn_cache"
RUNTIME = SANDBOX / "runtime"
USER_CFG = SANDBOX / "harness.yml"
SANDBOX_PORT = 13082
USER_PORT = 3082


def _product_harness() -> dict:
    data = yaml.safe_load((ROOT / "config" / "harness.yml").read_text(encoding="utf-8")) or {}
    block = data.get("harness") or data
    assert isinstance(block, dict)
    return block


def _user_runtime() -> Path:
    return (Path.home() / ".toa3" / "harness-runtime").resolve()


def _ensure_cached_zip(flavor: str, url: str, sha256: str) -> Path:
    from services.harness_prefab import _sha256_file

    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f"harness-{flavor}-cached.zip"
    if dest.is_file() and dest.stat().st_size > 50_000_000:
        digest = _sha256_file(dest)
        if digest == sha256.lower():
            print(f"OK cache hit {dest.name}")
            return dest
    print(f"downloading {url} → {dest.name} …")
    tmp = dest.with_suffix(".partial")
    urllib.request.urlretrieve(url, tmp)
    digest = _sha256_file(tmp)
    assert digest == sha256.lower(), (digest[:16], sha256[:16])
    tmp.replace(dest)
    print(f"OK cached {dest.name}")
    return dest


def _install_from_cdn(flavor: str) -> None:
    import services.harness_prefab as prefab
    from services.harness_prefab import FLAVOR_OFFICIAL, FLAVOR_PREFAB, install_prefab_bundle

    product = _product_harness()
    url_key = "prefab_bundle_url" if flavor == "prefab" else "official_bundle_url"
    sha_key = "prefab_sha256" if flavor == "prefab" else "official_sha256"
    url = str(product.get(url_key) or "").strip()
    sha = str(product.get(sha_key) or "").strip().lower()
    zip_path = _ensure_cached_zip(flavor, url, sha)
    f = FLAVOR_PREFAB if flavor == "prefab" else FLAVOR_OFFICIAL
    orig = prefab.bundle_spec

    def _spec(fl: str) -> dict:
        base = dict(orig(fl))
        base["url"] = zip_path.as_uri()
        base["sha256"] = sha
        return base

    prefab.bundle_spec = _spec  # type: ignore[assignment]
    try:
        if RUNTIME.exists():
            shutil.rmtree(RUNTIME, ignore_errors=True)
        ok, msg = install_prefab_bundle(f, install_root=RUNTIME)
    finally:
        prefab.bundle_spec = orig  # type: ignore[assignment]
    assert ok, msg


def _install_from_local_copy() -> None:
    """只读复制用户已有装树 → 沙箱（不改源目录）。"""
    src = _user_runtime()
    assert src.is_dir(), f"本机无参考装树，请改用 --from-cdn：{src}"
    node = src / "node" / ("node.exe" if sys.platform.startswith("win") else "node")
    dsh = src / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    assert node.is_file() and dsh.is_file(), "参考装树不完整，请 --from-cdn"
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME, ignore_errors=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # 程序树（可较大）；会话目录给空骨架，避免拷用户聊天
    for name in ("node", "node_modules", "MANIFEST.json"):
        p = src / name
        if p.is_dir():
            print(f"copying {name} …")
            shutil.copytree(p, RUNTIME / name, dirs_exist_ok=True, symlinks=True)
        elif p.is_file():
            shutil.copy2(p, RUNTIME / name)
    from services.harness_plugins import (
        link_web_profile_node_modules,
        strip_utf8_bom_in_profile,
    )
    from services.harness_setup import init_dsh_home

    ok, msg = init_dsh_home(RUNTIME / ".dsh")
    assert ok, msg
    dsh = RUNTIME / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    ok_link, link_msg = link_web_profile_node_modules(dsh, RUNTIME / ".dsh")
    print(f"web link: {ok_link} {link_msg}")
    strip_utf8_bom_in_profile(RUNTIME / ".dsh")
    print("OK sandbox tree from local copy (sessions empty)")


def _write_sandbox_cfg(*, node: Path, dsh: Path, home: Path) -> None:
    USER_CFG.parent.mkdir(parents=True, exist_ok=True)
    USER_CFG.write_text(
        yaml.safe_dump(
            {
                "harness": {
                    "enabled": True,
                    "auto_start": False,
                    "surface_mode": "embed",
                    "web_port": SANDBOX_PORT,
                    "dsh_home": str(home),
                    "node_exe": str(node),
                    "dsh_bin": str(dsh),
                    "stop_on_app_exit": True,
                    "clear_env_api_key": True,
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def main() -> int:
    from_cdn = "--from-cdn" in sys.argv
    no_start = "--no-start" in sys.argv
    flavor = "prefab"
    if "--flavor" in sys.argv:
        flavor = sys.argv[sys.argv.index("--flavor") + 1].strip().lower()

    assert RUNTIME.resolve() != _user_runtime()
    assert SANDBOX_PORT != USER_PORT

    if RUNTIME.exists() and (RUNTIME / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js").is_file():
        print("OK reuse existing sandbox tree")
        from services.harness_plugins import link_web_profile_node_modules, strip_utf8_bom_in_profile
        from services.harness_setup import init_dsh_home

        init_dsh_home(RUNTIME / ".dsh")
        dsh_p = RUNTIME / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        link_web_profile_node_modules(dsh_p, RUNTIME / ".dsh")
        strip_utf8_bom_in_profile(RUNTIME / ".dsh")
    elif from_cdn:
        _install_from_cdn(flavor)
    else:
        _install_from_local_copy()

    from services.harness_prefab import (
        dsh_bin_under,
        portable_node_exe,
        read_installed_manifest,
        verify_install_tree,
    )

    ok_tree, tree_msg = verify_install_tree(RUNTIME)
    assert ok_tree, tree_msg
    man = read_installed_manifest(RUNTIME)
    print(f"OK sandbox tree ver={man.get('version') or '?'} flavor={man.get('flavor') or '?'}")

    from services.harness_config import load_harness_config, node_exe_path

    # 用用户当前正在用的 Node 二进制（只读路径），避免便携 Node 22 上 import.meta.main 不跑 CLI
    live_cfg = load_harness_config(force=True)
    live_node = node_exe_path()
    if not live_node.is_file():
        live_node = portable_node_exe(RUNTIME)
    print(f"sandbox node (read-only): {live_node}")

    dsh = dsh_bin_under(RUNTIME)
    home = RUNTIME / ".dsh"
    assert dsh.is_file()
    assert dsh.resolve().is_relative_to(RUNTIME.resolve())
    _write_sandbox_cfg(node=live_node, dsh=dsh, home=home)

    if no_start:
        print("VERIFY harness_sandbox_clean OK (install-only)")
        return 0

    from services import harness_config as hc
    from services import harness_sidecar as side

    hc._CACHE = None
    hc._ALIGNED_ONCE = True
    orig_user = hc._user_harness_path
    orig_log = side.sidecar_log_path
    orig_log2 = side._sidecar_log_path
    sandbox_log = SANDBOX / "sidecar_last.log"
    sandbox_log.parent.mkdir(parents=True, exist_ok=True)

    def _sb_log() -> Path:
        return sandbox_log

    hc._user_harness_path = lambda: USER_CFG  # type: ignore[assignment]
    side.sidecar_log_path = _sb_log  # type: ignore[assignment]
    side._sidecar_log_path = _sb_log  # type: ignore[assignment]
    try:
        cfg = hc.load_harness_config(force=True)
        print(
            "sandbox cfg port=",
            cfg.get("web_port"),
            "dsh=",
            cfg.get("dsh_bin"),
            "home=",
            cfg.get("dsh_home"),
        )
        assert int(cfg.get("web_port") or 0) == SANDBOX_PORT
        assert Path(str(cfg.get("dsh_bin"))).resolve().is_relative_to(RUNTIME.resolve())

        user_busy = side._port_open(USER_PORT)
        print(f"note: user port {USER_PORT} busy={user_busy} (must stay untouched)")

        ok_start, start_msg = side.start(wait_ready=True, timeout_sec=50.0)
        if not ok_start:
            tail = sandbox_log.read_text(encoding="utf-8", errors="replace")[-1200:] if sandbox_log.is_file() else ""
            raise AssertionError(f"{start_msg}\n--- sandbox log ---\n{tail}")
        assert ok_start, start_msg
        assert side.is_running(timeout=1.2)
        assert side._port_open(SANDBOX_PORT)
        assert f":{SANDBOX_PORT}" in hc.web_url()
        print(f"OK sandbox start: {start_msg[:120]}")

        ok_stop, stop_msg = side.stop(force=True)
        assert ok_stop, stop_msg
        time.sleep(0.6)
        assert not side._port_open(SANDBOX_PORT)
        if user_busy:
            assert side._port_open(USER_PORT), "禁止影响用户 3082"
            print(f"OK user port {USER_PORT} still up")
        print(f"OK sandbox stop: {stop_msg}")
    finally:
        try:
            if int(hc.load_harness_config(force=True).get("web_port") or 0) == SANDBOX_PORT:
                side.stop(force=True)
        except Exception:
            pass
        hc._user_harness_path = orig_user  # type: ignore[assignment]
        side.sidecar_log_path = orig_log  # type: ignore[assignment]
        side._sidecar_log_path = orig_log2  # type: ignore[assignment]
        hc._CACHE = None
        hc._ALIGNED_ONCE = False
        hc.load_harness_config(force=True)

    print("VERIFY harness_sandbox_clean OK (user runtime untouched)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
