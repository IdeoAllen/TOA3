#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOA3 Windows 打包脚本（对齐 TOA2 packaging-app/build_windows.py）。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

PACKAGING_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGING_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PACKAGING_DIR))

from app.version import APP_NAME, APP_VERSION  # noqa: E402
from release_config_guard import (  # noqa: E402
    FORBIDDEN_RELEASE_NAMES,
    RELEASE_CONFIG_OVERRIDES,
    assert_release_tree_safe,
    make_release_assets_ignore,
    scan_project_config_before_release,
    shipped_override_path,
)

APP_EXE = APP_NAME  # TOA3.exe
APP_DISPLAY = "TOA3-运营宝"
RELEASE_DIR_NAME = f"{APP_NAME}-v{APP_VERSION}-win64"
DEV_DIR_NAME = f"{APP_NAME}-Dev-v{APP_VERSION}-win64"
SETUP_BASENAME = f"{APP_NAME}-Setup-v{APP_VERSION}"
DEV_SETUP_BASENAME = f"{APP_NAME}-Dev-Setup-v{APP_VERSION}"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


def verify_release_artifacts(
    release_dir: Path,
    *,
    setup_path: Path | None,
    setup_basename: str,
    profile: str,
) -> bool:
    """校验打包产物内版本与 app/version.py 一致，并写入发版记录。"""
    marker_name = "BUILD_PROFILE.dev" if profile == "dev" else "BUILD_PROFILE.release"
    marker = release_dir / "config" / marker_name
    if marker.is_file():
        for line in marker.read_text(encoding="utf-8").splitlines():
            if line.startswith("version="):
                found = line.split("=", 1)[1].strip()
                if found != APP_VERSION:
                    log(
                        f"错误: {marker_name} 版本 {found} ≠ app/version.py {APP_VERSION}"
                    )
                    return False
                break
        else:
            log(f"错误: {marker_name} 缺少 version= 行")
            return False

    readme = release_dir / "README.txt"
    if not readme.is_file() or APP_VERSION not in readme.read_text(encoding="utf-8"):
        log(f"错误: README.txt 未包含版本 {APP_VERSION}")
        return False

    if APP_VERSION not in release_dir.name:
        log(f"错误: 发布目录名未含版本 {APP_VERSION}: {release_dir.name}")
        return False

    if setup_path is not None:
        setup_name = Path(setup_path).name
        if APP_VERSION not in setup_name:
            log(f"错误: 安装包文件名未含版本 {APP_VERSION}: {setup_name}")
            return False

    record_path = PACKAGING_DIR / "dist" / "release_record.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "app_version": APP_VERSION,
        "profile": profile,
        "release_dir": release_dir.name,
        "setup_basename": setup_basename,
        "setup_path": str(setup_path) if setup_path else None,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"发版记录: {record_path} (version={APP_VERSION})")
    return True


def collect_menu_hidden_imports() -> list[str]:
    config_path = PROJECT_DIR / "config" / "app.yml"
    imports: set[str] = set()
    if not config_path.is_file():
        return []

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    for item in (config.get("menu") or {}).get("menu_items") or []:
        module_path = item.get("module_path")
        if not module_path:
            continue
        imports.add(module_path)
        parts = module_path.split(".")
        for i in range(2, len(parts)):
            imports.add(".".join(parts[:i]))

    imports.update(
        {
            "app",
            "core",
            "services",
            "widgets",
            "modules",
            "PySide6.QtUiTools",
            "PySide6.QtSvg",
            "PySide6.QtWebEngineWidgets",
            "PySide6.QtWebEngineCore",
            "PySide6.QtMultimedia",
            "PySide6.QtMultimediaWidgets",
            "fitz",
            "pymupdf",
            "pdf2image",
        }
    )
    return sorted(imports)


def collect_frozen_hidden_imports() -> list[str]:
    """PyInstaller 易漏的懒加载模块（系统设置 section、Harness 等）。"""
    sections_dir = PROJECT_DIR / "modules" / "system_settings"
    out: list[str] = [
        "modules.system_settings.settings_page",
        "modules.harness_agent.harness_agent_page",
        "modules.harness_agent.setup_gate",
        "modules.harness_agent.feed_strip",
        "modules.harness_agent.web_host",
    ]
    if sections_dir.is_dir():
        for py in sections_dir.glob("*.py"):
            if py.name.startswith("_"):
                continue
            out.append(f"modules.system_settings.{py.stem}")
    return out


