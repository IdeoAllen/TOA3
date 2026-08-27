# -*- coding: utf-8 -*-
"""抬升主题色对比度：禁用字 / 占位符相对表面不可见时自动加深或提亮。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "config" / "themes"


def _lum(hex_c: str) -> float:
    h = hex_c.lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _lerp(c1: str, c2: str, t: float) -> str:
    h1, h2 = c1.lstrip("#"), c2.lstrip("#")
    rgb1 = [int(h1[i : i + 2], 16) for i in (0, 2, 4)]
    rgb2 = [int(h2[i : i + 2], 16) for i in (0, 2, 4)]
    out = [int(rgb1[i] * (1 - t) + rgb2[i] * t) for i in range(3)]
    return "#" + "".join(f"{x:02X}" for x in out)


def ensure_contrast(fg: str, bg: str, target: float = 3.0) -> str:
    if contrast(fg, bg) >= target:
        return fg
    # 背景亮 → 往黑压；背景暗 → 往白提
    end = "#000000" if _lum(bg) > 0.45 else "#FFFFFF"
    best = fg
    for i in range(0, 101):
        c = _lerp(fg, end, i / 100)
        if contrast(c, bg) >= target:
            return c
        best = c
    return best


# (fg_key, bg_key, min_ratio)
PAIRS = [
    ("text_disabled", "surface", 3.0),
    ("text_disabled", "background", 3.0),
    ("input_placeholder", "input_bg", 3.0),
    ("text_secondary", "surface", 4.5),
    ("text_primary", "surface", 4.5),
    ("nav_fg", "nav_bg", 4.5),
]


def fix_palette(pal: dict) -> list[str]:
    changes: list[str] = []
    for fg_key, bg_key, thr in PAIRS:
        if fg_key not in pal or bg_key not in pal:
            continue
        old = str(pal[fg_key])
        bg = str(pal[bg_key])
        new = ensure_contrast(old, bg, thr)
        if new.upper() != old.upper():
            pal[fg_key] = new
            changes.append(f"{fg_key}: {old} → {new} (vs {bg_key})")
    # 侧栏若与 nav_bg 不一致且会导致浅底深/浅字问题：对齐为 nav_bg（VS 类主题）
    if "nav_bg" in pal and "surface_sidebar" in pal:
        if contrast(str(pal.get("nav_fg", "")), str(pal["surface_sidebar"])) < 3.0:
            if contrast(str(pal.get("nav_fg", "")), str(pal["nav_bg"])) >= 3.0:
                old = pal["surface_sidebar"]
                pal["surface_sidebar"] = pal["nav_bg"]
                changes.append(f"surface_sidebar: {old} → {pal['nav_bg']} (align nav_bg)")
    return changes


def main() -> None:
    for path in sorted(THEMES.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        pal = doc.get("palette") or {}
        changes = fix_palette(pal)
        if not changes:
            print(f"OK  {path.stem}")
            continue
        doc["palette"] = pal
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"FIX {path.stem}")
        for line in changes:
            print(f"    {line}")


if __name__ == "__main__":
    main()
