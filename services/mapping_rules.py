# -*- coding: utf-8 -*-
"""图片位置记忆规则读写（对标 TOA2 common/mapping_rules.py）。

默认加载 ``config/mapping_rules.json``。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.config_service import project_root

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

_TEMPLATE_ALIASES: dict[str, list[str]] = {
    "lixiao.pptx": ["利刃交付材料模版.pptx", "交付材料模版.pptx"],
    "利刃交付材料模版.pptx": ["lixiao.pptx", "交付材料模版.pptx"],
    "poxiao.pptx": ["破晓交付材料模版.pptx", "交付材料模版.pptx"],
    "破晓交付材料模版.pptx": ["poxiao.pptx", "交付材料模版.pptx"],
}


def default_rules_path() -> Path:
    return project_root() / "config" / "mapping_rules.json"


def ensure_rules_file(path: str | Path | None = None) -> Path:
    rules_path = Path(path) if path else default_rules_path()
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    if not rules_path.is_file():
        rules_path.write_text("{}", encoding="utf-8")
    return rules_path


def load_rules(path: str | Path | None = None) -> Dict[str, Any]:
    rules_path = ensure_rules_file(path)
    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("加载 mapping_rules 失败: %s", exc)
    return {}


def save_rules(rules: Dict[str, Any], path: str | Path | None = None) -> bool:
    rules_path = ensure_rules_file(path)
    try:
        rules_path.write_text(
            json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
    except Exception as exc:
        logger.error("保存 mapping_rules 失败: %s", exc)
        return False


def _normalize_project(project: str) -> list[str]:
    p = (project or "").strip().lower()
    if p in ("lixiao", "liren", "利刃"):
        return ["liren", "lixiao"]
    if p in ("poxiao", "破晓"):
        return ["poxiao"]
    return [project]


def _template_name_candidates(template_name: str) -> list[str]:
    raw = (template_name or "").strip()
    base = os.path.basename(raw.replace("\\", "/"))
    names = [base] if base else []
    if raw and raw != base:
        names.append(raw)
    for n in list(names):
        for alias in _TEMPLATE_ALIASES.get(n, []):
            if alias not in names:
                names.append(alias)
    return names


def _lookup_position(slide_rules: dict, position_index: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(slide_rules, dict):
        return None
    key = str(position_index)
    rule = slide_rules.get(key)
    if rule:
        return rule
    for pos_key, rule_obj in slide_rules.items():
        if "-" not in str(pos_key):
            continue
        try:
            start, end = map(int, str(pos_key).split("-", 1))
            idx = int(position_index) if not isinstance(position_index, int) else position_index
            if start <= idx <= end:
                return rule_obj
        except (ValueError, TypeError):
            continue
    if isinstance(position_index, str) and "-" in position_index:
        return slide_rules.get(position_index)
    return None


def get_rule(
    feature: str,
    project: str,
    template_name: str,
    slide_index: int,
    position_index: Any,
    path: str | Path | None = None,
) -> Optional[Dict[str, Any]]:
    rules = load_rules(path)
    feature_rules = rules.get(feature, {})
    if not isinstance(feature_rules, dict):
        return None
    for proj in _normalize_project(project):
        proj_rules = feature_rules.get(proj, {})
        if not isinstance(proj_rules, dict):
            continue
        for tpl in _template_name_candidates(template_name):
            tpl_rules = proj_rules.get(tpl, {})
            if not isinstance(tpl_rules, dict):
                continue
            slide_rules = tpl_rules.get(str(slide_index), {})
            found = _lookup_position(slide_rules, position_index)
            if found:
                return found
    return None


def set_rule(
    feature: str,
    project: str,
    template_name: str,
    slide_index: int,
    position_index: int,
    rule_obj: Dict[str, Any],
    path: str | Path | None = None,
) -> bool:
    rules = load_rules(path)
    tpl = os.path.basename(str(template_name).replace("\\", "/"))
    proj = _normalize_project(project)[0]
    (
        rules.setdefault(feature, {})
        .setdefault(proj, {})
        .setdefault(tpl, {})
        .setdefault(str(slide_index), {})
    )[str(position_index)] = rule_obj
    return save_rules(rules, path)


def list_template_rules(
    feature: str,
    project: str,
    template_name: str,
    path: str | Path | None = None,
) -> Dict[str, Any]:
    rules = load_rules(path)
    for proj in _normalize_project(project):
        for tpl in _template_name_candidates(template_name):
            found = rules.get(feature, {}).get(proj, {}).get(tpl, {})
            if found:
                return dict(found)
    return {}


def _list_images_sorted_by_ctime(directory: str, recursive: bool = True) -> list:
    found: list[str] = []
    if not os.path.exists(directory):
        return []
    if recursive:
        for root, _, files in os.walk(directory):
            for f in files:
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                    found.append(os.path.join(root, f))
    else:
        for f in os.listdir(directory):
            p = os.path.join(directory, f)
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in IMAGE_EXTS:
                found.append(p)
    found.sort(key=lambda x: os.path.getctime(x))
    return found


def _find_matching_directories(base_dir: str, path_pattern: str, recursive: bool = True) -> List[str]:
    if not path_pattern:
        return []
    matched_dirs: list[str] = []
    try:
        regex_pattern = re.escape(path_pattern)
        regex_pattern = regex_pattern.replace("\\*", ".*").replace("\\?", ".")
        regex = re.compile(regex_pattern)
        for root, dirs, _ in os.walk(base_dir):
            for d in dirs:
                dir_path = os.path.join(root, d)
                rel_path = os.path.relpath(dir_path, base_dir)
                if regex.search(rel_path):
                    matched_dirs.append(dir_path)
            if not recursive:
                break
    except Exception as exc:
        logger.error("查找匹配目录失败: %s", exc)
    return matched_dirs


def _filter_images_by_contains(images: List[str], contains_text: str) -> List[str]:
    if not contains_text:
        return images
    return [p for p in images if contains_text in os.path.basename(p)]


def resolve_rule_to_images(base_dir: str, rule: Dict[str, Any]) -> List[str]:
    """根据规则解析并返回多张图片路径。"""
    if not rule:
        return []
    rtype = rule.get("type")
    recursive = bool(rule.get("recursive", True))
    try:
        if rtype == "exact_filename":
            filename = str(rule.get("filename", "")).strip()
            if not filename:
                return []
            exact_path = os.path.join(base_dir, filename)
            return [exact_path] if os.path.isfile(exact_path) else []

        if rtype == "dir_prefix":
            prefix = str(rule.get("prefix", "")).strip()
            if not prefix:
                return []
            matched_dirs: list[str] = []
            for root, dirnames, _ in os.walk(base_dir):
                for d in dirnames:
                    if d.startswith(prefix):
                        matched_dirs.append(os.path.join(root, d))
                if not recursive:
                    break
            images: list[str] = []
            seen: set[str] = set()
            for d in matched_dirs:
                for img in _list_images_sorted_by_ctime(d, recursive=True):
                    if img not in seen:
                        seen.add(img)
                        images.append(img)
            sort_by = rule.get("sort_by", "create_time")
            sort_order = rule.get("sort_order", "asc")
            if sort_by == "create_time":
                images.sort(key=lambda x: os.path.getctime(x), reverse=(sort_order == "desc"))
            elif sort_by == "file_name":
                images.sort(key=lambda x: os.path.basename(x), reverse=(sort_order == "desc"))
            max_count = rule.get("max_count")
            if isinstance(max_count, int) and max_count > 0:
                images = images[:max_count]
            return images

        if rtype == "directory_path":
            path_pattern = str(rule.get("path_pattern", "")).strip()
            directory = str(rule.get("directory", "")).strip()
            file_contains = str(rule.get("file_contains", "")).strip()
            sort_by = rule.get("sort_by", "create_time")
            sort_order = rule.get("sort_order", "asc")
            images = []
            seen: set[str] = set()
            if path_pattern:
                for d in _find_matching_directories(base_dir, path_pattern, recursive):
                    for img in _list_images_sorted_by_ctime(d, recursive=True):
                        if img not in seen:
                            seen.add(img)
                            images.append(img)
            elif directory and os.path.isdir(directory):
                for img in _list_images_sorted_by_ctime(directory, recursive=recursive):
                    if img not in seen:
                        seen.add(img)
                        images.append(img)
            if file_contains:
                images = _filter_images_by_contains(images, file_contains)
            if sort_by == "create_time":
                images.sort(key=lambda x: os.path.getctime(x), reverse=(sort_order == "desc"))
            elif sort_by == "file_name":
                images.sort(key=lambda x: os.path.basename(x), reverse=(sort_order == "desc"))
            max_count = rule.get("max_count")
            if isinstance(max_count, int) and max_count > 0:
                images = images[:max_count]
            return images

        if rtype == "file_number_contains":
            path_pattern = str(rule.get("path_pattern", "")).strip()
            keywords = rule.get("keywords") or []
            sort_by = rule.get("sort_by", "create_time")
            sort_order = rule.get("sort_order", "asc")
            images = []
            seen: set[str] = set()
            if path_pattern:
                for d in _find_matching_directories(base_dir, path_pattern, recursive):
                    for img in _list_images_sorted_by_ctime(d, recursive=True):
                        if img not in seen:
                            seen.add(img)
                            images.append(img)
            else:
                for img in _list_images_sorted_by_ctime(base_dir, recursive=True):
                    if img not in seen:
                        seen.add(img)
                        images.append(img)
            if keywords:
                images = [p for p in images if any(k in p for k in keywords)]
            if sort_by == "create_time":
                images.sort(key=lambda x: os.path.getctime(x), reverse=(sort_order == "desc"))
            elif sort_by == "file_name":
                images.sort(key=lambda x: os.path.basename(x), reverse=(sort_order == "desc"))
            max_count = rule.get("max_count")
            if isinstance(max_count, int) and max_count > 0:
                images = images[:max_count]
            return images
    except Exception as exc:
        logger.error("解析规则到图片列表失败: %s", exc)
        return []
    return []


def resolve_rule_to_image(base_dir: str, rule: Dict[str, Any]) -> Optional[str]:
    """根据规则解析并返回单张图片路径。"""
    if not rule:
        return None
    try:
        index = int(rule.get("index", 1))
        images = resolve_rule_to_images(base_dir, rule)
        if not images:
            return None
        if 1 <= index <= len(images):
            return images[index - 1]
        return images[-1]
    except Exception as exc:
        logger.error("解析规则到图片失败: %s", exc)
        return None
