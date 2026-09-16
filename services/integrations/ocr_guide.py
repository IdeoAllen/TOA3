# -*- coding: utf-8 -*-
"""OCR 中文就绪：本机探测 + ≤2 步人话安装引导（禁止进页同步联网）。"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# 引擎结论（本轨评估）：默认本地 Tesseract；云端 provider 未实现；无 Paddle/Windows OCR。
ENGINE_CONCLUSION = "tesseract_local"

_COMMON_TESS_EXE = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

# 小白友好：安装包页（用户主动打开，非进页探测）
_WIN_INSTALLER_HINT = (
    "https://github.com/UB-Mannheim/tesseract/wiki"
)
_CHI_SIM_FILE_HINT = (
    "https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata"
)


@dataclass
class OcrChineseStatus:
    """本机 OCR / 中文语言包状态（全部本地 IO，无网络）。"""

    engine: str = ENGINE_CONCLUSION
    provider: str = "tesseract"
    enabled: bool = False
    tesseract_path: str = ""
    tesseract_ok: bool = False
    tessdata_dir: str = ""
    available_langs: list[str] = field(default_factory=list)
    chinese_ready: bool = False  # chi_sim 已装
    lang_config: str = ""
    config_wants_chinese: bool = False
    code: str = "unknown"  # ready | need_enable | missing_lang | missing_engine | disabled | no_deps
    title: str = ""
    steps: list[str] = field(default_factory=list)  # ≤2
    detail: str = ""

    def guide_text(self) -> str:
        lines = [self.title] if self.title else []
        for i, step in enumerate(self.steps[:2], 1):
            lines.append(f"{i}. {step}")
        if self.detail:
            lines.append("")
            lines.append(self.detail)
        return "\n".join(lines).strip()


def resolve_tesseract_path(configured: str | None = None) -> str:
    """解析可用 tesseract.exe：配置路径 → PATH → 常见安装位（本地，无联网）。"""
    candidates: list[str] = []
    tip = (configured or "").strip()
    if tip:
        candidates.append(tip)
    which = shutil.which("tesseract")
    if which:
        candidates.append(which)
    candidates.extend(_COMMON_TESS_EXE)
    seen: set[str] = set()
    for raw in candidates:
        p = str(Path(raw))
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        if Path(p).is_file():
            return p
    return tip or (candidates[0] if candidates else "")


def tessdata_dir_for(tesseract_path: str) -> Path | None:
    """由 exe 推断 tessdata 目录。"""
    exe = Path(tesseract_path or "")
    if not exe.is_file():
        return None
    # 标准布局：…/Tesseract-OCR/tesseract.exe → …/Tesseract-OCR/tessdata
    sibling = exe.parent / "tessdata"
    if sibling.is_dir():
        return sibling
    # 少数发行版用 TESSDATA_PREFIX
    prefix = (os.environ.get("TESSDATA_PREFIX") or "").strip()
    if prefix:
        p = Path(prefix)
        if p.is_dir():
            return p
        if (p / "tessdata").is_dir():
            return p / "tessdata"
    return sibling if exe.parent.is_dir() else None


def _list_langs_local(tesseract_path: str) -> set[str]:
    """本地列出语言包：优先读 tessdata 文件名；必要时调一次 --list-langs（本机进程，无网）。"""
    found: set[str] = set()
    td = tessdata_dir_for(tesseract_path)
    if td is not None and td.is_dir():
        for f in td.glob("*.traineddata"):
            name = f.stem.strip()
            if name and name not in ("osd", "equ"):
                found.add(name)
    if found:
        return found
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        return set(pytesseract.get_languages(config="") or [])
    except Exception as exc:
        logger.debug("list langs via pytesseract failed: %s", exc)
        return found


def probe_chinese_status(*, force_langs: Iterable[str] | None = None) -> OcrChineseStatus:
    """探测中文 OCR 就绪。force_langs 仅供 verify/单测注入，生产勿用联网。"""
    from services.integrations.config import integration_config

    cfg = integration_config("ocr") or {}
    st = OcrChineseStatus(
        provider=str(cfg.get("provider") or "tesseract"),
        enabled=bool(cfg.get("enabled")),
        lang_config=str(cfg.get("lang") or "eng"),
    )
    st.config_wants_chinese = any(
        p in ("chi_sim", "chi_tra", "chinese")
        for p in st.lang_config.replace(",", "+").lower().split("+")
    )

    if st.provider != "tesseract":
        st.code = "missing_engine"
        st.title = f"当前 OCR 引擎「{st.provider}」尚未接入。"
        st.steps = [
            "请在能力接入里改回本地 Tesseract（小白默认本机完成，无需云端）。",
            "改完后回到本页再点「启用中文识别」。",
        ]
        return st

    if not st.enabled:
        st.code = "disabled"
        st.title = "OCR 能力未启用。"
        st.steps = [
            "打开「系统设置 → 能力接入」，勾选启用 OCR。",
            "回到截图工具栏或本页再试识别。",
        ]
        return st

    try:
        import pytesseract  # noqa: F401
    except ImportError:
        st.code = "no_deps"
        st.title = "本机缺少 OCR 运行库。"
        st.steps = [
            "在 TOA 所用 Python 环境执行：pip install pytesseract Pillow",
            "装好后重启 TOA，再点「启用中文识别」。",
        ]
        return st

    path = resolve_tesseract_path(str(cfg.get("tesseract_path") or ""))
    st.tesseract_path = path
    st.tesseract_ok = bool(path and Path(path).is_file())
    td = tessdata_dir_for(path) if st.tesseract_ok else None
    st.tessdata_dir = str(td) if td else ""

    if not st.tesseract_ok:
        st.code = "missing_engine"
        st.title = "还没装好本机识字程序（Tesseract）。"
        st.steps = [
            f"打开安装说明页，下载 Windows 安装包并安装（勾选 Chinese Simplified / chi_sim）：{_WIN_INSTALLER_HINT}",
            "装好后回到本软件，再点一次「启用中文识别」。",
        ]
        st.detail = "默认走本地引擎，不连云；安装包较大，请用浏览器下载（本页不会自动联网探测）。"
        return st

    if force_langs is not None:
        langs = {str(x).strip() for x in force_langs if str(x).strip()}
    else:
        langs = _list_langs_local(path)
    st.available_langs = sorted(langs)
    st.chinese_ready = "chi_sim" in langs

    if st.chinese_ready:
        if st.config_wants_chinese and "chi_sim" in st.lang_config:
            st.code = "ready"
            st.title = "中文识别已就绪。"
            st.steps = []
            st.detail = f"语言={st.lang_config}；引擎=Tesseract 本地。"
        else:
            st.code = "need_enable"
            st.title = "已检测到中文语言包，还差一步写入设置。"
            st.steps = [
                "点「启用中文识别」一键写入 chi_sim+eng（不必手改配置文件）。",
            ]
        return st

    # 有引擎、无 chi_sim：≤2 步
    st.code = "missing_lang"
    st.title = "本机 Tesseract 还没有中文包（chi_sim）。"
    folder = st.tessdata_dir or "Tesseract 安装目录下的 tessdata 文件夹"
    st.steps = [
        f"把 chi_sim.traineddata 放到语言包文件夹（可点「打开语言包文件夹」）：{folder}",
        "放好后回到本页再点「启用中文识别」。",
    ]
    st.detail = (
        f"语言包文件直链（浏览器另存即可，软件不会后台下载）：{_CHI_SIM_FILE_HINT}\n"
        f"已装语言：{', '.join(st.available_langs) or '未知'}。未装中文前，英文识别仍可用。"
    )
    return st


def enable_chinese_ocr() -> tuple[bool, OcrChineseStatus, str]:
    """
    尝试启用中文：有 chi_sim 则写入 lang=chi_sim+eng。
    返回 (ok, status, user_message)。
    """
    st = probe_chinese_status()
    if st.code == "ready":
        return True, st, "中文识别已是开启状态，直接截图即可。"
    if st.code == "need_enable" or (st.chinese_ready and st.code != "ready"):
        from services.integrations.config import save_integrations_config

        save_integrations_config({"ocr": {"lang": "chi_sim+eng"}})
        # 若路径是自动发现的且配置为空/失效，一并写回，免手改 yml
        if st.tesseract_ok and st.tesseract_path:
            save_integrations_config({"ocr": {"tesseract_path": st.tesseract_path}})
        st2 = probe_chinese_status()
        return True, st2, "已启用中文识别（chi_sim+eng）。再截一张图即可。"
    return False, st, st.guide_text()


def open_tessdata_folder(status: OcrChineseStatus | None = None) -> tuple[bool, str]:
    """打开本机 tessdata 目录（本地动作，无联网）。"""
    st = status or probe_chinese_status()
    folder = st.tessdata_dir
    if not folder or not Path(folder).is_dir():
        return False, "找不到语言包文件夹。请先安装 Tesseract。"
    try:
        os.startfile(folder)  # type: ignore[attr-defined]
        return True, f"已打开：{folder}"
    except Exception as exc:
        return False, f"无法打开文件夹：{exc}"


def open_chinese_download_page() -> tuple[bool, str]:
    """用户主动打开浏览器（非进页探测）。缺引擎→安装说明；缺语言包→chi_sim 直链。"""
    import webbrowser

    st = probe_chinese_status()
    url = _WIN_INSTALLER_HINT if st.code == "missing_engine" else _CHI_SIM_FILE_HINT
    try:
        webbrowser.open(url)
        return True, f"已在浏览器打开：{url}"
    except Exception as exc:
        return False, f"无法打开浏览器：{exc}\n请手动访问：{url}"


def chinese_warning_for_result(result: dict[str, Any] | None) -> str:
    """识别结果里若回落英文，给出短提示（供截图/页内展示）。"""
    if not isinstance(result, dict):
        return ""
    if result.get("chinese_ready") is False and result.get("config_wants_chinese"):
        return str(result.get("chinese_hint") or "").strip()
    return ""