def find_iscc() -> str | None:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def write_clean_license(dst_path: Path) -> None:
    payload = {
        "is_licensed": False,
        "license_key": "",
        "expire_date": None,
        "features": [],
        "user_name": "",
        "company": "",
        "phone": "",
        "role": "",
        "machine_id": "",
        "bound_machine_id": "",
        "issue_date": None,
        "license_type": "unlicensed",
        "authorized_users": [],
        "activated_code_id": "",
        "schema_ver": 2,
    }
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_iss_utf8_bom(iss_path: Path) -> None:
    raw = iss_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return
    text = raw.decode("utf-8-sig")
    iss_path.write_text(text, encoding="utf-8-sig", newline="\r\n")


def ensure_brand_assets() -> None:
    script = PROJECT_DIR / "scripts" / "gen_toa3_brand_icon.py"
    if script.is_file():
        log("生成 TOA3 品牌图标（正式版 + 开发版）...")
        subprocess.run([sys.executable, str(script)], cwd=PROJECT_DIR, check=False)


def _copy_release_config_tree(cfg_src: Path, cfg_dst: Path, *, is_dev: bool) -> None:
    ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        "~$*",
        ".DS_Store",
        "Thumbs.db",
        "admin_bootstrap_code.txt",
        "license.json",
    )
    skip_names = set(FORBIDDEN_RELEASE_NAMES)
    if is_dev:
        skip_names.discard("app.dev.yml")
    cfg_dst.mkdir(parents=True, exist_ok=True)
    for item in cfg_src.iterdir():
        if item.name in skip_names:
            continue
        if not is_dev and item.name in RELEASE_CONFIG_OVERRIDES:
            override = shipped_override_path(PACKAGING_DIR, item.name)
            if override is not None:
                shutil.copy2(override, cfg_dst / item.name)
                log(f"发版 config 使用模板: {item.name}")
                continue
            log(f"警告: 缺少发版模板 shipped_config/{item.name}")
        if item.is_dir():
            shutil.copytree(item, cfg_dst / item.name, ignore=ignore)
        elif item.is_file():
            shutil.copy2(item, cfg_dst / item.name)


def prepare_release_staging(build_dir: Path, *, is_dev: bool) -> Path | None:
    """正式版：PyInstaller 嵌入资源用干净 config/assets（不含模型清单与 Comfy 样例）。"""
    if is_dev:
        return None
    staging = build_dir / "release_staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        "~$*",
        ".DS_Store",
        "Thumbs.db",
    )
    _copy_release_config_tree(PROJECT_DIR / "config", staging / "config", is_dev=False)
    assets_src = PROJECT_DIR / "assets"
    if assets_src.is_dir():
        shutil.copytree(
            assets_src,
            staging / "assets",
            ignore=make_release_assets_ignore(assets_src),
        )
    for folder in ("resources", "avatars", "ui", "vendor"):
        src = PROJECT_DIR / folder
        if src.is_dir():
            shutil.copytree(src, staging / folder, ignore=ignore)
    return staging


def resolve_packaging_icon(*, is_dev: bool) -> Path | None:
    if is_dev:
        candidates = (
            PROJECT_DIR / "avatars" / "logo_dev.ico",
            PROJECT_DIR / "resources" / "icons" / "app_logo_dev.ico",
        )
    else:
        candidates = (
            PROJECT_DIR / "avatars" / "logo.ico",
            PROJECT_DIR / "resources" / "icons" / "app_logo.ico",
        )
    for path in candidates:
        if path.is_file():
            return path
    return None


def promote_dev_brand_assets(release_dir: Path) -> None:
    """开发版安装包内快捷方式仍引用 avatars/logo.*，覆盖为 DEV 配色。"""
    pairs = (
        ("logo_dev.ico", "logo.ico"),
        ("logo_dev.png", "logo.png"),
    )
    avatars = release_dir / "avatars"
    icons = release_dir / "resources" / "icons"
    for src_name, dst_name in pairs:
        src = avatars / src_name
        if src.is_file():
            shutil.copy2(src, avatars / dst_name)
    icon_pairs = (
        ("app_logo_dev.ico", "app_logo.ico"),
        ("app_logo_dev.png", "app_logo.png"),
        ("brand_logo_dev.png", "brand_logo.png"),
    )
    for src_name, dst_name in icon_pairs:
        src = icons / src_name
        if src.is_file():
            shutil.copy2(src, icons / dst_name)


