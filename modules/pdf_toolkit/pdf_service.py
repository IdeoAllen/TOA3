# -*- coding: utf-8 -*-
"""PDF 工具服务：合并 / 拆分 / 按页提取（pypdf，失败可续）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class FileIssue:
    path: str
    reason: str


@dataclass
class PdfOpResult:
    ok_paths: list[str] = field(default_factory=list)
    issues: list[FileIssue] = field(default_factory=list)
    total_pages: int = 0

    @property
    def summary(self) -> str:
        lines: list[str] = []
        if self.ok_paths:
            lines.append(f"已生成 {len(self.ok_paths)} 个文件，合计 {self.total_pages} 页。")
            for p in self.ok_paths:
                lines.append(f"  + {p}")
        if self.issues:
            lines.append(f"跳过/失败 {len(self.issues)} 项：")
            for iss in self.issues:
                lines.append(f"  ! {Path(iss.path).name}: {iss.reason}")
        if not lines:
            lines.append("无输出。")
        return "\n".join(lines)


def _reader(path: Path):
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        try:
            result = reader.decrypt("")
            # pypdf 3+: int；pypdf 5+: PasswordType enum — 失败则仍 encrypted
            ok = int(result) if not hasattr(result, "name") else (0 if result.name == "NOT_DECRYPTED" else 1)
            if not ok and getattr(reader, "is_encrypted", False):
                # 部分版本 decrypt 后仍标 encrypted 但可读
                try:
                    _ = len(reader.pages)
                except Exception as e:
                    raise PermissionError("文件已加密，请先解密") from e
        except PermissionError:
            raise
        except Exception as e:
            raise PermissionError("文件已加密，请先解密") from e
    return reader


def inspect_pdf(path: str | Path) -> tuple[int, str | None]:
    """返回 (页数, 错误原因)。成功时错误为 None。"""
    p = Path(path)
    if not p.is_file():
        return 0, "文件不存在"
    if p.suffix.lower() != ".pdf":
        return 0, "不是 PDF"
    try:
        reader = _reader(p)
        return len(reader.pages), None
    except PermissionError as e:
        return 0, str(e)
    except Exception as e:
        return 0, f"无法读取（可能已损坏）: {e}"


def merge_pdfs(paths: Iterable[str | Path], out_path: str | Path) -> PdfOpResult:
    """按顺序合并；单文件失败记入 issues，其余继续。"""
    from pypdf import PdfWriter

    result = PdfOpResult()
    writer = PdfWriter()
    used = 0
    for raw in paths:
        p = Path(raw)
        try:
            reader = _reader(p)
            n = len(reader.pages)
            if n == 0:
                result.issues.append(FileIssue(str(p), "无页面"))
                continue
            writer.append(reader)
            used += n
        except PermissionError as e:
            result.issues.append(FileIssue(str(p), str(e)))
        except Exception as e:
            result.issues.append(FileIssue(str(p), f"无法读取: {e}"))

    if used == 0:
        result.issues.append(FileIssue(str(out_path), "没有可合并的有效 PDF"))
        return result

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        writer.write(f)
    result.ok_paths.append(str(out))
    result.total_pages = used
    return result


def split_pdf(
    path: str | Path,
    out_dir: str | Path,
    *,
    pages_per_file: int = 1,
) -> PdfOpResult:
    """按每 N 页拆成多个 PDF。"""
    from pypdf import PdfReader, PdfWriter

    result = PdfOpResult()
    p = Path(path)
    n_per = max(1, int(pages_per_file))
    try:
        reader = _reader(p)
    except PermissionError as e:
        result.issues.append(FileIssue(str(p), str(e)))
        return result
    except Exception as e:
        result.issues.append(FileIssue(str(p), f"无法读取: {e}"))
        return result

    total = len(reader.pages)
    if total == 0:
        result.issues.append(FileIssue(str(p), "无页面"))
        return result

    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stem = p.stem
    part = 1
    for start in range(0, total, n_per):
        end = min(start + n_per, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        out = dest / f"{stem}_part{part:03d}_p{start + 1}-{end}.pdf"
        with out.open("wb") as f:
            writer.write(f)
        result.ok_paths.append(str(out))
        result.total_pages += end - start
        part += 1
    return result


def extract_pages(
    path: str | Path,
    out_path: str | Path,
    page_numbers: Iterable[int],
) -> PdfOpResult:
    """按 1-based 页码提取；越界页记入 issues。"""
    from pypdf import PdfWriter

    result = PdfOpResult()
    p = Path(path)
    try:
        reader = _reader(p)
    except PermissionError as e:
        result.issues.append(FileIssue(str(p), str(e)))
        return result
    except Exception as e:
        result.issues.append(FileIssue(str(p), f"无法读取: {e}"))
        return result

    total = len(reader.pages)
    writer = PdfWriter()
    used = 0
    for num in page_numbers:
        if num < 1 or num > total:
            result.issues.append(FileIssue(str(p), f"页码 {num} 超出范围 1–{total}"))
            continue
        writer.add_page(reader.pages[num - 1])
        used += 1

    if used == 0:
        result.issues.append(FileIssue(str(p), "没有有效页码可提取"))
        return result

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        writer.write(f)
    result.ok_paths.append(str(out))
    result.total_pages = used
    return result


def parse_page_spec(text: str) -> list[int]:
    """解析「1,3,5-7」为 1-based 页码列表（保序去重）。"""
    pages: list[int] = []
    seen: set[int] = set()
    for part in (text or "").replace("，", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            try:
                start, end = int(a.strip()), int(b.strip())
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            for n in range(start, end + 1):
                if n not in seen:
                    seen.add(n)
                    pages.append(n)
        else:
            try:
                n = int(token)
            except ValueError:
                continue
            if n not in seen:
                seen.add(n)
                pages.append(n)
    return pages


def default_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
