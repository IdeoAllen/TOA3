# -*- coding: utf-8 -*-
"""生成侧栏/首页菜单统一线宽 SVG（24×24 · stroke 1.8）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "resources" / "icons" / "svg"

HEAD = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="#333333" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">'
)
TAIL = "</svg>\n"

ICONS: dict[str, str] = {
    "home": """
  <path d="M3 10.5 12 3l9 7.5"/>
  <path d="M5 9.5V20h14V9.5"/>
  <path d="M10 20v-6h4v6"/>
""",
    "file_text": """
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
  <path d="M14 3v5h5"/>
  <path d="M9 13h6M9 17h4"/>
""",
    "folder": """
  <path d="M3 7h5l2 2h11v10H3z"/>
""",
    "folder_open": """
  <path d="M3 7h5l2 2h11v2H5l-2 8V7z"/>
  <path d="M5 11h16l-2 8H3"/>
""",
    "camera": """
  <path d="M4 8h3l1.5-2h7L17 8h3v11H4z"/>
  <circle cx="12" cy="13.5" r="3.2"/>
""",
    "calendar": """
  <rect x="3.5" y="5" width="17" height="15" rx="2"/>
  <path d="M8 3v4M16 3v4M3.5 10h17"/>
  <path d="M8 14h3M13 14h3M8 17h3"/>
""",
    "user": """
  <circle cx="12" cy="8" r="3.5"/>
  <path d="M5 20c1.5-3.5 4-5 7-5s5.5 1.5 7 5"/>
""",
    "web_workspace": """
  <circle cx="12" cy="12" r="9"/>
  <path d="M3 12h18"/>
  <path d="M12 3a14 14 0 0 1 0 18"/>
  <path d="M12 3a14 14 0 0 0 0 18"/>
""",
    "quick_notepad": """
  <path d="M7 3h7l4 4v14H7z"/>
  <path d="M14 3v4h4"/>
  <path d="M9.5 11h7M9.5 15h5"/>
""",
    "quadrant_tasks": """
  <rect x="3.5" y="3.5" width="17" height="17" rx="2"/>
  <path d="M12 3.5v17M3.5 12h17"/>
""",
    "pomodoro": """
  <circle cx="12" cy="13" r="7.5"/>
  <path d="M12 13V8.5"/>
  <path d="M10 4.5h4"/>
  <path d="M12 4.5V3"/>
""",
    "ocr_tool": """
  <path d="M5 8V5h3M16 5h3v3M19 16v3h-3M8 19H5v-3"/>
  <path d="M9 9h2.5v7M9 16h2.5M14 9h.01M14 12h3v4h-3"/>
""",
    "clipboard_history": """
  <rect x="6" y="5" width="12" height="16" rx="2"/>
  <path d="M9 5V3.8A1.8 1.8 0 0 1 10.8 2h2.4A1.8 1.8 0 0 1 15 3.8V5"/>
  <path d="M9 11h6M9 15h4"/>
""",
    "llm_assistant": """
  <path d="M12 3l1.2 3.6L17 8l-3.8 1.4L12 13l-1.2-3.6L7 8l3.8-1.4z"/>
  <path d="M18.5 13.5l.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7z"/>
  <path d="M5.5 14.5l.6 1.7 1.7.6-1.7.6-.6 1.7-.6-1.7-1.7-.6 1.7-.6z"/>
""",
    "harness_agent": """
  <rect x="4" y="5" width="16" height="14" rx="2"/>
  <path d="M8 9h8M8 12h6M8 15h4"/>
  <circle cx="17" cy="8" r="2"/>
  <path d="M16 7.5v1M17 8.5h1"/>
""",
    "image_creator": """
  <rect x="3.5" y="5" width="17" height="14" rx="2"/>
  <circle cx="9" cy="10" r="1.6"/>
  <path d="M3.5 16l4.5-4 3 3 3-4 4.5 5"/>
  <path d="M17 3v4M15 5h4"/>
""",
    "image_adjust": """
  <path d="M5 8h10"/>
  <circle cx="17" cy="8" r="2"/>
  <path d="M5 12h6"/>
  <circle cx="13" cy="12" r="2"/>
  <path d="M5 16h12"/>
  <circle cx="19" cy="16" r="2"/>
""",
    "batch_rename": """
  <path d="M5 7h9"/>
  <path d="M5 12h14"/>
  <path d="M5 17h7"/>
  <path d="M16 15l3 3-1.5 1.5L14.5 16.5z"/>
""",
    "pdf_toolkit": """
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
  <path d="M14 3v5h5"/>
  <path d="M8 13h2.2c.9 0 1.5.5 1.5 1.3S11.1 15.6 10.2 15.6H8.8V18H7.5v-5z"/>
  <path d="M13 13h1.5c1.2 0 2 .7 2 2.1S15.7 17.2 14.5 17.2H13V18h-1.3v-5H13zm0 1.3v1.6h.5c.5 0 .9-.3.9-.8s-.4-.8-.9-.8H13z"/>
""",
    "excel_cleaner": """
  <rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/>
  <path d="M3.5 9h17M3.5 13.5h17M9 4.5v15"/>
  <path d="M12.5 11.2l4 4M16.5 11.2l-4 4"/>
""",
    "image": """
  <rect x="3.5" y="5" width="17" height="14" rx="2"/>
  <circle cx="9" cy="10" r="1.6"/>
  <path d="M3.5 16l4.5-4 3 3 3-4 4.5 5"/>
