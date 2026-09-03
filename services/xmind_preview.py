# -*- coding: utf-8 -*-
"""XMind (.xmind) 大纲预览：ZIP 内 content.json / 旧版 content.xml。"""
from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

XMIND_EXTENSIONS = frozenset({".xmind"})
_MAX_LINES = 800
_MAX_CHARS = 48_000


def is_xmind_path(path: Path) -> bool:
    return path.suffix.lower() in XMIND_EXTENSIONS


def read_xmind_outline(path: Path) -> str:
    """读取思维导图大纲纯文本。失败抛 OSError / ValueError / RuntimeError。"""
    path = Path(path)
    if not path.is_file():
        raise OSError(f"文件不存在：{path}")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            if "content.json" in names:
                raw = zf.read("content.json")
                data = json.loads(raw.decode("utf-8"))
                text = _outline_from_json(data)
            elif "content.xml" in names:
                raw = zf.read("content.xml")
                text = _outline_from_xml(raw)
            else:
                # 部分导出会带路径前缀
                json_name = next((n for n in names if n.endswith("content.json")), None)
                xml_name = next((n for n in names if n.endswith("content.xml")), None)
                if json_name:
                    data = json.loads(zf.read(json_name).decode("utf-8"))
                    text = _outline_from_json(data)
                elif xml_name:
                    text = _outline_from_xml(zf.read(xml_name))
                else:
                    raise ValueError("不是有效的 XMind 包（缺少 content.json / content.xml）")
    except zipfile.BadZipFile as exc:
        raise ValueError("无法作为 ZIP 打开（损坏或非 XMind 文件）") from exc

    text = (text or "").strip()
    if not text:
        return "（导图无可见主题）"
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n…（已截断预览）"
    return text


def _outline_from_json(data: Any) -> str:
    sheets: list[Any]
    if isinstance(data, list):
        sheets = data
    elif isinstance(data, dict) and isinstance(data.get("sheets"), list):
        sheets = data["sheets"]
    else:
        raise ValueError("content.json 格式无法识别")

    lines: list[str] = []
    for i, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            continue
        title = str(sheet.get("title") or f"画布 {i + 1}").strip()
        if len(sheets) > 1 or title:
            lines.append(f"【{title}】")
        root = sheet.get("rootTopic") or sheet.get("root")
        if isinstance(root, dict):
            _walk_json_topic(root, 0, lines)
        if len(lines) >= _MAX_LINES:
            lines.append("…（主题过多，已截断）")
            break
        if i < len(sheets) - 1:
            lines.append("")
    return "\n".join(lines)


def _walk_json_topic(topic: dict[str, Any], depth: int, lines: list[str]) -> None:
    if len(lines) >= _MAX_LINES:
        return
    title = str(topic.get("title") or "").strip()
    if not title and isinstance(topic.get("attributedTitle"), list):
        parts = []
        for item in topic["attributedTitle"]:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        title = "".join(parts).strip()
    prefix = "  " * depth
    bullet = "" if depth == 0 else "• "
    lines.append(f"{prefix}{bullet}{title or '（无标题）'}")

    notes = topic.get("notes")
    if isinstance(notes, dict) and len(lines) < _MAX_LINES:
        plain = notes.get("plain")
        note_txt = ""
        if isinstance(plain, dict):
            note_txt = str(plain.get("content") or "").strip()
        elif isinstance(plain, str):
            note_txt = plain.strip()
        if note_txt:
            one = note_txt.replace("\n", " ")
            if len(one) > 120:
                one = one[:120] + "…"
            lines.append(f"{prefix}  〔注〕{one}")

    children = topic.get("children")
    if not isinstance(children, dict):
        return
    for key in ("attached", "detached", "summary"):
        group = children.get(key)
        if not isinstance(group, list):
            continue
        for child in group:
            if not isinstance(child, dict):
                continue
            if len(lines) >= _MAX_LINES:
                return
            _walk_json_topic(child, depth + 1, lines)


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _outline_from_xml(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"content.xml 解析失败：{exc}") from exc

    lines: list[str] = []
    sheets = [el for el in root.iter() if _local(el.tag) == "sheet"]
    if not sheets:
        # 退化：整树找 topic
        sheets = [root]

    for i, sheet in enumerate(sheets):
        sheet_title = ""
        for child in list(sheet):
            if _local(child.tag) == "title" and (child.text or "").strip():
                sheet_title = (child.text or "").strip()
                break
        if not sheet_title:
            sheet_title = sheet.attrib.get("title") or f"画布 {i + 1}"
        if len(sheets) > 1 or sheet_title:
            lines.append(f"【{sheet_title}】")

        topics = [el for el in list(sheet) if _local(el.tag) == "topic"]
        if not topics:
            # 直接子级没有则深度找第一个 topic
            for el in sheet.iter():
                if _local(el.tag) == "topic":
                    topics = [el]
                    break
        for topic in topics:
            _walk_xml_topic(topic, 0, lines)
            if len(lines) >= _MAX_LINES:
                lines.append("…（主题过多，已截断）")
                return "\n".join(lines)
        if i < len(sheets) - 1:
            lines.append("")
    return "\n".join(lines)


def _xml_topic_title(el: ET.Element) -> str:
    if el.attrib.get("title"):
        return str(el.attrib.get("title") or "").strip()
    for child in list(el):
        if _local(child.tag) == "title":
            return (child.text or "").strip()
    return ""


def _walk_xml_topic(el: ET.Element, depth: int, lines: list[str]) -> None:
    if len(lines) >= _MAX_LINES:
        return
    title = _xml_topic_title(el)
    prefix = "  " * depth
    bullet = "" if depth == 0 else "• "
    lines.append(f"{prefix}{bullet}{title or '（无标题）'}")

    children_el = None
    for child in list(el):
        if _local(child.tag) == "children":
            children_el = child
            break
    if children_el is None:
        return
    for topics_wrap in list(children_el):
        # topics / attached-topics 等
        if "topic" not in _local(topics_wrap.tag):
            # 可能是 <topics type="attached">
            if _local(topics_wrap.tag) != "topics":
                continue
        for topic in list(topics_wrap):
            if _local(topic.tag) != "topic":
                continue
            if len(lines) >= _MAX_LINES:
                return
            _walk_xml_topic(topic, depth + 1, lines)
