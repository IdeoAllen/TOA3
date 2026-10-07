# -*- coding: utf-8 -*-
"""门禁：便携 Node 无 import.meta.main 时仍能通过 launcher 调起 dsh。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.harness_dsh_launch import dsh_cli_argv, ensure_dsh_launcher, launcher_install_root
    from services.harness_prefab import dsh_bin_under
    from services.harness_setup import default_install_root

    root = default_install_root()
    if not root.is_dir():
        print("skip: no install root")
        return 0
    launch = ensure_dsh_launcher(install_root=root)
    assert launch.is_file()
    body = launch.read_text(encoding="utf-8")
    assert "runCli" in body and "import.meta.main" in body
    dsh = dsh_bin_under(root)
    if not dsh.is_file():
        print("skip: no dsh bin.js")
        return 0
    argv = dsh_cli_argv("--help", dsh=dsh)
    assert len(argv) >= 4
    assert argv[1].endswith("toa_dsh_launch.mjs")
    assert argv[2].endswith("bin.js")
    # 包装脚本不是 bin.js：直接执行，启动器不得写到 C:\Users
    guard = Path(r"C:\Users\someone\Desktop\harness中心\工具\dsh-guard.mjs")
    wrapped = dsh_cli_argv("--profile", "web", node=argv[0], dsh=guard)
    assert wrapped[1].endswith("dsh-guard.mjs")
    assert "toa_dsh_launch.mjs" not in wrapped[1]
    assert not any(str(p).replace("/", "\\").lower() == r"c:\users\toa_dsh_launch.mjs" for p in wrapped)
    assert launcher_install_root(guard) == root
    print("verify_harness_dsh_launch: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