""",
    "image_watermark": """
  <rect x="3.5" y="5" width="17" height="14" rx="2"/>
  <path d="M8 16c0-2.2 1.8-4 4-4s4 1.8 4 4"/>
  <circle cx="12" cy="10" r="1.4"/>
""",
    "watermark_photo": """
  <rect x="3.5" y="6" width="17" height="13" rx="2"/>
  <circle cx="12" cy="12.5" r="3"/>
  <path d="M8 6l1.2-2h5.6L16 6"/>
  <path d="M15.5 9.5h2.5"/>
""",
    "image_to_scan": """
  <path d="M5 8V5h3M16 5h3v3M19 16v3h-3M8 19H5v-3"/>
  <rect x="7.5" y="8" width="9" height="8" rx="1"/>
  <path d="M7.5 11h9"/>
""",
    "image_format_convert": """
  <rect x="3.5" y="5" width="10" height="8" rx="1.5"/>
  <path d="M15 9h4.5v10H9v-4"/>
  <path d="M17 6l2 2-2 2M7 16l-2-2 2-2"/>
""",
    "watermark_remover": """
  <path d="M5 16l5-9 3 3 6-7"/>
  <path d="M4 20h16"/>
  <path d="M14.5 11.5l4 7"/>
""",
    "photo_extractor": """
  <path d="M7 4H4v3M17 4h3v3M20 17v3h-3M7 20H4v-3"/>
  <rect x="7.5" y="7.5" width="9" height="9" rx="1"/>
""",
    "directory_inspector": """
  <path d="M3 7h5l2 2h11v10H3z"/>
  <circle cx="15.5" cy="14" r="3"/>
  <path d="M17.7 16.2 20 18.5"/>
""",
    "column_preview": """
  <rect x="3.5" y="4" width="5" height="16" rx="1"/>
  <rect x="9.5" y="4" width="5" height="16" rx="1"/>
  <rect x="15.5" y="4" width="5" height="16" rx="1"/>
""",
    "directory_generator": """
  <path d="M3 8h5l2 2h8v9H3z"/>
  <path d="M17 4v6M14 7h6"/>
""",
    "deduction_note_formatter": """
  <path d="M8 6h12M8 12h12M8 18h8"/>
  <path d="M4 6h.01M4 12h.01M4 18h.01"/>
""",
    "package": """
  <path d="M12 3 20 7.5v9L12 21 4 16.5v-9z"/>
  <path d="M12 12 20 7.5M12 12v9M12 12 4 7.5"/>
""",
    "list": """
  <path d="M9 6h11M9 12h11M9 18h11"/>
  <path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>
""",
    "clock": """
  <circle cx="12" cy="12" r="8.5"/>
  <path d="M12 7.5V12l3 2"/>
""",
    "notifications": """
  <path d="M6 16V10a6 6 0 0 1 12 0v6"/>
  <path d="M5 16h14"/>
  <path d="M10 19a2 2 0 0 0 4 0"/>
""",
    "table": """
  <rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/>
  <path d="M3.5 9h17M3.5 13.5h17M9 4.5v15M15 4.5v15"/>
""",
    "resume_extractor": """
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
  <path d="M14 3v5h5"/>
  <circle cx="10" cy="12" r="2"/>
  <path d="M7.5 17c.8-1.5 1.9-2.2 3.5-2.2S13.7 15.5 14.5 17"/>
  <path d="M16 13.5h2.5M17.25 12.25v2.5"/>
""",
    "schedule_reminder": """
  <rect x="3.5" y="5" width="17" height="15" rx="2"/>
  <path d="M8 3v4M16 3v4M3.5 10h17"/>
  <path d="M12 13v3.5"/>
  <circle cx="12" cy="18" r="0.8" fill="#333333" stroke="none"/>
  <path d="M9.5 13.5c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5"/>
""",
    "resume_generator": """
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
  <path d="M14 3v5h5"/>
  <circle cx="12" cy="12" r="2.2"/>
  <path d="M8.5 17.5c1-2 2.5-3 3.5-3s2.5 1 3.5 3"/>
""",
    "table_card_generator": """
  <path d="M3.5 6H20.5V18a2 2 0 0 1-2 2H5.5a2 2 0 0 1-2-2V6z"/>
  <path d="M3.5 10H20.5"/>
  <path d="M8 14h8M10 17h4"/>
""",
    "document_composer": """
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
  <path d="M14 3v5h5"/>
  <path d="M9 12h6M9 15h6M9 18h4"/>
""",
    "row_to_column": """
  <rect x="3.5" y="4.5" width="7" height="15" rx="1"/>
  <path d="M13 8h7M13 12h7M13 16h7"/>
  <path d="M12 12h-1"/>
""",
    "generic_generator": """
  <path d="M12 3l1.5 4.5H18l-3.5 2.8 1.3 4.7L12 12.8 8.2 15l1.3-4.7L6 7.5h4.5z"/>
""",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, body in ICONS.items():
        path = OUT / f"{key}_svg.svg"
        path.write_text(HEAD + body + TAIL, encoding="utf-8")
        print("wrote", path.name)
    # 兼容旧文件名
    for hyphen, under in (("file-text", "file_text"), ("folder-open", "folder_open")):
        src = OUT / f"{under}_svg.svg"
        dst = OUT / f"{hyphen}_svg.svg"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print("wrote", dst.name)


if __name__ == "__main__":
    main()