def preflight(profile: str = "release", *, skip_verify: bool = False) -> bool:
    if skip_verify:
        log("跳过 MVP 验收（--skip-verify）")
    else:
        log("运行 MVP 验收 ...")
        try:
            result = subprocess.run(
                [sys.executable, str(PROJECT_DIR / "scripts" / "verify_mvp.py")],
                cwd=PROJECT_DIR,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            log("MVP 验收超时（>180s），中止打包")
            return False
        if result.returncode != 0:
            log("MVP 验收失败，中止打包")
            return False

    if profile == "release":
        release_cfg = PROJECT_DIR / "config" / "app.release.yml"
        if release_cfg.is_file():
            data = yaml.safe_load(release_cfg.read_text(encoding="utf-8")) or {}
            if (data.get("auth") or {}).get("skip_login"):
                log("错误: app.release.yml 仍开启 skip_login")
                return False
        pre_errs = scan_project_config_before_release(PROJECT_DIR, PACKAGING_DIR)
        if pre_errs:
            for err in pre_errs:
                log(f"发版门禁: {err}")
            return False
        log("发版门禁: shipped_config 模板已就绪（integrations/harness/模型清单用干净默认）")
    elif profile == "dev":
        dev_cfg = PROJECT_DIR / "config" / "app.dev.yml"
        if not dev_cfg.is_file():
            log("错误: 开发版打包需要 config/app.dev.yml")
            return False
        if not (dev_cfg.read_text(encoding="utf-8") or "").strip():
            log("错误: app.dev.yml 为空")
            return False
    else:
        log(f"错误: 未知 profile={profile}，请用 release 或 dev")
        return False
    return True


def build_inno_setup(
    release_dir: Path | None = None,
    *,
    setup_basename: str = SETUP_BASENAME,
    release_dir_name: str = RELEASE_DIR_NAME,
    is_dev: bool = False,
) -> str | None:
    dist_dir = PACKAGING_DIR / "dist"
    release_dir = release_dir or (dist_dir / release_dir_name)
    if not release_dir.is_dir():
        log(f"未找到发布目录，跳过 Setup: {release_dir}")
        return None

    iscc = find_iscc()
    if not iscc:
        log("未找到 Inno Setup (ISCC.exe)，跳过 setup.exe 构建")
        return None

    iss = PACKAGING_DIR / "toa3_setup.iss"
    if not iss.is_file():
        log(f"未找到 Inno 脚本: {iss}")
        return None

    ensure_iss_utf8_bom(iss)
    setup_icon = (
        r"..\avatars\logo_dev.ico"
        if is_dev
        else r"..\avatars\logo.ico"
    )
    log(f"开始构建 Inno Setup 安装包 ({setup_basename}) ...")
    result = subprocess.run(
        [
            iscc,
            f"/DSetupBaseName={setup_basename}",
            f"/DMyAppVersion={APP_VERSION}",
            f"/DMyReleaseDir={release_dir_name}",
            f"/DSetupIconFile={setup_icon}",
            str(iss),
        ],
        cwd=PACKAGING_DIR,
    )
    if result.returncode != 0:
        log("Inno Setup 构建失败")
        return None

    setup_exe = dist_dir / f"{setup_basename}.exe"
    if not setup_exe.is_file():
        log(f"未找到生成的 setup.exe: {setup_exe}")
        return None
    log(f"Setup 安装包: {setup_exe}")
    return str(setup_exe)


def build(
    onefile: bool = True,
    clean: bool = False,
    msi: bool = False,
    *,
    profile: str = "release",
    skip_verify: bool = False,
) -> bool:
    profile = (profile or "release").strip().lower()
    is_dev = profile == "dev"
    release_dir_name = DEV_DIR_NAME if is_dev else RELEASE_DIR_NAME
    setup_basename = DEV_SETUP_BASENAME if is_dev else SETUP_BASENAME

    if not preflight(profile, skip_verify=skip_verify):
        return False

    log(f"打包配置 profile={profile} → {release_dir_name}")

    ensure_brand_assets()

    dist_dir = PACKAGING_DIR / "dist"
    build_dir = PACKAGING_DIR / "build"
    dist_dir.mkdir(parents=True, exist_ok=True)
    release_staging = prepare_release_staging(build_dir, is_dev=is_dev)

    if clean:
        for path in (build_dir, dist_dir):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        dist_dir.mkdir(parents=True, exist_ok=True)

    main_script = PROJECT_DIR / "app" / "main.py"
    icon_path = resolve_packaging_icon(is_dev=is_dev)
    if icon_path is not None:
        log(f"打包图标: {icon_path.name} ({'开发版' if is_dev else '正式版'})")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(main_script),
        "--name",
        APP_EXE,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir / "pyi_work"),
        "--specpath",
        str(PACKAGING_DIR),
        "--paths",
        str(PROJECT_DIR),
        "--noconfirm",
        "--windowed",
        "--collect-submodules",
        "PySide6",
        "--collect-submodules",
        "app",
        "--collect-submodules",
        "core",
        "--collect-submodules",
        "services",
        "--collect-submodules",
        "widgets",
        "--collect-submodules",
        "modules",
        "--collect-submodules",
        "pandas._libs",
        "--collect-binaries",
        "pandas",
        "--exclude-module",
        "torch",
        "--exclude-module",
        "torchvision",
        "--exclude-module",
        "torchaudio",
    ]
    rth = PACKAGING_DIR / "pyi_rth_qtwebengine.py"
    if rth.is_file():
        cmd.extend(["--runtime-hook", str(rth)])
    cmd.extend(["--collect-all", "PySide6"])
    if onefile:
        cmd.append("--onefile")
    if icon_path is not None and icon_path.is_file():
        cmd.extend(["--icon", str(icon_path)])

    data_pairs = [
        ("config", "config"),
        ("resources", "resources"),
        ("assets", "assets"),
        ("avatars", "avatars"),
        ("ui", "ui"),
        ("vendor", "vendor"),
    ]
    for src, dest in data_pairs:
        src_path = PROJECT_DIR / src
        if release_staging is not None and (release_staging / dest).exists():
            src_path = release_staging / dest
        elif not src_path.exists():
            continue
        if src_path.exists():
            cmd.extend(["--add-data", f"{src_path}{os.pathsep}{dest}"])

    hidden_imports = [
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtUiTools",
        "PySide6.QtSvg",
        "PIL",
        "pandas",
        "openpyxl",
        "pptx",
        "docx",
        "reportlab",
        "PyPDF2",
        "pypdf",
        "yaml",
        "cv2",
        "numpy",
        "pytesseract",
        "fitz",
        *collect_menu_hidden_imports(),
        *collect_frozen_hidden_imports(),
    ]
    for item in sorted(set(hidden_imports)):
        cmd.extend(["--hidden-import", item])

    log(f"开始打包 {APP_NAME} v{APP_VERSION} ...")
    result = subprocess.run(cmd, cwd=PACKAGING_DIR)
    if result.returncode != 0:
        log("打包失败")
        return False

    release_dir = dist_dir / release_dir_name
    release_dir.mkdir(parents=True, exist_ok=True)

    exe_name = f"{APP_EXE}.exe"
    exe_src = dist_dir / exe_name
    onedir_src = dist_dir / APP_EXE
    if onefile and exe_src.is_file():
        shutil.copy2(exe_src, release_dir / exe_name)
    elif onedir_src.is_dir():
        for item in onedir_src.iterdir():
            dest = release_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
    elif exe_src.is_file():
        shutil.copy2(exe_src, release_dir / exe_name)

    for folder in ("config", "resources", "assets", "avatars", "ui", "vendor"):
        src = PROJECT_DIR / folder
        dst = release_dir / folder
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        ignore = shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "~$*",
            ".DS_Store",
            "Thumbs.db",
            "admin_bootstrap_code.txt",
            "license.json",
        )
        if folder == "config":
            _copy_release_config_tree(src, dst, is_dev=is_dev)
            marker = dst / ("BUILD_PROFILE.dev" if is_dev else "BUILD_PROFILE.release")
            marker.write_text(f"profile={profile}\nversion={APP_VERSION}\n", encoding="utf-8")
        elif folder == "assets" and not is_dev:
            shutil.copytree(src, dst, ignore=make_release_assets_ignore(src))
        else:
            shutil.copytree(src, dst, ignore=ignore)

    if is_dev:
        promote_dev_brand_assets(release_dir)
        log("开发版：已覆盖 avatars/logo.* 为 DEV 配色（任务栏 / 快捷方式可辨）")

    write_clean_license(release_dir / "config" / "license.json")

    if not is_dev:
        try:
            assert_release_tree_safe(release_dir)
            log("发版门禁: 发布目录无密钥 / data/user / 个人路径")
        except RuntimeError as exc:
            log(str(exc))
            return False

    profile_label = "开发版（含 app.dev.yml · 自动登录赵成）" if is_dev else "基础版入口 + 授权码 / 正式版开通"
    readme = release_dir / "README.txt"
    readme.write_text(
        f"TOA3 赋能培训运营助手（运营宝）· {profile_label}\n"
        f"版本: {APP_VERSION}\n"
        f"构建: {profile}\n\n"
        f"请通过正式安装包安装：\n"
        f"  {setup_basename}.exe\n\n"
        + (
            "开发版：默认 skip_login，恢复本机赵成全功能授权；勿对外分发。\n"
            if is_dev
            else "首次启动：有授权码点「授权码登录」；没有就点「进入软件」（基础版，可离线使用记事/截图/剪贴板等）。\n"
            "正式版：在软件内选择产品方案一键开通，或粘贴运营台签发的授权码。\n"
            "升级安装不会删除「系统设置 → 扩展」里你自己做的功能。\n"
        )
        + "授权到期或被停用后，无需卸载，重新申请新码激活即可。\n"
        "默认不需要管理员权限；如需装到 Program Files 可在向导中选择提升。\n"
        "卸载: Windows「应用和功能」或开始菜单 Uninstall TOA3。\n"
        "与 TOA2 可并存（安装目录 %LOCALAPPDATA%\\Programs\\TOA3）。\n",
        encoding="utf-8",
    )

    archive = shutil.make_archive(str(dist_dir / release_dir_name), "zip", release_dir)
    log(f"发布目录: {release_dir}")
    log(f"ZIP 归档: {archive}")

    setup_path = None
    if msi:
        setup_path = build_inno_setup(
            release_dir,
            setup_basename=setup_basename,
            release_dir_name=release_dir_name,
            is_dev=is_dev,
        )
        if not setup_path:
            log("错误: 未生成 setup.exe。请安装 Inno Setup 6 后重试（winget install JRSoftware.InnoSetup）")
            return False

    try:
        from make_upgrade_launcher import write_upgrade_scripts

        outs = write_upgrade_scripts(str(dist_dir), APP_VERSION, APP_EXE)
        for p in outs:
            log(f"产品入口: {p}")
    except Exception as e:
        log(f"生成安装/升级/卸载入口失败: {e}")

    if msi and setup_path:
        log(f"正式安装包（请分发这个）: {setup_path}")

    if not verify_release_artifacts(
        release_dir,
        setup_path=setup_path,
        setup_basename=setup_basename,
        profile=profile,
    ):
        return False

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--onedir", action="store_true")
    parser.add_argument("--msi", action="store_true", help="打包完成后生成 Setup.exe")
    parser.add_argument("--setup-only", action="store_true", help="仅基于已有 release 目录生成 Setup.exe")
    parser.add_argument(
        "--profile",
        choices=("release", "dev"),
        default="release",
        help="release=正式单机版（默认）；dev=内部开发版（含 app.dev.yml）",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="跳过 scripts/verify_mvp.py（CI/本地加速；发版前建议至少手动跑一次）",
    )
    args = parser.parse_args()

    setup_base = DEV_SETUP_BASENAME if args.profile == "dev" else SETUP_BASENAME
    release_dir_name = DEV_DIR_NAME if args.profile == "dev" else RELEASE_DIR_NAME

    if args.setup_only:
        dist_dir = PACKAGING_DIR / "dist"
        ok = (
            build_inno_setup(
                dist_dir / release_dir_name,
                setup_basename=setup_base,
                release_dir_name=release_dir_name,
                is_dev=args.profile == "dev",
            )
            is not None
        )
    else:
        ok = build(
            onefile=not args.onedir,
            clean=args.clean,
            msi=args.msi,
            profile=args.profile,
            skip_verify=args.skip_verify,
        )
    raise SystemExit(0 if ok else 1)
