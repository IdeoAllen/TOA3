# -*- coding: utf-8 -*-
"""DSH 官方/预制 zip 下载、校验、解压。

制品根目录（解压后即 harness-runtime）：
  node/node.exe
  node_modules/@deepseek-ai/dsh/lib/bin.js
  .dsh/…（空骨架，无 credentials）
  MANIFEST.json
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("TOA3.harness_prefab")

FLAVOR_OFFICIAL = "official"
FLAVOR_PREFAB = "prefab"
FLAVORS = (FLAVOR_OFFICIAL, FLAVOR_PREFAB)

FLAVOR_LABELS: dict[str, str] = {
    FLAVOR_OFFICIAL: "官方精简版",
    FLAVOR_PREFAB: "预制必备版",
}

FLAVOR_BLURBS: dict[str, str] = {
    FLAVOR_OFFICIAL: "精简干净 · 仅核心 Web · 无扩展插件",
    FLAVOR_PREFAB: "含必备插件 · 开箱少折腾 · 推荐日常",
}

# 进度阶段（文案给 SetupGate）
STAGE_CONNECT = "connect"
STAGE_DOWNLOAD = "download"
STAGE_VERIFY = "verify"
STAGE_EXTRACT = "extract"
STAGE_CONFIGURE = "configure"
STAGE_DONE = "done"

STAGE_LABELS: dict[str, str] = {
    STAGE_CONNECT: "连接服务器",
    STAGE_DOWNLOAD: "下载中",
    STAGE_VERIFY: "校验完整性",
    STAGE_EXTRACT: "解压到本机",
    STAGE_CONFIGURE: "配置运行环境",
    STAGE_DONE: "完成",
}

ProgressFn = Callable[[str, int, str], None]
# msg, percent 0-100, stage
CancelFn = Callable[[], bool]

CORE_BUNDLES = ("@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app")


class InstallCancelled(Exception):
    """用户取消安装。"""


def _noop_progress(msg: str, pct: int = 0, stage: str = "") -> None:
    del msg, pct, stage


def _never_cancel() -> bool:
    return False


def normalize_flavor(flavor: str | None) -> str:
    f = str(flavor or "").strip().lower()
    if f in FLAVORS:
        return f
    return FLAVOR_PREFAB


def bundle_spec(flavor: str) -> dict[str, Any]:
    """从 harness.yml 读某 flavor 的下载元数据。"""
    from services.harness_config import load_harness_config

    cfg = load_harness_config()
    f = normalize_flavor(flavor)
    if f == FLAVOR_OFFICIAL:
        return {
            "flavor": f,
            "url": str(cfg.get("official_bundle_url") or "").strip(),
            "sha256": str(cfg.get("official_sha256") or "").strip().lower(),
            "version": str(cfg.get("official_bundle_version") or "").strip(),
            "size_hint_mb": cfg.get("official_size_hint_mb"),
        }
    return {
        "flavor": f,
        "url": str(cfg.get("prefab_bundle_url") or "").strip(),
        "sha256": str(cfg.get("prefab_sha256") or "").strip().lower(),
        "version": str(cfg.get("prefab_bundle_version") or "").strip(),
        "size_hint_mb": cfg.get("prefab_size_hint_mb"),
        "plugins": list(cfg.get("prefab_essential_plugins") or []),
    }


def essential_plugins() -> list[str]:
    from services.harness_config import load_harness_config

    raw = load_harness_config().get("prefab_essential_plugins") or []
    out: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def portable_node_exe(install_root: Path) -> Path:
    return install_root / "node" / ("node.exe" if os.name == "nt" else "node")


def dsh_bin_under(install_root: Path) -> Path:
    return install_root / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"


def verify_install_tree(install_root: Path) -> tuple[bool, str]:
    node = portable_node_exe(install_root)
    dsh = dsh_bin_under(install_root)
    if not node.is_file():
        return False, f"预制包缺少便携 Node：{node}"
    if not dsh.is_file():
        return False, f"预制包缺少 dsh：{dsh}"
    return True, "ok"


def read_installed_manifest(install_root: Path) -> dict[str, Any]:
    path = install_root / "MANIFEST.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def runtime_update_available(
    install_root: Path | None = None,
) -> dict[str, Any] | None:
    """本机 MANIFEST / 内核与 harness.yml 钉扎不一致时返回更新信息。

    判定：bundle version 不同，或双方均有 sha256 且不同，或 dsh 内核偏离钉扎。
    仅比对本机与配置钉扎（与 SOP-04 §5「切配置」同节奏），**不**联网扫 CDN。
    无安装树 / 无钉扎 / 完全一致 → None。
    """
    from services.harness_setup import DSH_PINNED_VERSION, default_install_root
    from services.harness_system_backup import read_installed_dsh_core_version

    root = Path(install_root) if install_root is not None else default_install_root()
    if not root.is_dir():
        return None
    manifest = read_installed_manifest(root)
    if not manifest:
        return None
    flavor = normalize_flavor(str(manifest.get("flavor") or FLAVOR_PREFAB))
    installed = str(manifest.get("version") or "").strip()
    installed_sha = str(manifest.get("sha256") or "").strip().lower()
    spec = bundle_spec(flavor)
    available = str(spec.get("version") or "").strip()
    expect_sha = str(spec.get("sha256") or "").strip().lower()
    url = str(spec.get("url") or "").strip()
    if not available or not url:
        return None
    version_diff = bool(installed and installed != available)
    sha_diff = bool(installed_sha and expect_sha and installed_sha != expect_sha)
    core = read_installed_dsh_core_version(root)
    # 代码钉扎优先：CDN 底座可暂慢一拍，内核落后即提示「更新环境」（走 npm 原地升核）
    pinned_core = DSH_PINNED_VERSION
    core_drift = bool(core and pinned_core and core != pinned_core)
    # 旧安装无 sha：只能靠 version；同号重建包须改 yml version 或写进 MANIFEST.sha256
    if not version_diff and not sha_diff and not core_drift:
        return None
    if not installed and not sha_diff and not core_drift:
        return None
    size = spec.get("size_hint_mb")
    try:
        size_mb = int(float(size)) if size is not None else 0
    except (TypeError, ValueError):
        size_mb = 0
    # 仅内核落后且 CDN 同号：体积提示改为 npm 升核（远小于整包）
    npm_core_only = bool(core_drift and not version_diff and not sha_diff)
    if npm_core_only:
        size_mb = 0
    display_available = available
    if core_drift and not version_diff:
        display_available = f"{pinned_core}（npm 升核，保留会话/插件）"
    elif not version_diff and sha_diff:
        display_available = f"{available}（程序包更新）"
    installed_display = installed or "(未知)"
    if core_drift:
        installed_display = f"{installed_display} · 内核 {core}"
    return {
        "flavor": flavor,
        "label": FLAVOR_LABELS.get(flavor, flavor),
        "installed_version": installed_display,
        "available_version": display_available,
        "available_version_raw": available,
        "size_hint_mb": size_mb,
        "url": url,
        "sha_diff": sha_diff,
        "version_diff": version_diff,
        "core_drift": core_drift,
        "npm_core_only": npm_core_only,
        "upgrade_via": "npm" if npm_core_only else "cdn",
        "dsh_core": core,
        "dsh_pinned": pinned_core,
    }


def write_manifest(
    install_root: Path,
    *,
    flavor: str,
    version: str = "",
    plugins: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "flavor": normalize_flavor(flavor),
        "version": version or "dev",
        "plugins": list(plugins or []),
        "core_bundles": list(CORE_BUNDLES),
    }
    if extra:
        payload.update(extra)
    path = install_root / "MANIFEST.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _raise_if_cancelled(cancel: CancelFn) -> None:
    if cancel():
        raise InstallCancelled("已取消安装")


def _resolve_source(url: str) -> tuple[str, Path | None]:
    """返回 (kind, local_path)。kind=http|file。"""
    raw = (url or "").strip()
    if not raw:
        return "http", None
    if raw.lower().startswith("file:"):
        from urllib.parse import urlparse, unquote

        parsed = urlparse(raw)
        path = unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return "file", Path(path)
    p = Path(raw)
    if p.is_file():
        return "file", p
    return "http", None


def _sha256_file(path: Path, *, cancel: CancelFn, progress: ProgressFn) -> str:
    h = hashlib.sha256()
    total = max(1, path.stat().st_size)
    done = 0
    with path.open("rb") as f:
        while True:
            _raise_if_cancelled(cancel)
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
            done += len(block)
            pct = 55 + int(done * 10 / total)
            progress(STAGE_LABELS[STAGE_VERIFY], min(65, pct), STAGE_VERIFY)
    return h.hexdigest()


def _fmt_eta(seconds: float) -> str:
    if seconds < 5 or seconds > 3600 * 6:
        return ""
    if seconds < 60:
        return f"，大约还要不到 1 分钟"
    mins = int(seconds / 60)
    if mins < 60:
        return f"，大约还要 {mins} 分钟"
    return f"，大约还要 {mins // 60} 小时"


def _download_http(
    url: str,
    dest: Path,
    *,
    cancel: CancelFn,
    progress: ProgressFn,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    progress(STAGE_LABELS[STAGE_CONNECT], 2, STAGE_CONNECT)
    req = urllib.request.Request(url, headers={"User-Agent": "TOA3-harness-prefab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            chunk = 1024 * 256
            last_pct = -1
            t0 = time.monotonic()
            last_ui = 0.0
            with tmp.open("wb") as out:
                while True:
                    _raise_if_cancelled(cancel)
                    block = resp.read(chunk)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    now = time.monotonic()
                    if total > 0:
                        pct = 5 + int(done * 50 / total)
                        # 每 1% 或每 0.8s 刷新，避免 UI 刷屏
                        if pct != last_pct or (now - last_ui) >= 0.8:
                            mb_done = done / (1024 * 1024)
                            mb_total = total / (1024 * 1024)
                            elapsed = max(0.01, now - t0)
                            speed = done / elapsed
                            remain = (total - done) / speed if speed > 1024 else 0
                            eta = _fmt_eta(remain)
                            progress(
                                f"正在下载 {mb_done:.0f}/{mb_total:.0f} MB"
                                f"（约 {mb_total:.0f} MB，可取消）{eta}",
                                min(55, pct),
                                STAGE_DOWNLOAD,
                            )
                            last_pct = pct
                            last_ui = now
                    elif (now - last_ui) >= 1.0:
                        mb_done = done / (1024 * 1024)
                        progress(
                            f"正在下载…已下 {mb_done:.0f} MB（总大小未知，可取消）",
                            20,
                            STAGE_DOWNLOAD,
                        )
                        last_ui = now
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"下载失败：{exc}") from exc
    except TimeoutError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("下载超时，请检查网络后重试。") from exc
    if not tmp.is_file() or tmp.stat().st_size < 1024:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("下载失败：文件过小或不完整。")
    tmp.replace(dest)


def _safe_extract_zip(zip_path: Path, dest_dir: Path, *, cancel: CancelFn, progress: ProgressFn) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        total = len(names) or 1
        for i, name in enumerate(names):
            _raise_if_cancelled(cancel)
            # 防 zip slip
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise RuntimeError(f"非法压缩路径：{name}")
            zf.extract(name, dest_dir)
            if i % 20 == 0 or i + 1 == total:
                pct = 65 + int((i + 1) * 25 / total)
                progress(
                    f"{STAGE_LABELS[STAGE_EXTRACT]} ({i + 1}/{total})",
                    min(90, pct),
                    STAGE_EXTRACT,
                )


def _unwrap_single_root(extract_dir: Path) -> Path:
    """若 zip 内只有一层顶目录，返回该目录；否则返回 extract_dir。"""
    children = [p for p in extract_dir.iterdir() if not p.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        # 常见：harness-runtime-official/...
        inner = children[0]
        if (inner / "node_modules").is_dir() or (inner / "node").is_dir() or (inner / "MANIFEST.json").is_file():
            return inner
    return extract_dir


def _clear_install_tree(install_root: Path, *, keep_dsh: bool = True) -> None:
    if not install_root.is_dir():
        return
    home = install_root / ".dsh"
    for child in list(install_root.iterdir()):
        if keep_dsh and (child.name == ".dsh" or (home.is_dir() and child.resolve() == home.resolve())):
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("clear install child %s: %s", child, exc)


def install_prefab_bundle(
    flavor: str,
    *,
    install_root: Path | None = None,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
    keep_user_data: bool = True,
) -> tuple[bool, str]:
    """下载并解压指定 flavor 到 install_root。"""
    from services.harness_setup import default_install_root, init_dsh_home

    prog = progress or _noop_progress
    cancel_fn = cancel or _never_cancel
    f = normalize_flavor(flavor)
    label = FLAVOR_LABELS.get(f, f)
    spec = bundle_spec(f)
    url = str(spec.get("url") or "").strip()
    expect_sha = str(spec.get("sha256") or "").strip().lower()
    root = install_root or default_install_root()

    if not url:
        return (
            False,
            f"尚未配置「{label}」下载地址。"
            "请联系管理员发布安装包，或稍后再试。",
        )

    staging: Path | None = None
    zip_path: Path | None = None
    try:
        _raise_if_cancelled(cancel_fn)
        kind, local = _resolve_source(url)
        staging = Path(tempfile.mkdtemp(prefix=f"toa3-harness-{f}-"))
        if kind == "file" and local is not None:
            if not local.is_file():
                return False, f"本地预制包不存在：{local}"
            zip_path = local
            prog(STAGE_LABELS[STAGE_CONNECT], 5, STAGE_CONNECT)
        else:
            zip_path = staging / f"harness-{f}.zip"
            _download_http(url, zip_path, cancel=cancel_fn, progress=prog)

        prog(STAGE_LABELS[STAGE_VERIFY], 56, STAGE_VERIFY)
        digest = _sha256_file(zip_path, cancel=cancel_fn, progress=prog)
        if expect_sha and digest != expect_sha:
            return False, f"校验失败：期望 sha256={expect_sha[:12]}…，实际 {digest[:12]}…"

        extract_dir = staging / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(zip_path, extract_dir, cancel=cancel_fn, progress=prog)
        payload = _unwrap_single_root(extract_dir)

        ok_tree, tree_msg = verify_install_tree(payload)
        if not ok_tree:
            # 允许无便携 node、仅有 dsh 的旧包？计划要求有 node — 严格校验
            return False, tree_msg

        prog(STAGE_LABELS[STAGE_CONFIGURE], 92, STAGE_CONFIGURE)
        root.mkdir(parents=True, exist_ok=True)

        # 升级前快照用户插件（.dsh 会保留，但 sanitize/官方口味可能洗清单）
        plugin_snap = None
        existing_home = root / ".dsh"
        if keep_user_data and existing_home.is_dir():
            try:
                from services.harness_plugins import capture_profile_plugins

                plugin_snap = capture_profile_plugins(existing_home)
            except Exception as exc:
                logger.warning("capture plugins before install: %s", exc)

        _clear_install_tree(root, keep_dsh=keep_user_data)

        for child in payload.iterdir():
            _raise_if_cancelled(cancel_fn)
            if keep_user_data and child.name == ".dsh" and (root / ".dsh").is_dir():
                continue
            dest = root / child.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
                else:
                    dest.unlink(missing_ok=True)
            shutil.move(str(child), str(dest))

        home = root / ".dsh"
        ok_home, _ = init_dsh_home(home)
        if not ok_home:
            return False, "无法创建 DSH 数据目录"

        # 官方：仅核心；预制：补必备并保留用户已装（升级禁洗空）
        _ensure_profile_flavor(home, f)
        if plugin_snap:
            try:
                from services.harness_plugins import merge_profile_plugins

                ok_m, msg_m = merge_profile_plugins(home, plugin_snap, flavor=f)
                if not ok_m:
                    logger.warning("merge plugins after flavor: %s", msg_m)
            except Exception as exc:
                logger.warning("merge plugins failed: %s", exc)

        plugins = _profile_extra_plugins(home) if f == FLAVOR_PREFAB else []
        write_manifest(
            root,
            flavor=f,
            version=str(spec.get("version") or ""),
            plugins=plugins,
            extra={"sha256": digest, "plugin_snapshot_count": len((plugin_snap or {}).get("dependencies") or {})},
        )

        prog(STAGE_LABELS[STAGE_DONE], 100, STAGE_DONE)
        n_ext = len((plugin_snap or {}).get("dependencies") or {})
        extra = f"（已保留升级前 {n_ext} 个扩展依赖）" if n_ext else ""
        return True, f"「{label}」已安装到本机{extra}，请保存 API Key 后启动服务"
    except InstallCancelled:
        return False, "已取消安装"
    except OSError as exc:
        from services.harness_plugins import _friendly_os_error

        return False, _friendly_os_error(exc)
    except Exception as exc:
        logger.exception("install_prefab_bundle failed")
        return False, str(exc) or exc.__class__.__name__
    finally:
        if staging is not None and staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)


def _profile_extra_plugins(home: Path) -> list[str]:
    """读 web profile 中非核心 bundles（写 MANIFEST.plugins 用）。"""
    pkg = home / "profiles" / "web" / "package.json"
    if not pkg.is_file():
        return []
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = ((data.get("dsh") or {}).get("profile") or {}).get("bundles") or []
    core = set(CORE_BUNDLES)
    out: list[str] = []
    for b in raw:
        name = str(b).strip()
        if name and name not in core and name not in out:
            out.append(name)
    return out


def _ensure_profile_flavor(home: Path, flavor: str) -> None:
    """官方版强制仅核心；预制版补齐核心+必备，并保留用户已装插件。

    覆盖升级时 ``prefab_essential_plugins`` 为空绝不能把已有扩展洗成只剩核心
    （2026-09-14 事故：MANIFEST/profile 被写成 plugins=[]）。
    """
    pkg = home / "profiles" / "web" / "package.json"
    try:
        data: dict[str, Any]
        if pkg.is_file():
            data = json.loads(pkg.read_text(encoding="utf-8"))
        else:
            data = {
                "name": "dsh-profile-web",
                "private": True,
                "dependencies": {},
                "dsh": {"profile": {"bundles": list(CORE_BUNDLES)}},
            }
        dsh_block = data.setdefault("dsh", {})
        profile = dsh_block.setdefault("profile", {})
        bundles = list(profile.get("bundles") or [])
        kept: list[str] = []
        for core in CORE_BUNDLES:
            if core not in kept:
                kept.append(core)
        if normalize_flavor(flavor) == FLAVOR_PREFAB:
            # 保留用户已装；再并上配置里的必备白名单（可为空）
            for b in bundles:
                name = str(b).strip()
                if name and name not in kept:
                    kept.append(name)
            for name in essential_plugins():
                if name and name not in kept:
                    kept.append(name)
        profile["bundles"] = kept
        pkg.parent.mkdir(parents=True, exist_ok=True)
        pkg.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ensure profile flavor: %s", exc)


def make_cancel_event() -> tuple[threading.Event, CancelFn]:
    ev = threading.Event()

    def _check() -> bool:
        return ev.is_set()

    return ev, _check
