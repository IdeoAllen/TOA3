#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建用户扩展：脚手架 + 登记到业务板块。

用法:
  python scripts/create_user_extension.py --name "请假台卡" --desc "场景：… 痛点：… 作用：…"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.plugin_registry import register_plugin  # noqa: E402
from services.plugin_sandbox import ensure_extensions_home  # noqa: E402
from services.plugin_scaffold import (  # noqa: E402
    create_plugin_scaffold,
    suggest_plugin_id,
    write_requirements_md,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="创建 TOA 用户扩展并挂到业务板块")
    parser.add_argument("--name", required=True, help="显示名称")
    parser.add_argument("--id", default="", help="可选英文 id；默认从名称自动生成")
    parser.add_argument(
        "--desc",
        required=True,
        help="需求描述（场景、痛点、作用等，勿只写名称）",
    )
    parser.add_argument(
        "--group",
        default="business",
        help="子模块 group，默认 business（业务）",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有脚手架文件")
    args = parser.parse_args(argv[1:])

    name = str(args.name or "").strip()
    desc = str(args.desc or "").strip()
    if not name:
        print("错误: --name 不能为空")
        return 2
    if len(desc) < 8:
        print("错误: --desc 请写清场景/痛点/作用（至少数十字）")
        return 2

    ensure_extensions_home()
    pid = str(args.id or "").strip() or suggest_plugin_id(name)
    short = desc.splitlines()[0].strip()[:120]
    try:
        out = create_plugin_scaffold(
            plugin_id=pid,
            name=name,
            group=str(args.group or "business").strip() or "business",
            description=short,
            overwrite=bool(args.overwrite),
        )
        write_requirements_md(out, name=name, description=desc)
        man = register_plugin(out, show=True, status="mvp", gaps=[])
    except Exception as exc:  # noqa: BLE001 — CLI 边界
        print(f"失败: {exc}")
        return 1

    print("OK · 已创建并登记到业务板块")
    print(f"name: {man.name}")
    print(f"id:   {man.plugin_id}")
    print(f"group:{man.group}")
    print(f"root: {man.root}")
    print("下一步: 在本 root 按 REQUIREMENTS.md 实现 → python scripts/audit_plugin.py <root>")
    print("用户: TOA → 系统 → 扩展 → 开发完成 → 打开 → 顶栏「业务」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
