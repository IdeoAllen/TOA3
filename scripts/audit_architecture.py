# -*- coding: utf-8 -*-
"""架构超边扫描：modules 禁 setStyleSheet（无例外注释）/ QMessageBox / 直连 HTTP。

白名单仅登记「已知债务」或「已注释控件库例外」，不得扩大。
详见 docs/architecture/ARCH-03-超边门禁.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "modules"

# 相对 modules/ 的路径 → 债务说明（还债波次见 architecture/14）
STYLE_DEBT_ALLOWLIST: dict[str, str] = {
    "screenshot_tool/screenshot_tool_page.py": "控件库例外：截图历史缩略预览",
    "image_creator/image_creator_page.py": "债务：Hold/非八件套；色板预览边框",
}

_EXCEPTION_RE = re.compile(r"控件库例外")
_STYLE_RE = re.compile(r"\.setStyleSheet\s*\(")
_MSGBOX_RE = re.compile(r"\bQMessageBox\b")
_HTTP_RE = re.compile(
    r"\b(?:import\s+requests|from\s+requests\s+import|urllib\.request|"
    r"urllib\.urlopen|httpx\.|aiohttp\.)\b"
)
# gallery 文案可提 QMessageBox 作为禁令说明
_TEXT_OK_RE = re.compile(r"禁止裸\s*QMessageBox|勿使用\s*QMessageBox")


def _rel(path: Path) -> str:
    return path.relative_to(MODULES).as_posix()


def _scan_file(path: Path, errors: list[str], warnings: list[str]) -> None:
    rel = _rel(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    for i, line in enumerate(lines):
        lineno = i + 1
        window = "\n".join(lines[max(0, i - 5) : i + 1])

        if _STYLE_RE.search(line):
            if _EXCEPTION_RE.search(window):
                continue
            if rel in STYLE_DEBT_ALLOWLIST:
                warnings.append(
                    f"{rel}:{lineno}: setStyleSheet（债务白名单：{STYLE_DEBT_ALLOWLIST[rel]}）"
                )
                continue
            errors.append(
                f"{rel}:{lineno}: 业务 setStyleSheet 超边（须删或加「# 控件库例外：…」）"
            )

        if _MSGBOX_RE.search(line) and not _TEXT_OK_RE.search(line):
            # 字符串教学文案放行
            if "QMessageBox" in line and (
                "禁止" in line or '"' in line or "'" in line or "#" in line.split("QMessageBox")[0]
            ):
                if "import" not in line and "from " not in line:
                    continue
            if "import" in line or "from " in line or "QMessageBox(" in line:
                errors.append(f"{rel}:{lineno}: 禁止裸 QMessageBox，改用 core.user_messages")

        if _HTTP_RE.search(line):
            errors.append(
                f"{rel}:{lineno}: modules 禁止直连 HTTP，改用 services.integrations.get_client"
            )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    if not MODULES.is_dir():
        print("FAIL: modules/ missing")
        return 1

    for path in sorted(MODULES.rglob("*.py")):
        if path.name == "__pycache__":
            continue
        _scan_file(path, errors, warnings)

    # 白名单文件必须仍存在，避免幽灵条目扩大例外
    for rel in STYLE_DEBT_ALLOWLIST:
        if not (MODULES / rel).is_file():
            errors.append(f"白名单文件已不存在，请从 STYLE_DEBT_ALLOWLIST 删除: {rel}")

    print("=== audit_architecture ===")
    for w in warnings:
        print("WARN", w)
    if errors:
        for e in errors:
            print("ERROR", e)
        print(f"FAIL: {len(errors)} overreach issue(s)")
        return 1
    print(f"OK — no hard overreach ({len(warnings)} debt warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
