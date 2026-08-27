# -*- coding: utf-8 -*-
"""简历提取：单文件 / 目录批处理 → 字段 → 导出 CSV/XLSX。"""
from __future__ import annotations

import csv
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_output_dir

logger = logging.getLogger("TOA3.resume_extractor")

FIELD_KEYS = ("文件名", "城市", "姓名", "手机号", "微信号")
OCR_LANG = "chi_sim+eng"

# 与产品口径对齐：多级目录递归扫描的简历类型
SUPPORTED_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".txt",
    ".md",
    ".docx",
    ".pptx",
    ".ppt",  # 二进制 ppt 仅登记；请另存为 pptx
}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_TEXT_SUFFIXES = {".txt", ".md", ".csv"}


def _engine():
    from modules.resume_extractor.toa2_engine import ResumeExtractor

    return ResumeExtractor()


def extract_fields_from_text(
    text: str,
    *,
    filename: str = "",
    file_path: str = "",
) -> dict[str, str | None]:
    """轻量字段启发式（不依赖 OCR 重依赖）。"""
    from modules.resume_extractor.toa2_engine import DEFAULT_CITIES, ResumeExtractor

    ex = ResumeExtractor.__new__(ResumeExtractor)
    ex.cities = list(DEFAULT_CITIES)
    ex.name_pattern = (
        r"姓名[：:\s]*([\u4e00-\u9fa5]{2,4})|^([\u4e00-\u9fa5]{2,4})\s*$|"
        r"([\u4e00-\u9fa5]{2,4})\s*先生|([\u4e00-\u9fa5]{2,4})\s*女士"
    )
    ex.phone_pattern = r"(1[3-9]\d{9})"
    ex.wechat_pattern = (
        r"微信[：:\s]*([a-zA-Z0-9_\-]{5,20})|微信号[：:\s]*([a-zA-Z0-9_\-]{5,20})|"
        r"[a-zA-Z][a-zA-Z0-9_\-]{4,19}"
    )
    return_fields = {
        "文件名": filename or (Path(file_path).name if file_path else ""),
        "城市": ex.extract_city(text, filename, file_path),
        "姓名": ex.extract_name(text, filename or (Path(file_path).name if file_path else "")),
        "手机号": ex.extract_phone(text),
        "微信号": ex.extract_wechat(text),
    }
    return ex._apply_filename_fallbacks(
        return_fields, return_fields["文件名"] or ""
    )


def _fields_meaningful(fields: dict[str, Any] | None) -> bool:
    if not fields:
        return False
    for key in ("姓名", "手机号", "微信号", "城市"):
        val = fields.get(key)
        if val and str(val).strip() and str(val).strip() != "--":
            return True
    return False


def _try_ocr_image(path: Path) -> str | None:
    """经 integrations OCR 识别图片（中英优先）。"""
    try:
        from services.integrations import get_client
        from services.integrations.config import integration_enabled

        if not integration_enabled("ocr"):
            return None
        client = get_client("ocr")
        raw = client.recognize_image(str(path), lang=OCR_LANG)
        if isinstance(raw, dict):
            text = str(raw.get("text") or raw.get("content") or "")
            return text or None
        return str(raw) if raw else None
    except Exception as e:
        logger.info("integrations OCR 失败 %s: %s", path.name, e)
        return None


def _render_pdf_pages(path: Path, *, max_pages: int = 5):
    """将 PDF 渲染为 PIL 图列表（pdf2image/poppler → 可选 PyMuPDF）。"""
    images = []
    try:
        from pdf2image import convert_from_path

        from modules.resume_extractor.toa2_engine import _resolve_poppler_path

        poppler_path = _resolve_poppler_path()
        images = convert_from_path(
            str(path),
            dpi=200,
            first_page=1,
            last_page=max_pages,
            poppler_path=poppler_path,
        )
        if images:
            return images
    except Exception as e:
        logger.info("pdf2image 渲染失败 %s: %s", path.name, e)

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            from PIL import Image
            import io

            images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
        doc.close()
        if images:
            return images
    except Exception as e:
        logger.info("PyMuPDF 渲染失败 %s: %s", path.name, e)

    return []


def _ocr_pil_images(images) -> str:
    """临时落盘后经 integrations OCR；失败则直调 pytesseract。"""
    parts: list[str] = []
    for i, image in enumerate(images):
        text = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=f"_p{i}.png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                image.save(tmp_path, format="PNG")
                text = _try_ocr_image(tmp_path) or ""
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.info("OCR 页 %s 失败: %s", i, e)

        if not text.strip():
            try:
                import pytesseract

                text = pytesseract.image_to_string(image, lang=OCR_LANG) or ""
            except Exception:
                text = ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def _ocr_pdf(path: Path) -> str | None:
    """扫描件/图片型 PDF：渲染后 OCR。"""
    images = _render_pdf_pages(path, max_pages=5)
    if not images:
        return None
    text = _ocr_pil_images(images)
    return text or None


