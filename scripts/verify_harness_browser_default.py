#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容旧名：已改回默认内嵌，转调 verify_harness_embed_default。"""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("verify_harness_embed_default.py")),
        run_name="__main__",
    )
