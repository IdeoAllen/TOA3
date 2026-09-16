# -*- coding: utf-8 -*-
"""剪贴板历史存储（文本 + 图片；支持置顶 / 搜索 / 隐私 / 送记事）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

_MAX = 120
_SOURCE_LABEL = {
    "auto": "自动",
    "manual": "手动",
    "screenshot": "截图",
    "ocr": "OCR",
}
_PRIVACY_MASK = "••••（隐私时段）"


def _path() -> Path:
    return module_data_dir("clipboard_history", create=True) / "history.json"


def _prefs_path() -> Path:
    return module_data_dir("clipboard_history", create=True) / "prefs.json"


def _images_dir() -> Path:
    d = module_data_dir("clipboard_history", create=True) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_prefs() -> dict[str, Any]:
    path = _prefs_path()
    if not path.is_file():
        return {"privacy": False}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {"privacy": bool(raw.get("privacy"))}
    except Exception:
        pass
    return {"privacy": False}


def save_prefs(prefs: dict[str, Any]) -> None:
    data = {"privacy": bool((prefs or {}).get("privacy"))}
    _prefs_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def privacy_on() -> bool:
    return bool(load_prefs().get("privacy"))


def set_privacy(on: bool) -> None:
    """隐私时段：暂停一切入库（含截图/OCR 显式 push）；列表侧遮罩。"""
    prefs = load_prefs()
    prefs["privacy"] = bool(on)
    save_prefs(prefs)


def source_label(source: str | None) -> str:
    key = str(source or "")
    return _SOURCE_LABEL.get(key, key)


def filter_history(
    items: list[dict[str, Any]] | None = None,
    *,
    query: str = "",
    source: str = "",
) -> list[dict[str, Any]]:
    """全文搜索 + 来源过滤（source 空=全部）。"""
    rows = items if items is not None else load_history()
    q = (query or "").strip().lower()
    src = (source or "").strip().lower()
    out: list[dict[str, Any]] = []
    for x in rows:
        if not isinstance(x, dict):
            continue
        if src and str(x.get("source") or "").lower() != src:
            continue
        if q:
            label = source_label(str(x.get("source") or ""))
            blob = (
                f"{x.get('text') or ''} {x.get('kind') or ''} "
                f"{x.get('source') or ''} {label}"
            ).lower()
            if q not in blob:
                continue
        out.append(x)
    return out


def list_line(item: dict[str, Any], *, privacy: bool | None = None) -> str:
    """列表行文案；隐私开启时遮罩正文。"""
    mask = privacy_on() if privacy is None else bool(privacy)
    star = "★ " if item.get("pinned") else ""
    kind = "🖼" if item.get("kind") == "image" else "文"
    src = source_label(str(item.get("source") or ""))
    if mask:
        preview = _PRIVACY_MASK
    else:
        preview = (item.get("text") or "").replace("\n", " ")[:64]
    return f"{star}[{kind}] {item.get('time', '')} · {src} · {preview}"


def notepad_handoff(item: dict[str, Any] | None) -> dict[str, Any] | None:
    """送记事本载荷：{title, body, image_path}；不可送则 None。"""
    if not item or not isinstance(item, dict):
        return None
    title = "来自剪贴板历史"
    if item.get("kind") == "image":
        path = image_abs_path(item)
        if path is None:
            return None
        return {"title": title, "body": "", "image_path": str(path)}
    text = str(item.get("text") or "").strip()
    if not text:
        return None
    return {"title": title, "body": text, "image_path": None}


def load_history() -> list[dict[str, Any]]:
    path = _path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []
        changed = False
        for x in items:
            if not x.get("id"):
                x["id"] = uuid.uuid4().hex[:12]
                changed = True
            if not x.get("kind"):
                x["kind"] = "image" if x.get("image") else "text"
                changed = True
        if changed:
            save_history(items)
        return items
    except Exception:
        return []


def save_history(items: list[dict[str, Any]]) -> None:
    pinned = [x for x in items if x.get("pinned")]
    rest = [x for x in items if not x.get("pinned")]
    ordered = (pinned + rest)[:_MAX]
    _path().write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")


def _insert_entry(entry: dict[str, Any]) -> dict[str, Any]:
    items = load_history()
    idx = next((i for i, x in enumerate(items) if not x.get("pinned")), 0)
    items.insert(idx, entry)
    save_history(items)
    return entry


def push_text(text: str, *, source: str = "manual") -> dict[str, Any] | None:
    if privacy_on():
        return None
    text = (text or "").strip()
    if not text:
        return None
    items = load_history()
    existing = next(
        (x for x in items if x.get("kind", "text") == "text" and x.get("text") == text),
        None,
    )
    if existing:
        items = [x for x in items if x.get("id") != existing.get("id")]
        existing["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing["source"] = source
        if existing.get("pinned"):
            items.insert(0, existing)
        else:
            idx = next((i for i, x in enumerate(items) if not x.get("pinned")), len(items))
            items.insert(idx, existing)
        save_history(items)
        return existing
    entry = {
        "id": uuid.uuid4().hex[:12],
        "kind": "text",
        "text": text[:8000],
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pinned": False,
        "source": source,
    }
    return _insert_entry(entry)


def push_image(pixmap, *, source: str = "manual") -> dict[str, Any] | None:
    """保存位图为无损 PNG（兼容旧调用）。优先用 push_clipboard_image 保留原图字节。"""
    if privacy_on():
        return None
    if pixmap is None or getattr(pixmap, "isNull", lambda: True)():
        return None
    from PySide6.QtGui import QImage

    qimg = pixmap.toImage()
    if qimg.isNull():
        return None
    # 去掉 devicePixelRatio 缩放，按物理像素存原尺寸
    dpr = float(pixmap.devicePixelRatio() or 1.0)
    if dpr > 1.01:
        qimg = qimg.copy()
        # toImage 已是逻辑像素；若 pixmap 带 DPR，用 physical 尺寸重建
        phys_w = max(1, int(round(pixmap.width() * dpr)))
        phys_h = max(1, int(round(pixmap.height() * dpr)))
        if qimg.width() < phys_w or qimg.height() < phys_h:
            qimg = pixmap.toImage()
    return _store_qimage(qimg, source=source)


def push_clipboard_image(clipboard, *, source: str = "manual") -> dict[str, Any] | None:
    """从系统剪贴板抓取原图：优先 PNG/JPEG 原始字节，其次 QImage，避免 HiDPI 缩略。"""
    if privacy_on():
        return None
    if clipboard is None:
        return None
    mime = clipboard.mimeData()
    if mime is None:
        return None

    # 1) 原始编码字节（真正的原图）
    for fmt, ext in (
        ("image/png", "png"),
        ("image/jpeg", "jpg"),
        ("image/bmp", "bmp"),
        ("image/webp", "webp"),
    ):
        if mime.hasFormat(fmt):
            raw = mime.data(fmt)
            data = bytes(raw.data()) if hasattr(raw, "data") else bytes(raw)
            if len(data) > 32:
                return _store_image_bytes(data, ext=ext, source=source)

    # 2) QImage（全分辨率）
    if mime.hasImage():
        from PySide6.QtGui import QImage

        img = mime.imageData()
        if isinstance(img, QImage) and not img.isNull():
            return _store_qimage(img, source=source)

    # 3) 回退 pixmap
    pix = clipboard.pixmap()
    if pix is not None and not pix.isNull():
        return push_image(pix, source=source)
    return None


def _store_image_bytes(data: bytes, *, ext: str, source: str) -> dict[str, Any] | None:
    iid = uuid.uuid4().hex[:12]
    rel = f"images/{iid}.{ext}"
    dest = _images_dir() / f"{iid}.{ext}"
    try:
        dest.write_bytes(data)
    except OSError:
        return None
    w = h = 0
    try:
        from PySide6.QtGui import QImage

        qi = QImage.fromData(data)
        if not qi.isNull():
            w, h = qi.width(), qi.height()
    except Exception:
        pass
    entry = {
        "id": iid,
        "kind": "image",
        "text": f"[图片 {w}×{h}]" if w and h else "[图片]",
        "image": rel,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pinned": False,
        "source": source,
        "width": w,
        "height": h,
        "original": True,
    }
    return _insert_entry(entry)


def _store_qimage(qimg, *, source: str) -> dict[str, Any] | None:
    from PySide6.QtGui import QImage

    if qimg is None or qimg.isNull():
        return None
    # 统一无损 PNG，不缩放
    img = qimg
    if img.format() == QImage.Format.Format_Invalid:
        return None
    iid = uuid.uuid4().hex[:12]
    rel = f"images/{iid}.png"
    dest = _images_dir() / f"{iid}.png"
    if not img.save(str(dest), "PNG"):
        return None
    entry = {
        "id": iid,
        "kind": "image",
        "text": f"[图片 {img.width()}×{img.height()}]",
        "image": rel,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pinned": False,
        "source": source,
        "width": int(img.width()),
        "height": int(img.height()),
        "original": True,
    }
    return _insert_entry(entry)


def image_abs_path(item: dict[str, Any]) -> Path | None:
    rel = str(item.get("image") or "").strip()
    if not rel:
        return None
    p = module_data_dir("clipboard_history", create=False) / rel
    return p if p.is_file() else None


def toggle_pin(item_id: str) -> None:
    items = load_history()
    for x in items:
        if x.get("id") == item_id:
            x["pinned"] = not bool(x.get("pinned"))
            break
    save_history(items)


def delete_item(item_id: str) -> None:
    items = load_history()
    kept = []
    for x in items:
        if x.get("id") == item_id:
            img = image_abs_path(x)
            if img is not None:
                try:
                    img.unlink(missing_ok=True)
                except OSError:
                    pass
            continue
        kept.append(x)
    save_history(kept)


def clear_history(*, keep_pinned: bool = True) -> None:
    items = load_history()
    if keep_pinned:
        drop = [x for x in items if not x.get("pinned")]
        keep = [x for x in items if x.get("pinned")]
    else:
        drop = items
        keep = []
    for x in drop:
        img = image_abs_path(x)
        if img is not None:
            try:
                img.unlink(missing_ok=True)
            except OSError:
                pass
    save_history(keep)


def find_item(item_id: str) -> dict[str, Any] | None:
    for x in load_history():
        if x.get("id") == item_id:
            return x
    return None
