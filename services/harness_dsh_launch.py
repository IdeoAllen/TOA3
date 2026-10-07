# -*- coding: utf-8 -*-
"""dsh CLI 启动包装：规避便携 Node 无 import.meta.main 导致 bin.js 静默退出。"""
from __future__ import annotations

from pathlib import Path

_LAUNCHER_NAME = "toa_dsh_launch.mjs"
_LAUNCHER_BODY = """\
#!/usr/bin/env node
/**
 * TOA3 · dsh launcher
 * 部分便携 Node（如 22.14）上 import.meta.main 为 undefined，
 * @deepseek-ai/dsh/lib/bin.js 的 `if (import.meta.main) await runCli()` 永不执行 → 进程秒退。
 * 本包装强制调用 runCli()。
 */
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const bin = resolve(process.argv[2] || "");
if (!bin) {
  console.error("toa_dsh_launch: missing dsh bin.js path");
  process.exit(2);
}
const rest = process.argv.slice(3);
process.argv = [process.execPath, bin, ...rest];
const mod = await import(pathToFileURL(bin).href);
if (typeof mod.runCli !== "function") {
  console.error("toa_dsh_launch: runCli not exported from bin.js");
  process.exit(2);
}
await mod.runCli();
"""


def ensure_dsh_launcher(*, install_root: Path | None = None) -> Path:
    """确保启动器落在安装根（随运行时目录，冻结包也可写）。"""
    if install_root is None:
        from services.harness_setup import default_install_root

        install_root = default_install_root()
    path = Path(install_root) / _LAUNCHER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == _LAUNCHER_BODY:
            return path
    except OSError:
        pass
    path.write_text(_LAUNCHER_BODY, encoding="utf-8", newline="\n")
    return path


def _is_official_dsh_bin(dsh_p: Path) -> bool:
    """官方入口是 ``…/dsh/lib/bin.js``。自定义包装（如 dsh-guard.mjs）不是。"""
    return dsh_p.name == "bin.js" and dsh_p.parent.name == "lib"


def launcher_install_root(dsh_p: Path) -> Path:
    """启动器只写 TOA 运行时目录。禁止按任意 dsh 路径向上数五级（会落到 ``C:\\Users``）。"""
    from services.harness_setup import default_install_root

    canonical = default_install_root()
    if not _is_official_dsh_bin(dsh_p):
        return canonical
    try:
        root = dsh_p.resolve().parents[4]
    except (OSError, IndexError):
        return canonical
    if not root.is_dir() or not (root / "node_modules").is_dir():
        return canonical
    # 拒绝盘符根与 ``C:\Users``（向上数错时的常见落点，普通用户无写权限）
    if root.parent == Path(root.anchor) or root == Path.home().parent:
        return canonical
    return root


def dsh_cli_argv(*cli_args: str, node: Path | None = None, dsh: Path | None = None) -> list[str]:
    """构造启动命令。

    官方 ``bin.js``：``node toa_dsh_launch.mjs <bin.js> …``（补 import.meta.main）。
    自定义包装脚本：直接 ``node <脚本> …``，不按目录深度猜安装根。
    """
    from services.harness_config import dsh_bin_path, node_exe_path

    node_p = Path(node) if node is not None else node_exe_path()
    dsh_p = Path(dsh) if dsh is not None else dsh_bin_path()
    if not _is_official_dsh_bin(dsh_p):
        return [str(node_p), str(dsh_p), *[str(a) for a in cli_args]]
    launcher = ensure_dsh_launcher(install_root=launcher_install_root(dsh_p))
    return [str(node_p), str(launcher), str(dsh_p), *[str(a) for a in cli_args]]
