# -*- coding: utf-8 -*-
"""Harness 运行环境检测与一键安装。"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SetupGate 识别：缺 Node 时展示「去安装 Node.js」
NEED_NODE_PREFIX = "NEED_NODE:"

# npm 内核钉扎（升级迭代改这里；禁止长期漂 latest）
# CDN zip 的 bundle_version 可暂慢一拍（底座包）；已装用户靠 upgrade_dsh_core_inplace 升核并保留 .dsh
DSH_NPM_PACKAGE = "@deepseek-ai/dsh@0.1.7-rc.2"
# 内核 npm 版本；CDN zip 的 bundle_version 可带重建后缀（如 0.1.7-rc.2.1），二者勿混为同一字段
DSH_PINNED_VERSION = "0.1.7-rc.2"


def _workbuddy_roots() -> list[Path]:
    home = Path.home()
    roots = [home / ".workbuddy", home / "WorkBuddy"]
    desktop = home / "Desktop"
    if desktop.is_dir():
        roots.append(desktop / "WorkBuddy")
    return [r for r in roots if r.is_dir()]


def discover_runtime() -> dict[str, str]:
    """扫描运行时：优先 TOA 独立目录（含便携 Node），其次本机 Node，再次 WorkBuddy（仅借 node/dsh）。"""
    found: dict[str, str] = {}
    toa_root = default_install_root()
    toa_dsh = toa_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    toa_home = toa_root / ".dsh"
    toa_node = toa_root / "node" / ("node.exe" if os.name == "nt" else "node")
    if toa_dsh.is_file():
        found["dsh_bin"] = str(toa_dsh)
    if toa_node.is_file():
        found["node_exe"] = str(toa_node)
    # 始终优先 TOA home（可尚不存在）；绝不把 WorkBuddy/.dsh 写入发现结果
    found["dsh_home"] = str(toa_home)

    sys_node = find_system_node()
    if sys_node is not None:
        found.setdefault("node_exe", str(sys_node))

    for root in _workbuddy_roots():
        binaries = root / "binaries" / "node" / "versions"
        if binaries.is_dir():
            versions = sorted(binaries.iterdir(), key=lambda p: p.name, reverse=True)
            for ver in versions:
                node = ver / "node.exe"
                dsh = ver / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
                if node.is_file():
                    found.setdefault("node_exe", str(node))
                if dsh.is_file():
                    found.setdefault("dsh_bin", str(dsh))
                if found.get("node_exe") and found.get("dsh_bin"):
                    break
        if found.get("node_exe") and found.get("dsh_bin"):
            break
    return found


def find_system_node() -> Path | None:
    """本机 Node（PATH / 常见安装路径）。"""
    import shutil

    which = shutil.which("node")
    if which:
        p = Path(which)
        if p.is_file():
            return p
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "nodejs" / "node.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs" / "node.exe",
    ]
    for p in roots:
        if p.is_file():
            return p
    return None


def default_install_root() -> Path:
    return Path.home() / ".toa3" / "harness-runtime"


def npm_install_dsh(node_exe: Path, install_root: Path, *, timeout: float = 900.0) -> tuple[bool, str]:
    install_root.mkdir(parents=True, exist_ok=True)
    npm = node_exe.parent / "npm.cmd"
    if not npm.is_file():
        npm = node_exe.parent / "npm"
    if not npm.is_file():
        return False, "未找到 npm，请使用完整 Node 安装包。"
    cmd = [str(npm), "install", DSH_NPM_PACKAGE, "--prefix", str(install_root), "--no-fund", "--no-audit"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            # 超时杀进程后偶发：包其实已装上（大树安装常 >10min）
            dsh_ok = (install_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js").is_file()
            if dsh_ok:
                try:
                    from services.harness_system_backup import read_installed_dsh_core_version

                    if read_installed_dsh_core_version(install_root) == DSH_PINNED_VERSION:
                        return True, str(
                            install_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
                        )
                except Exception:
                    pass
            tail = (result.stderr or result.stdout or "").strip()[-400:]
            return False, f"安装失败：{tail or 'npm 退出非零'}"
    except subprocess.TimeoutExpired:
        dsh = install_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        if dsh.is_file():
            try:
                from services.harness_system_backup import read_installed_dsh_core_version

                ver = read_installed_dsh_core_version(install_root)
                if ver == DSH_PINNED_VERSION:
                    return True, str(dsh)
                return False, f"安装超时且内核为 {ver or '?'}，期望 {DSH_PINNED_VERSION}"
            except Exception:
                pass
        return False, "安装超时，请检查网络后重试。"
    except OSError as exc:
        return False, str(exc)
    dsh = install_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    if not dsh.is_file():
        return False, "安装完成但未找到 dsh，请重试或手动检测路径。"
    return True, str(dsh)


def upgrade_dsh_core_inplace(
    *,
    progress=None,
    cancel=None,
    flavor: str | None = None,
    plugin_snapshot: dict | None = None,
) -> tuple[bool, str]:
    """原地升核到 ``DSH_PINNED_VERSION``：保留 ``.dsh`` 会话/Key/插件清单，合并并重装缺失包。

    用于「更新环境」在 CDN zip 尚未跟上钉扎时的主路径；也用于 zip 解压后二次对齐内核。
    ``plugin_snapshot`` 若由调用方在装前 capture，优先使用（避免 zip 洗包后快照为空）。
    """
    from services.harness_plugins import capture_profile_plugins
    from services.harness_prefab import (
        FLAVOR_PREFAB,
        normalize_flavor,
        portable_node_exe,
        read_installed_manifest,
        write_manifest,
    )
    from services.harness_system_backup import read_installed_dsh_core_version

    def _prog(msg: str, pct: int = 0, stage: str = "upgrade") -> None:
        if progress:
            try:
                progress(msg, int(pct), stage)
            except TypeError:
                progress(msg)

    def _cancelled() -> bool:
        return bool(cancel and cancel())

    root = default_install_root()
    home = root / ".dsh"
    if not root.is_dir():
        return False, "尚未安装 Harness 运行环境，请先走四步开用。"

    manifest = read_installed_manifest(root) if root.is_dir() else {}
    f = normalize_flavor(str(flavor or manifest.get("flavor") or FLAVOR_PREFAB))
    before = read_installed_dsh_core_version(root)
    if before == DSH_PINNED_VERSION:
        return True, f"内核已是钉扎版本 {DSH_PINNED_VERSION}，无需升核"

    _prog(f"准备升核 {before or '?'} → {DSH_PINNED_VERSION}…", 5)
    if _cancelled():
        return False, "已取消升级"

    plugin_snap = plugin_snapshot
    if plugin_snap is None:
        plugin_snap = capture_profile_plugins(home) if home.is_dir() else None
    _prog("已快照插件清单（升级后合并）", 8)

    try:
        from services import harness_sidecar

        _prog("正在停止服务…", 10)
        harness_sidecar.stop(force=True)
    except Exception as exc:
        logger.warning("stop before core upgrade: %s", exc)

    if _cancelled():
        return False, "已取消升级"

    node_p = portable_node_exe(root)
    if not node_p.is_file():
        sys_node = find_system_node()
        if sys_node is None or not sys_node.is_file():
            return False, "未找到可用 Node（便携或本机），无法升核。"
        node_p = sys_node

    _prog(f"正在 npm 安装 {DSH_NPM_PACKAGE}（保留会话目录）…", 20)
    ok_npm, npm_msg = npm_install_dsh(node_p, root, timeout=1200.0)
    if not ok_npm:
        return False, npm_msg
    if _cancelled():
        return False, "已取消升级"

    dsh_p = root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    after = read_installed_dsh_core_version(root)
    if after != DSH_PINNED_VERSION:
        return False, f"升核后内核为 {after or '?'}，期望 {DSH_PINNED_VERSION}"

    # MANIFEST：程序包号可仍是 CDN 底座；内核钉扎写入 dsh_pinned
    try:
        write_manifest(
            root,
            flavor=f,
            version=str(manifest.get("version") or DSH_PINNED_VERSION),
            plugins=list(manifest.get("plugins") or []),
            extra={
                "dsh_pinned": DSH_PINNED_VERSION,
                "core_upgrade": "npm",
                "upgraded_from": before or "",
            },
        )
    except Exception as exc:
        logger.warning("write MANIFEST after core upgrade: %s", exc)

    _prog("正在恢复插件与 Web 组件…", 70)
    ok_fin, fin_msg = _finalize_runtime(
        node_p,
        dsh_p,
        home,
        ok_msg=f"内核已升级到 {DSH_PINNED_VERSION}",
        plugin_snapshot=plugin_snap,
        flavor=f,
    )
    if not ok_fin:
        return False, fin_msg
    _prog("升核完成", 100)
    return True, fin_msg


def init_dsh_home(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        profiles = path / "profiles" / "web"
        profiles.mkdir(parents=True, exist_ok=True)
        pkg = profiles / "package.json"
        if not pkg.is_file():
            pkg.write_text(
                '{"name":"dsh-profile-web","private":true,"dependencies":{},'
                '"dsh":{"profile":{"bundles":["@deepseek-ai/dsh-base","@deepseek-ai/dsh-web-app"]}}}',
                encoding="utf-8",
            )
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


def runtime_report(node: Path, dsh: Path, home: Path) -> dict[str, Any]:
    return {
        "node_ok": node.is_file(),
        "dsh_ok": dsh.is_file(),
        "home_ok": home.is_dir(),
        "node_exe": str(node),
        "dsh_bin": str(dsh),
        "dsh_home": str(home),
    }


def _finalize_runtime(
    node_p: Path,
    dsh_p: Path,
    home: Path,
    *,
    ok_msg: str,
    plugin_snapshot: dict | None = None,
    flavor: str = "prefab",
) -> tuple[bool, str]:
    from services.harness_config import (
        PRODUCT_SURFACE_MODE,
        load_harness_config,
        save_harness_config,
    )
    from services.harness_plugins import (
        ensure_plugins_after_install,
        ensure_web_profile_bundles,
        sanitize_web_profile_package,
    )

    ok_home, _ = init_dsh_home(home)
    if not ok_home:
        return False, "无法创建 DSH 数据目录"

    try:
        from services.harness_runtime_heal import ensure_runtime_boot_prereqs, node_has_zstd

        # node 在 install_root/node/node.exe → parent.parent = install_root
        root_guess = node_p.parent.parent
        if not (root_guess / "node_modules").is_dir():
            root_guess = default_install_root()
        ok_rt, rt_msg = ensure_runtime_boot_prereqs(root_guess)
        if not ok_rt:
            return False, rt_msg or "运行时前置检查失败"
        # heal 可能已把配置切到本机 Node；收尾写回时沿用
        try:
            healed = Path(str(load_harness_config(force=True).get("node_exe") or ""))
            if healed.is_file() and node_has_zstd(healed):
                node_p = healed
        except Exception:
            pass
    except Exception as exc:
        logger.warning("finalize runtime heal skipped: %s", exc)
        rt_msg = ""

    plugin_note = ""
    if plugin_snapshot:
        ok_plug, plug_msg = ensure_plugins_after_install(
            home,
            plugin_snapshot,
            flavor=flavor,
            node=node_p,
            dsh=dsh_p,
        )
        plugin_note = plug_msg
        if not ok_plug:
            return False, f"插件恢复失败：{plug_msg}"
    else:
        ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
        if not ok_prof:
            return False, f"Web 界面组件安装失败：{prof_msg}"
        ok_san, san_msg = sanitize_web_profile_package(home, dsh=dsh_p)
        if not ok_san:
            return False, f"清理 profile 插件失败：{san_msg}"
        if san_msg and "移除" in san_msg:
            plugin_note = san_msg

    save_harness_config(
        {
            "enabled": True,
            "auto_start": True,
            "surface_mode": PRODUCT_SURFACE_MODE,
            "web_port": 3082,
            "node_exe": str(node_p),
            "dsh_bin": str(dsh_p),
            "dsh_home": str(home),
        }
    )
    load_harness_config(force=True)
    try:
        from services.harness_model_defaults import ensure_official_default_model

        ensure_official_default_model()
    except Exception:
        pass
    extras = [x for x in (plugin_note, rt_msg) if x and "无插件" not in x and "跳过" not in x]
    if extras:
        return True, f"{ok_msg}；" + "；".join(extras)
    return True, ok_msg


def install_harness_runtime(
    flavor: str | None = None,
    *,
    progress=None,
    cancel=None,
) -> tuple[bool, str]:
    """安装 / 登记 Harness 运行环境。

    - ``flavor`` 为 ``official`` / ``prefab``：走官方预制 zip 双路线（主路径）。
    - ``flavor`` 为空：登记已有环境，或回落本机 Node + npm（修复/高级）。
    """
    try:
        if flavor:
            return _install_flavor_inner(str(flavor), progress=progress, cancel=cancel)
        return _install_harness_runtime_inner()
    except OSError as exc:
        from services.harness_plugins import _friendly_os_error

        return False, _friendly_os_error(exc)


def _install_flavor_inner(flavor: str, *, progress=None, cancel=None) -> tuple[bool, str]:
    from services.harness_config import align_harness_runtime_config
    from services.harness_plugins import capture_profile_plugins
    from services.harness_prefab import (
        FLAVOR_LABELS,
        dsh_bin_under,
        install_prefab_bundle,
        normalize_flavor,
        portable_node_exe,
    )

    align_harness_runtime_config(persist=True)
    f = normalize_flavor(flavor)
    label = FLAVOR_LABELS.get(f, f)
    root = default_install_root()
    home_pre = root / ".dsh"
    plugin_snap = capture_profile_plugins(home_pre) if home_pre.is_dir() else None
    ok, msg = install_prefab_bundle(
        f,
        install_root=root,
        progress=progress,
        cancel=cancel,
        keep_user_data=True,
    )
    if not ok:
        # 未配置 URL 且本机已有 Node：可回落 npm，并标明来源
        if "尚未配置" in msg:
            found = discover_runtime()
            node_s = str(found.get("node_exe") or "").strip()
            if not node_s or not Path(node_s).is_file():
                sys_node = find_system_node()
                node_s = str(sys_node) if sys_node else ""
            if node_s and Path(node_s).is_file():
                ok_npm, npm_msg = _install_via_npm(Path(node_s))
                if ok_npm:
                    return True, f"{npm_msg}（预制包地址未配置，已用本机 Node 在线安装）"
                return False, f"{msg}\n另：在线安装也失败：{npm_msg}"
        return False, msg

    node_p = portable_node_exe(root)
    dsh_p = dsh_bin_under(root)
    home = root / ".dsh"
    if not node_p.is_file() or not dsh_p.is_file():
        return False, f"「{label}」解压后校验失败，请重试或改装另一版本。"

    # CDN 底座可能慢于代码钉扎：解压后原地 npm 升核，会话/插件快照已在上方 capture
    from services.harness_system_backup import read_installed_dsh_core_version

    core_now = read_installed_dsh_core_version(root)
    if core_now and core_now != DSH_PINNED_VERSION:
        if progress:
            try:
                progress(f"预制包内核 {core_now}，对齐钉扎 {DSH_PINNED_VERSION}…", 88, "upgrade")
            except TypeError:
                progress(f"预制包内核 {core_now}，对齐钉扎 {DSH_PINNED_VERSION}…")
        ok_up, up_msg = upgrade_dsh_core_inplace(
            progress=progress,
            cancel=cancel,
            flavor=f,
            plugin_snapshot=plugin_snap,
        )
        if not ok_up:
            return False, f"{msg}；升核失败：{up_msg}"
        return True, f"{msg}；{up_msg}"

    return _finalize_runtime(
        node_p,
        dsh_p,
        home,
        ok_msg=msg,
        plugin_snapshot=plugin_snap,
        flavor=f,
    )


def _install_via_npm(node_p: Path) -> tuple[bool, str]:
    root = default_install_root()
    ok, msg = npm_install_dsh(node_p, root)
    if not ok:
        return False, msg
    dsh_p = root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    home = root / ".dsh"
    return _finalize_runtime(
        node_p,
        dsh_p,
        home,
        ok_msg="DeepSeek Harness 安装完成，请保存 API Key 后启动服务",
    )


def _install_harness_runtime_inner() -> tuple[bool, str]:
    from services.harness_config import (
        align_harness_runtime_config,
        is_workbuddy_home,
        load_harness_config,
    )

    align_harness_runtime_config(persist=True)

    found = discover_runtime()
    node_s = str(found.get("node_exe") or "").strip()
    dsh_s = str(found.get("dsh_bin") or "").strip()

    if not node_s or not Path(node_s).is_file():
        sys_node = find_system_node()
        if sys_node is not None:
            node_s = str(sys_node)

    # 已有 dsh：登记到 TOA 数据目录（勿再绑 WorkBuddy 脏 home）
    if node_s and dsh_s and Path(node_s).is_file() and Path(dsh_s).is_file():
        node_p = Path(node_s)
        dsh_p = Path(dsh_s)
        cfg = load_harness_config()
        home_s = str(cfg.get("dsh_home") or "").strip()
        if (not home_s) or is_workbuddy_home(home_s):
            home = default_install_root() / ".dsh"
        else:
            home = Path(home_s)
        return _finalize_runtime(
            node_p,
            dsh_p,
            home,
            ok_msg="已登记本机 Harness 环境并完成 Web 组件检查",
        )

    if node_s and Path(node_s).is_file():
        return _install_via_npm(Path(node_s))

    return (
        False,
        f"{NEED_NODE_PREFIX}"
        "本机未找到运行环境。请选择「安装官方版」或「安装预制版」下载预制包；"
        "若预制地址未就绪，也可先安装 Node.js LTS 后走高级回退。",
    )


def repair_harness_runtime() -> tuple[bool, str]:
    """修复：读上次启动日志自诊 → 清僵锁 → 剔杀手插件 → 重建 Web → 快照；人话结果。

    不要求用户打开日志；日志只给 Host 对照常见错自动处理。
    """
    from services.harness_config import (
        align_harness_runtime_config,
        is_workbuddy_home,
        load_harness_config,
        save_harness_config,
    )
    from services.harness_credentials import (
        clear_stale_credential_locks,
        diagnose_llm_access,
        has_api_key,
        sanitize_credentials_document,
    )
    from services.harness_model_defaults import ensure_official_default_model
    from services.harness_plugins import (
        ensure_web_profile_bundles,
        heal_web_profile_junction,
        link_web_profile_node_modules,
        sanitize_web_profile_package,
        strip_boot_killer_plugins,
        strip_utf8_bom_in_profile,
        web_profile_ready,
    )
    from services.harness_profile_versions import (
        ensure_baseline_snapshot,
        snapshot_web_profile,
    )
    from services.harness_sidecar import diagnose_start_log

    align_notes = align_harness_runtime_config(persist=True, force=True)
    cfg = load_harness_config(force=True)
    node_s = str(cfg.get("node_exe") or "").strip()
    dsh_s = str(cfg.get("dsh_bin") or "").strip()
    if not node_s or not dsh_s or not Path(node_s).is_file() or not Path(dsh_s).is_file():
        return install_harness_runtime()
    node_p = Path(node_s)
    dsh_p = Path(dsh_s)
    home_s = str(cfg.get("dsh_home") or "").strip()
    if (not home_s) or is_workbuddy_home(home_s):
        home = default_install_root() / ".dsh"
    else:
        home = Path(home_s)
    ok_home, _ = init_dsh_home(home)
    if not ok_home:
        return False, "无法创建 DSH 数据目录"

    notes: list[str] = list(align_notes)
    last_cause = diagnose_start_log()
    if last_cause:
        notes.append(f"根据上次启动记录：{last_cause}")

    ok_lock, lock_msg = clear_stale_credential_locks(home)
    if lock_msg:
        notes.append(lock_msg)
    if not ok_lock:
        return False, lock_msg or "无法清除凭证锁"

    ensure_baseline_snapshot(home=home)

    ok_bom, bom_msg = strip_utf8_bom_in_profile(home)
    if bom_msg and "正常" not in bom_msg:
        notes.append(bom_msg)

    ok_cred, cred_msg = sanitize_credentials_document()
    if not ok_cred:
        return False, cred_msg
    if cred_msg and "正常" not in cred_msg and "跳过" not in cred_msg:
        notes.append(cred_msg)

    from services.harness_credentials import ensure_mxapi_image_refs

    ok_mx, mx_msg = ensure_mxapi_image_refs()
    if ok_mx and "已写入" in mx_msg:
        notes.append(mx_msg)

    changed_model, model_msg = ensure_official_default_model()
    if changed_model:
        notes.append(model_msg)

    # 先剔除已知启动杀手（如 dsh-agent-teams ↔ uiConversation）
    ok_kill, kill_msg = strip_boot_killer_plugins(home)
    if "移除" in kill_msg or "remove" in kill_msg.lower():
        notes.append(kill_msg)
    elif not ok_kill:
        notes.append(kill_msg)

    if web_profile_ready(home, dsh=dsh_p):
        notes.append("Web 组件已就绪")
    else:
        ok_link, link_msg = link_web_profile_node_modules(dsh_p, home)
        if ok_link:
            notes.append("已修复 Web 组件")
        else:
            ok_heal, heal_msg = heal_web_profile_junction(dsh_p, home)
            if ok_heal:
                notes.append(heal_msg or "已重建 Web 组件联接")
            else:
                ok_prof, prof_msg = ensure_web_profile_bundles(node_p, dsh_p, home)
                if not ok_prof:
                    return False, prof_msg or heal_msg or link_msg
                notes.append("已补装 Web 组件")

    ok_san, san_msg = sanitize_web_profile_package(home, dsh=dsh_p)
    if not ok_san:
        return False, f"清理 profile 插件失败：{san_msg}"
    if "移除" in san_msg:
        notes.append(san_msg)

    # 清理成功后拍一份「可用」快照，供下次插件搞挂一键回退
    ok_snap, snap_msg, _ = snapshot_web_profile(reason="after_repair", mark_good=True, home=home)
    if ok_snap:
        notes.append(snap_msg)

    # 修复不改显示方式：保留用户内嵌/浏览器偏好
    save_harness_config(
        {
            "enabled": True,
            "auto_start": True,
            "node_exe": str(node_p),
            "dsh_bin": str(dsh_p),
            "dsh_home": str(home),
        }
    )
    load_harness_config(force=True)

    key_ok, key_msg = diagnose_llm_access(probe_balance=True)
    if not has_api_key():
        return False, "环境已检查，但未配置 API Key。请在本页保存密钥后再启动。"
    if not key_ok:
        notes.append(key_msg)
        if "余额" in key_msg or "402" in key_msg or "QUOTA" in key_msg:
            notes.append("运行环境已就绪；对话失败需充值 DeepSeek，不是插件损坏。")
            return True, "\n".join(notes)
        notes.append("即将自动重新启动服务。")
        return True, "\n".join(notes)
    notes.append(key_msg)
    notes.append("即将自动重新启动服务。")
    return True, "\n".join(notes)


def uninstall_harness_runtime(*, delete_install: bool = True, keep_user_data: bool = True) -> tuple[bool, str]:
    """一键卸载 Host 登记的运行时：停服务 → 可选删安装包 → 清路径配置。

    - delete_install：删除 ``~/.toa3/harness-runtime/node_modules`` 等安装树
    - keep_user_data：保留 ``.dsh`` 会话/工作区（默认保留，避免误删干活记录）
    """
    import shutil

    from services.harness_config import load_harness_config, save_harness_config
    from services.harness_sidecar import stop

    notes: list[str] = []
    ok_stop, stop_msg = stop(force=True)
    notes.append(stop_msg if ok_stop else f"停止：{stop_msg}")

    root = default_install_root()
    home = root / ".dsh"
    try:
        cfg = load_harness_config(force=True)
        home_s = str(cfg.get("dsh_home") or "").strip()
        if home_s:
            home = Path(home_s)
    except Exception:
        pass

    if delete_install and root.is_dir():
        # 删安装树，但可单独留下 .dsh
        for child in list(root.iterdir()):
            if keep_user_data and child.resolve() == home.resolve():
                continue
            if keep_user_data and child.name == ".dsh":
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)  # type: ignore[call-arg]
            except TypeError:
                try:
                    if child.is_file():
                        child.unlink()
                except OSError as exc:
                    notes.append(f"删除失败 {child.name}：{exc}")
            except OSError as exc:
                notes.append(f"删除失败 {child.name}：{exc}")
        notes.append(f"已清理安装目录：{root}")
    elif delete_install:
        notes.append("安装目录本就不存在")

    if not keep_user_data and home.is_dir():
        try:
            shutil.rmtree(home, ignore_errors=False)
            notes.append("已删除用户数据目录（会话清空）")
        except OSError as exc:
            notes.append(f"用户数据删除失败：{exc}")

    save_harness_config(
        {
            "enabled": False,
            "auto_start": False,
            "node_exe": "",
            "dsh_bin": "",
            # home 保留路径指针便于再装时复用会话；若已删则仍写默认
            "dsh_home": str(home if keep_user_data else (root / ".dsh")),
        }
    )
    load_harness_config(force=True)
    tip = "Harness 已卸载。"
    if keep_user_data:
        tip += "会话数据已保留；需要时可再进页选择官方/预制版安装。"
    else:
        tip += "安装与会话均已清除。"
    notes.append(tip)
    return True, "\n".join(notes)
