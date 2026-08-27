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

from app.version import APP_NAME, APP_VERSION  # noqa: E402

APP_EXE = APP_NAME  # TOA3.exe
APP_DISPLAY = "TOA3-运营宝"
RELEASE_DIR_NAME = f"{APP_NAME}-v{APP_VERSION}-win64"
SETUP_BASENAME = f"{APP_NAME}-Setup-v{APP_VERSION}"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


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
            "fitz",
            "pymupdf",
            "pdf2image",
        }
    )
    return sorted(imports)


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
        log("生成 TOA3 品牌图标 ...")
        subprocess.run([sys.executable, str(script)], cwd=PROJECT_DIR, check=False)


def preflight() -> bool:
    log("运行 MVP 验收 ...")
    result = subprocess.run([sys.executable, str(PROJECT_DIR / "scripts" / "verify_mvp.py")], cwd=PROJECT_DIR)
    if result.returncode != 0:
        log("MVP 验收失败，中止打包")
        return False

    release_cfg = PROJECT_DIR / "config" / "app.release.yml"
    if release_cfg.is_file():
        data = yaml.safe_load(release_cfg.read_text(encoding="utf-8")) or {}
        if (data.get("auth") or {}).get("skip_login"):
            log("错误: app.release.yml 仍开启 skip_login")
            return False
    return True


def build_inno_setup(release_dir: Path | None = None) -> str | None:
    dist_dir = PACKAGING_DIR / "dist"
    release_dir = release_dir or (dist_dir / RELEASE_DIR_NAME)
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
    log("开始构建 Inno Setup 安装包 ...")
    result = subprocess.run([iscc, str(iss)], cwd=PACKAGING_DIR)
    if result.returncode != 0:
        log("Inno Setup 构建失败")
        return None

    setup_exe = dist_dir / f"{SETUP_BASENAME}.exe"
    if not setup_exe.is_file():
        log(f"未找到生成的 setup.exe: {setup_exe}")
        return None
    log(f"Setup 安装包: {setup_exe}")
    return str(setup_exe)


def build(onefile: bool = True, clean: bool = False, msi: bool = False) -> bool:
    if not preflight():
        return False

    ensure_brand_assets()

    dist_dir = PACKAGING_DIR / "dist"
    build_dir = PACKAGING_DIR / "build"
    dist_dir.mkdir(parents=True, exist_ok=True)

    if clean:
        for path in (build_dir, dist_dir):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        dist_dir.mkdir(parents=True, exist_ok=True)

    main_script = PROJECT_DIR / "app" / "main.py"
    icon_path = PROJECT_DIR / "avatars" / "logo.ico"
    if not icon_path.is_file():
        icon_path = PROJECT_DIR / "resources" / "icons" / "app_logo.ico"

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
        str(build_dir),
        "--specpath",
        str(PACKAGING_DIR),
        "--paths",
        str(PROJECT_DIR),
        "--noconfirm",
        "--clean",
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
    if onefile:
        cmd.append("--onefile")
    if icon_path.is_file():
        cmd.extend(["--icon", str(icon_path)])

    data_pairs = [
        ("config", "config"),
        ("resources", "resources"),
        ("assets", "assets"),
        ("avatars", "avatars"),
        ("ui", "ui"),
    ]
    for src, dest in data_pairs:
        src_path = PROJECT_DIR / src
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
        "yaml",
        "cv2",
        "numpy",
        "pytesseract",
        "fitz",
        *collect_menu_hidden_imports(),
    ]
    for item in sorted(set(hidden_imports)):
        cmd.extend(["--hidden-import", item])

    log(f"开始打包 {APP_NAME} v{APP_VERSION} ...")
    result = subprocess.run(cmd, cwd=PACKAGING_DIR)
    if result.returncode != 0:
        log("打包失败")
        return False

    release_dir = dist_dir / RELEASE_DIR_NAME
    release_dir.mkdir(parents=True, exist_ok=True)

    exe_name = f"{APP_EXE}.exe"
    exe_src = dist_dir / exe_name
    if exe_src.is_file():
        shutil.copy2(exe_src, release_dir / exe_name)

    for folder in ("config", "resources", "assets", "avatars", "ui"):
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
            "app.dev.yml",
        )
        if folder == "config":
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                if item.name in {"license.json", "app.dev.yml", "admin_bootstrap_code.txt"}:
                    continue
                if item.is_dir():
                    shutil.copytree(item, dst / item.name, ignore=ignore)
                elif item.is_file():
                    shutil.copy2(item, dst / item.name)
        else:
            shutil.copytree(src, dst, ignore=ignore)

    write_clean_license(release_dir / "config" / "license.json")

    readme = release_dir / "README.txt"
    readme.write_text(
        f"TOA3 赋能培训运营助手（运营宝）· 单机版\n"
        f"版本: {APP_VERSION}\n\n"
        f"请通过正式安装包安装：\n"
        f"  {SETUP_BASENAME}.exe\n\n"
        "首次启动可选「单机体验」：免授权码、可离线，含记事/截图/剪贴板/四象限任务等基础工具。\n"
        "完整版：向管理员索取 TOA2 授权码，在登录窗选择「授权码登录」并联网激活。\n"
        "授权到期或被停用后，无需卸载，重新申请新码激活即可。\n"
        "默认不需要管理员权限；如需装到 Program Files 可在向导中选择提升。\n"
        "卸载: Windows「应用和功能」或开始菜单 Uninstall TOA3。\n"
        "与 TOA2 可并存（安装目录 %LOCALAPPDATA%\\Programs\\TOA3）。\n",
        encoding="utf-8",
    )

    archive = shutil.make_archive(str(dist_dir / RELEASE_DIR_NAME), "zip", release_dir)
    log(f"发布目录: {release_dir}")
    log(f"ZIP 归档: {archive}")

    setup_path = None
    if msi:
        setup_path = build_inno_setup(release_dir)
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

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--onedir", action="store_true")
    parser.add_argument("--msi", action="store_true", help="打包完成后生成 Setup.exe")
    parser.add_argument("--setup-only", action="store_true", help="仅基于已有 release 目录生成 Setup.exe")
    args = parser.parse_args()

    if args.setup_only:
        ok = build_inno_setup() is not None
    else:
        ok = build(onefile=not args.onedir, clean=args.clean, msi=args.msi)
    raise SystemExit(0 if ok else 1)
