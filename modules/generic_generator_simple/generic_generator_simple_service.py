# -*- coding: utf-8 -*-
"""轻量模板填充引擎：{{key}} 替换。"""
from __future__ import annotations

import json
import re
from pathlib import Path

_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_\u4e00-\u9fff]+)\s*\}\}")


def render_template(template: str, values: dict[str, str]) -> str:
    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return str(values.get(key, m.group(0)))

    return _TOKEN_RE.sub(_repl, template or "")


def extract_placeholders(template: str) -> list[str]:
    seen: list[str] = []
    for m in _TOKEN_RE.finditer(template or ""):
        key = m.group(1)
        if key not in seen:
            seen.append(key)
    return seen


def write_outputs(
    text: str,
    out_dir: str | Path,
    *,
    basename: str = "generated",
    as_json: bool = False,
    meta: dict | None = None,
) -> list[Path]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    txt = root / f"{basename}.txt"
    txt.write_text(text, encoding="utf-8")
    paths.append(txt)
    if as_json:
        payload = {"text": text, **(meta or {})}
        js = root / f"{basename}.json"
        js.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(js)
    return paths
