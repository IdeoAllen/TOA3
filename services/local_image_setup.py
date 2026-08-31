# -*- coding: utf-8 -*-
"""本机生图 · 一键安装：扫描 ComfyUI、迁移、在线下载。"""
from __future__ import annotations

import fnmatch
import logging
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from services.config_service import project_root

logger = logging.getLogger("TOA3.local_image_setup")

ProgressFn = Callable[[str, int, int], None]

_BUNDLE_PATH = project_root() / "config" / "local_image_bundle.yml"


def _noop_progress(msg: str, cur: int = 0, total: int = 0) -> None:
    del msg, cur, total


def load_bundle_config() -> dict[str, Any]:
    try:
        import yaml

        if _BUNDLE_PATH.is_file():
            data = yaml.safe_load(_BUNDLE_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("load bundle config: %s", exc)
    return {}


def _file_ok(path: Path, min_bytes: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= min_bytes
    except OSError:
        return False


def discover_comfyui_roots(*, max_depth: int = 6) -> list[Path]:
    """查找本机 ComfyUI models 根目录。"""
    found: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        p = p.resolve()
        key = str(p).lower()
        if key in seen or not p.is_dir():
            return
        seen.add(key)
        found.append(p)

    for env_key in ("COMFYUI_PATH", "COMFYUI_MODELS", "COMFYUI_ROOT"):
        raw = (os.environ.get(env_key) or "").strip()
        if not raw:
            continue
        base = Path(raw).expanduser()
        if base.name.lower() == "models" and base.is_dir():
            _add(base)
        elif (base / "models").is_dir():
            _add(base / "models")
        elif base.is_dir():
            _add(base)

    seeds = [
        Path.home() / "ComfyUI" / "models",
        Path.home() / "ComfyUI",
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path("C:/ComfyUI/models"),
        Path("C:/ComfyUI"),
        Path("D:/ComfyUI/models"),
        Path("D:/ComfyUI"),
    ]
    for seed in seeds:
        if seed.is_dir():
            if seed.name.lower() == "models":
                _add(seed)
            elif (seed / "models").is_dir():
                _add(seed / "models")
            elif seed.name.lower() == "comfyui" and (seed / "models").is_dir():
                _add(seed / "models")

    # 仅在 Desktop / Documents 浅层找 ComfyUI（避免全盘扫描卡 UI）
    for base in (Path.home() / "Desktop", Path.home() / "Documents"):
        for hit in _find_comfy_models_dirs(base, depth=4):
            _add(hit)
    return found


def _find_comfy_models_dirs(base: Path, depth: int = 4) -> list[Path]:
    if depth < 0 or not base.is_dir():
        return []
    out: list[Path] = []
    if base.name.lower() == "comfyui" and (base / "models").is_dir():
        out.append((base / "models").resolve())
    if depth <= 0:
        return out
    try:
        for child in base.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                out.extend(_find_comfy_models_dirs(child, depth - 1))
    except OSError:
        pass
    return out


def _best_in_dirs(
    roots: list[Path],
    dir_names: list[str],
    *,
    patterns: list[str],
    min_bytes: int,
) -> tuple[Path | None, list[str]]:
    """在 ComfyUI 子目录中找最大且满足 min_bytes 的文件。"""
    issues: list[str] = []
    best: Path | None = None
    best_size = 0
    for root in roots:
        for dname in dir_names:
            base = root / dname if (root / dname).is_dir() else root
            if not base.is_dir():
                continue
            try:
                for p in base.rglob("*"):
                    if not p.is_file():
                        continue
                    name = p.name.lower()
                    if not any(fnmatch.fnmatch(name, pat.lower()) for pat in patterns):
                        continue
                    try:
                        size = p.stat().st_size
                    except OSError:
                        continue
                    if size < min_bytes:
                        issues.append(
                            f"{p.name} 不完整（{size // (1024 * 1024)}MB，需 ≥{min_bytes // (1024 * 1024)}MB）"
                        )
                        continue
                    if size > best_size:
                        best = p
                        best_size = size
            except OSError:
                continue
    return best, issues


_SCAN_CACHE: dict[str, Any] | None = None


def scan_local_assets(*, force: bool = False) -> dict[str, Any]:
    """扫描 ComfyUI + TOA 目录，返回可迁移资源。"""
    global _SCAN_CACHE
    if _SCAN_CACHE is not None and not force:
        return _SCAN_CACHE
    from services.local_image_runtime import (
        find_diffusion_model,
        find_text_encoder,
        find_vae,
        install_status,
        weights_root,
    )

    cfg = load_bundle_config()
    scan = cfg.get("comfyui_scan") or {}
    comfy_roots = discover_comfyui_roots()
    st = install_status()

    result: dict[str, Any] = {
        "comfy_roots": [str(p) for p in comfy_roots],
        "weights_dir": str(weights_root()),
        "ready": bool(st.get("ready")),
        "missing": list(st.get("missing") or []),
        "issues": [],
        "candidates": {},
    }

    if st.get("ready"):
        result["candidates"] = {
            "diffusion": st.get("diffusion"),
            "vae": st.get("vae"),
            "text_encoder": st.get("text_encoder"),
            "source": "toa",
        }
        _SCAN_CACHE = result
        return result

    # 已在 TOA 目录
    diff = find_diffusion_model()
    vae = find_vae()
    text = find_text_encoder()
    if diff and vae and text:
        result["candidates"] = {
            "diffusion": str(diff),
            "vae": str(vae),
            "text_encoder": str(text),
            "source": "toa_partial",
        }
        _SCAN_CACHE = result
        return result

    if not comfy_roots:
        result["issues"].append("未找到 ComfyUI 模型目录，可直接「一键下载」。")
        _SCAN_CACHE = result
        return result

    vae_dirs = list(scan.get("vae_dirs") or ["vae"])
    text_dirs = list(scan.get("text_dirs") or ["text_encoders", "clip", "clip_gguf"])
    diff_dirs = list(scan.get("diffusion_dirs") or ["unet", "diffusion_models", "checkpoints"])

    vae_hit, vae_issues = _best_in_dirs(
        comfy_roots, vae_dirs, patterns=["ae.safetensors", "ae.sft"], min_bytes=300_000_000
    )
    diff_hit, diff_issues = _best_in_dirs(
        comfy_roots,
        diff_dirs,
        patterns=["z_image*.gguf", "z-image*.gguf"],
        min_bytes=2_500_000_000,
    )
    if diff_hit is None:
        d2, d2_issues = _best_in_dirs(
            comfy_roots,
            diff_dirs,
            patterns=["z_image*turbo*.safetensors", "z_image*bf16*.safetensors"],
            min_bytes=10_000_000_000,
        )
        diff_hit = d2
        diff_issues.extend(d2_issues)

    text_hit, text_issues = _best_in_dirs(
        comfy_roots,
        text_dirs,
        patterns=["Qwen3*.gguf", "qwen*.gguf"],
        min_bytes=1_500_000_000,
    )
    if text_hit is None:
        t2, t2_issues = _best_in_dirs(
            comfy_roots,
            text_dirs,
            patterns=["qwen_3_4b*.safetensors", "qwen*.safetensors"],
            min_bytes=7_000_000_000,
        )
        text_hit = t2
        text_issues.extend(t2_issues)

    result["issues"].extend(vae_issues[:2])
    result["issues"].extend(diff_issues[:2])
    result["issues"].extend(text_issues[:2])

    if vae_hit or diff_hit or text_hit:
        result["candidates"] = {
            "diffusion": str(diff_hit) if diff_hit else "",
            "vae": str(vae_hit) if vae_hit else "",
            "text_encoder": str(text_hit) if text_hit else "",
            "source": "comfyui",
        }
    _SCAN_CACHE = result
    return result


def _link_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return
    try:
        if dest.exists():
            dest.unlink()
        os.link(src, dest)
        return
    except OSError:
        pass
    shutil.copy2(src, dest)


def migrate_to_toa(candidates: dict[str, Any]) -> tuple[bool, str]:
    """把扫描到的模型放进 TOA 统一目录（优先硬链接，省磁盘）。"""
    from services.local_image_runtime import install_status, weights_root, write_manifest

    dst = weights_root()
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    mapping: dict[str, str] = {}

    for role in ("diffusion", "vae", "text_encoder"):
        raw = str(candidates.get(role) or "").strip()
        if not raw:
            continue
        src = Path(raw)
        if not src.is_file():
            continue
        dest = dst / src.name
        _link_or_copy(src, dest)
        mapping[role] = src.name
        copied += 1

    if copied:
        write_manifest(
            {
                "source": str(candidates.get("source") or "migrate"),
                "files": mapping,
            }
        )

    st = install_status()
    if st.get("ready"):
        return True, f"已就绪：模型在 {dst}，可到媒体工坊生图。"
    miss = "、".join(st.get("missing") or []) or "组件"
    if copied:
        return False, f"已迁移 {copied} 个文件，仍缺 {miss}。可点「一键下载」补齐。"
    return False, "未找到可用模型文件。请用「一键下载」。"


def _download_file(
    url: str,
    dest: Path,
    *,
    progress: ProgressFn,
    label: str,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "TOA3-local-image/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        chunk = 1024 * 256
        last_pct = -1
        with tmp.open("wb") as out:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if total > 0:
                    pct = int(done * 100 / total)
                    if pct != last_pct and (pct % 2 == 0 or done == total):
                        progress(f"正在下载 {label}…", done, total)
                        last_pct = pct
                elif done % (50 * 1024 * 1024) < chunk:
                    progress(f"正在下载 {label}…", done, 0)
    if tmp.stat().st_size < 1024:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"下载失败：{label}")
    tmp.replace(dest)


def _extract_zip(zip_path: Path, dest_dir: Path, *, progress: ProgressFn) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        total = len(names) or 1
        for i, name in enumerate(names):
            progress(f"正在解压运行时… ({i + 1}/{total})", i + 1, total)
            zf.extract(name, dest_dir)


def download_runtime(
    profile: str = "win_cuda12",
    *,
    progress: ProgressFn | None = None,
) -> tuple[bool, str]:
    from services.local_image_runtime import find_sd_binary, runtime_root, write_manifest

    prog = progress or _noop_progress
    cfg = load_bundle_config()
    rt_cfg = (cfg.get("runtime") or {}).get(profile) or {}
    zips = rt_cfg.get("zips") or []
    if not zips:
        return False, "未配置运行时下载地址。"

    root = runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        for i, item in enumerate(zips):
            url = str(item.get("url") if isinstance(item, dict) else item or "").strip()
            if not url:
                continue
            zp = tdir / f"rt_{i}.zip"
            prog(f"正在下载运行时 ({i + 1}/{len(zips)})…", 0, 0)
            _download_file(url, zp, progress=prog, label="运行时")
            _extract_zip(zp, root, progress=prog)

    if find_sd_binary() is None:
        return False, "运行时解压完成但未找到 sd-cli，请换 CPU 模式重试。"
    man = {"runtime_profile": profile, "source": "download"}
    write_manifest(man)
    return True, "本机生图程序已装好。"


def download_model_bundle(
    bundle_id: str = "balanced",
    *,
    progress: ProgressFn | None = None,
) -> tuple[bool, str]:
    from services.local_image_runtime import install_status, weights_root, write_manifest

    prog = progress or _noop_progress
    cfg = load_bundle_config()
    bundle = (cfg.get("bundles") or {}).get(bundle_id)
    if not bundle:
        return False, f"未知档位：{bundle_id}"

    dst = weights_root()
    dst.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}

    for role in ("diffusion", "text_encoder", "vae"):
        spec = bundle.get(role) or {}
        if not isinstance(spec, dict):
            continue
        filename = str(spec.get("filename") or "").strip()
        url = str(spec.get("url") or "").strip()
        min_bytes = int(spec.get("min_bytes") or 0)
        if not filename or not url:
            continue
        target = dst / filename
        if _file_ok(target, min_bytes):
            copied[role] = filename
            continue
        _download_file(url, target, progress=prog, label=filename)
        if not _file_ok(target, min_bytes):
            target.unlink(missing_ok=True)
            return False, f"下载不完整：{filename}，请检查网络后重试。"
        copied[role] = filename

    write_manifest(
        {
            "source": "download",
            "bundle": bundle_id,
            "quant": bundle.get("quant"),
            "label": bundle.get("label"),
            "files": copied,
        }
    )
    st = install_status()
    if st.get("ready"):
        return True, "模型已下载完成，可到媒体工坊生图。"
    miss = "、".join(st.get("missing") or [])
    return False, f"模型已下载，仍缺：{miss}"


def one_click_setup(
    bundle_id: str = "balanced",
    *,
    runtime_profile: str = "win_cuda12",
    try_migrate_first: bool = True,
    progress: ProgressFn | None = None,
) -> tuple[bool, str]:
    """小白主路径：先迁移本机已有 → 下载缺的模型 → 下载运行时。"""
    global _SCAN_CACHE
    _SCAN_CACHE = None
    from services.local_image_runtime import find_sd_binary, install_status

    prog = progress or _noop_progress
    messages: list[str] = []

    if try_migrate_first:
        prog("正在查找本机已有模型…", 0, 0)
        scan = scan_local_assets()
        cands = scan.get("candidates") or {}
        if cands.get("diffusion") or cands.get("vae") or cands.get("text_encoder"):
            ok, msg = migrate_to_toa(cands)
            messages.append(msg)
            if ok:
                return True, msg

    st = install_status()
    missing = set(st.get("missing") or [])
    need_weights = bool(
        missing & {"生图模型文件", "画面还原组件（VAE）", "文字理解组件"}
    )
    if need_weights:
        prog("正在下载推荐模型包（体积较大，请耐心等待）…", 0, 0)
        ok, msg = download_model_bundle(bundle_id, progress=prog)
        messages.append(msg)
        st = install_status()
        if not st.get("ready") and "生图模型文件" in (st.get("missing") or []):
            return False, msg

    if find_sd_binary() is None:
        prog("正在下载本机生图程序…", 0, 0)
        ok, msg = download_runtime(runtime_profile, progress=prog)
        messages.append(msg)
        if not ok:
            return False, msg

    st = install_status()
    if st.get("ready"):
        return True, "本机生图已就绪，去媒体工坊写一句话即可出图。"
    miss = "、".join(st.get("missing") or [])
    return False, "；".join(messages) or f"仍缺：{miss}"


def find_diffusion_model_ready(st: dict[str, Any] | None = None) -> bool:
    from services.local_image_runtime import find_diffusion_model, install_status

    s = st or install_status()
    return bool(s.get("diffusion") or find_diffusion_model())


def find_vae_text_ready(st: dict[str, Any] | None = None) -> bool:
    from services.local_image_runtime import find_text_encoder, find_vae, install_status

    s = st or install_status()
    return bool((s.get("vae") or find_vae()) and (s.get("text_encoder") or find_text_encoder()))


def auto_find_and_migrate(*, progress: ProgressFn | None = None) -> tuple[bool, str]:
    global _SCAN_CACHE
    _SCAN_CACHE = None
    prog = progress or _noop_progress
    prog("正在扫描 ComfyUI 与本机目录…", 0, 0)
    scan = scan_local_assets()
    if scan.get("ready"):
        return True, "本机生图已就绪。"
    cands = scan.get("candidates") or {}
    if not any(cands.get(k) for k in ("diffusion", "vae", "text_encoder")):
        issues = scan.get("issues") or []
        hint = issues[0] if issues else "未找到完整模型，请用「一键下载」。"
        return False, hint
    return migrate_to_toa(cands)


def status_summary() -> str:
    scan = scan_local_assets()
    st_lines: list[str] = []
    if scan.get("ready"):
        return "本机生图：已就绪 · 可直接去媒体工坊"
    miss = scan.get("missing") or []
    if miss:
        st_lines.append("缺少：" + "、".join(miss))
    roots = scan.get("comfy_roots") or []
    if roots:
        st_lines.append(f"已发现 ComfyUI：{len(roots)} 处")
    issues = scan.get("issues") or []
    if issues:
        st_lines.append(issues[0])
    if not st_lines:
        st_lines.append("点「一键下载并安装」即可，无需自己找模型。")
    return " · ".join(st_lines)