def _read_pdf_text(path: Path) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(str(path))
        parts = []
        for page in reader.pages[:10]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        pass
    try:
        import PyPDF2

        with path.open("rb") as f:
            reader = PyPDF2.PdfReader(f)
            parts = []
            for page in reader.pages[:10]:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)
    except Exception:
        return ""


def _read_docx_text(path: Path) -> str:
    try:
        from docx import Document

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        table_texts: list[str] = []
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        table_texts.append(cell.text)
        return "\n".join(paragraphs + table_texts)
    except Exception:
        return ""


def _read_pptx_text(path: Path) -> str:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        prs = Presentation(str(path))
        parts: list[str] = []

        def _shape_text(shape) -> None:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs) or (para.text or "")
                    if line.strip():
                        parts.append(line)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        if cell.text and cell.text.strip():
                            parts.append(cell.text)
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                for child in shape.shapes:
                    _shape_text(child)

        for slide in prs.slides:
            for shape in slide.shapes:
                _shape_text(shape)
        return "\n".join(parts)
    except Exception as e:
        logger.info("读取 pptx 失败 %s: %s", path.name, e)
        return ""


def ocr_status_summary() -> str:
    """页内提示：OCR / Poppler 是否可用。"""
    bits: list[str] = []
    try:
        from services.integrations.config import integration_config, integration_enabled

        if not integration_enabled("ocr"):
            bits.append("OCR 集成未启用")
        else:
            cfg = integration_config("ocr") or {}
            tip = str(cfg.get("tesseract_path") or "").strip()
            if tip and Path(tip).is_file():
                bits.append(f"Tesseract 就绪（{Path(tip).name}）")
            else:
                bits.append("Tesseract 未配置（integrations.yml → ocr.tesseract_path）")
            pop = str(cfg.get("poppler_path") or "").strip()
            if pop and Path(pop).is_dir():
                bits.append("Poppler 已配置")
            else:
                from modules.resume_extractor.toa2_engine import _resolve_poppler_path

                resolved = _resolve_poppler_path()
                if resolved:
                    bits.append(f"Poppler 探测到：{resolved}")
                else:
                    bits.append("Poppler 未找到（图片型 PDF 需 pdf2image+poppler 或 PyMuPDF）")
    except Exception as e:
        bits.append(f"OCR 状态未知：{e}")
    return "；".join(bits) if bits else "OCR 状态未知"


