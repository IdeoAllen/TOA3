#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计 TOA 业务插件包：python scripts/audit_plugin.py <plugin_root>"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.plugin_loader import audit_plugin_root  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: python scripts/audit_plugin.py <plugin_root>")
        return 2
    root = Path(argv[1]).expanduser()
    man, report = audit_plugin_root(root)
    if man:
        print(f"plugin: {man.plugin_id} · {man.name} · v{man.version}")
        print(f"root: {man.root}")
    print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