def extract_resume(path: str | Path) -> dict[str, Any]:
    """单文件提取；优先 TOA2 引擎，空结果再走轻量/OCR 回退。"""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在: {src}")

    result: dict[str, Any] = {
        "source": str(src),
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "engine": "stub",
        "text": "",
        "fields": {},
        "note": "",
    }

    suffix = src.suffix.lower()
    fields: dict[str, Any] | None = None

    if suffix == ".ppt":
        result["engine"] = "unsupported"
        result["note"] = "旧版 .ppt 不支持，请另存为 .pptx 后再提取。"
        result["fields"] = {"文件名": src.name}
        return result

    # 尝试完整引擎
    try:
        eng = _engine()
        if suffix == ".pdf":
            fields = eng.process_resume(str(src))
            result["engine"] = "toa2_engine"
        elif suffix in _IMAGE_SUFFIXES:
            fields = eng.process_image_file(str(src))
            result["engine"] = "toa2_engine"
        elif suffix in _TEXT_SUFFIXES:
            fields = eng.process_text_file(str(src))
            result["engine"] = "toa2_engine"
        elif suffix == ".docx":
            fields = eng.process_docx_file(str(src))
            result["engine"] = "toa2_engine"
        elif suffix == ".pptx":
            fields = eng.process_pptx_file(str(src))
            result["engine"] = "toa2_engine"
    except Exception as e:
        logger.info("toa2_engine 不可用或失败，回退轻量路径: %s", e)
        fields = None

    if fields and _fields_meaningful(fields):
        result["fields"] = {k: fields.get(k) for k in FIELD_KEYS}
        # PDF 有姓名/城市但缺手机时，再用渲染 OCR 补联系方式（招聘扫描件常见）
        if suffix == ".pdf" and not str(result["fields"].get("手机号") or "").strip():
            ocr_text = _ocr_pdf(src)
            if ocr_text:
                result["text"] = ((result.get("text") or "") + "\n" + ocr_text).strip()
                from modules.resume_extractor.toa2_engine import ResumeExtractor

                eng2 = ResumeExtractor()
                phone = eng2.extract_phone(ocr_text) or eng2.extract_phone(
                    (result.get("text") or "") + "\n" + ocr_text
                )
                wechat = eng2.extract_wechat(ocr_text)
                if phone:
                    result["fields"]["手机号"] = phone
                    if not result["fields"].get("微信号"):
                        result["fields"]["微信号"] = phone
                    result["engine"] = f"{result.get('engine')}+pdf_ocr"
                if wechat and not result["fields"].get("微信号"):
                    result["fields"]["微信号"] = wechat
                # 若姓名仍是噪声，再用文件名
                if not eng2.looks_like_display_name(str(result["fields"].get("姓名") or "")):
                    bn = eng2.extract_name_from_boss_filename(src.name)
                    if bn:
                        result["fields"]["姓名"] = bn
        missing = [
            label
            for key, label in (("手机号", "手机号"), ("微信号", "微信号"), ("姓名", "姓名"))
            if not str(result["fields"].get(key) or "").strip()
        ]
        if missing:
            result["note"] = (
                f"已提取部分字段；正文未检出{'/'.join(missing)}（源文件可能未写该信息）。"
            )
        else:
            result["note"] = "已提取字段。"
        return result

    # 轻量回退（含图片型 PDF OCR）
    text = ""
    note_extra = ""
    if suffix in _TEXT_SUFFIXES:
        text = src.read_text(encoding="utf-8", errors="ignore")
        result["engine"] = "plaintext"
    elif suffix == ".pdf":
        text = _read_pdf_text(src)
        if len(text.strip()) < 40:
            ocr = _ocr_pdf(src)
            if ocr:
                text = f"{text}\n{ocr}".strip() if text.strip() else ocr
                result["engine"] = "pdf_ocr"
            else:
                result["engine"] = "pdf_text"
                if not text.strip():
                    note_extra = (
                        "图片型 PDF 未能 OCR（检查 Tesseract / Poppler 或安装 PyMuPDF）。"
                    )
        else:
            result["engine"] = "pdf_text"
    elif suffix == ".docx":
        text = _read_docx_text(src)
        result["engine"] = "docx"
    elif suffix == ".pptx":
        text = _read_pptx_text(src)
        result["engine"] = "pptx"
    elif suffix in _IMAGE_SUFFIXES:
        ocr = _try_ocr_image(src)
        if ocr:
            text = ocr
            result["engine"] = "ocr"
        else:
            # 直调引擎图片路径再试一次（可能仅缺 integrations 配置）
            try:
                eng = _engine()
                fields2 = eng.process_image_file(str(src))
                if fields2 and _fields_meaningful(fields2):
                    result["fields"] = {k: fields2.get(k) for k in FIELD_KEYS}
                    result["engine"] = "toa2_engine"
                    result["note"] = "已提取字段。"
                    return result
            except Exception:
                pass
            result["note"] = "OCR 未启用或不可用。请在 integrations.yml 配置 tesseract_path。"
            result["fields"] = {"文件名": src.name}
            return result
    else:
        result["note"] = f"不支持的类型: {suffix}"
        result["fields"] = {"文件名": src.name}
        return result

    result["text"] = text
    result["fields"] = extract_fields_from_text(text, filename=src.name, file_path=str(src))
    if fields and not _fields_meaningful(result["fields"]):
        # 合并引擎侧文件名启发式结果
        for k in FIELD_KEYS:
            if not result["fields"].get(k) and fields.get(k):
                result["fields"][k] = fields.get(k)
    result["note"] = note_extra or "已按轻量/OCR 路径提取。"
    return result


def extract_directory(directory: str | Path) -> list[dict[str, Any]]:
    """递归扫描多级目录下全部支持类型。"""
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录: {root}")
    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    results: list[dict[str, Any]] = []
    for f in files:
        try:
            results.append(extract_resume(f))
        except Exception as e:
            results.append(
                {
                    "source": str(f),
                    "extracted_at": datetime.now().isoformat(timespec="seconds"),
                    "engine": "error",
                    "text": "",
                    "fields": {"文件名": f.name},
                    "note": str(e),
                }
            )
    return results


def rows_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        fields = dict(item.get("fields") or {})
        row = {k: fields.get(k) or "" for k in FIELD_KEYS}
        if not row.get("文件名"):
            row["文件名"] = Path(str(item.get("source") or "")).name
        name = str(row.get("姓名") or "")
        city = str(row.get("城市") or "") or "--"
        phone = str(row.get("手机号") or "")
        if name or phone or (city and city != "--"):
            row["备注"] = f"{name}助教-{city}-{phone}"
        else:
            row["备注"] = ""
        row["引擎"] = item.get("engine") or ""
        note = str(item.get("note") or "")
        if note and not _fields_meaningful(fields):
            row["备注"] = note
        rows.append(row)
    return rows


def save_extract_json(data: dict[str, Any], out_dir: str | Path) -> Path:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = root / f"resume_extract_{stamp}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_results(
    results: list[dict[str, Any]],
    out_dir: str | Path | None = None,
    *,
    fmt: str = "xlsx",
) -> Path:
    rows = rows_from_results(results)
    if not rows:
        raise ValueError("没有可导出的结果")
    root = Path(out_dir) if out_dir else module_output_dir("resume_extractor", create=True)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = (fmt or "xlsx").lower()
    if fmt == "csv":
        path = root / f"简历信息提取_{stamp}.csv"
        fieldnames = list(rows[0].keys())
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    try:
        import pandas as pd
    except ImportError:
        path = root / f"简历信息提取_{stamp}.csv"
        fieldnames = list(rows[0].keys())
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    path = root / f"简历信息提取_{stamp}.xlsx"
    from services.excel_export import dataframe_to_xlsx

    return dataframe_to_xlsx(pd.DataFrame(rows), path)
