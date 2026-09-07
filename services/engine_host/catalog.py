# -*- coding: utf-8 -*-
"""引擎管家收录目录：本地 Web 引擎 + Harness 适配条目。"""
from __future__ import annotations

from dataclasses import dataclass

from services.local_web_engine import load_specs, read_status


@dataclass(frozen=True)
class CatalogEntry:
    engine_id: str
    title: str
    description: str
    kind: str  # local_web | harness
    prefer_embed: bool = False


def list_catalog_entries() -> list[CatalogEntry]:
    """可信收录：local_web_engines.yml 全部 + Harness（适配，非改写旧页）。"""
    out: list[CatalogEntry] = []
    # Harness 置顶：办公传送门主样板
    out.append(
        CatalogEntry(
            engine_id="harness_agent",
            title="Harness Agent",
            description="编码智能体 · 浏览器干活（适配器，旧页不动）",
            kind="harness",
            prefer_embed=False,
        )
    )
    for eid, spec in sorted(load_specs().items(), key=lambda kv: kv[1].title.lower()):
        if str(eid).startswith("demo_"):
            continue
        out.append(
            CatalogEntry(
                engine_id=eid,
                title=spec.title or eid,
                description=(spec.description or "").strip() or "本地 Web 引擎",
                kind="local_web",
                prefer_embed=bool(spec.prefer_embed),
            )
        )
    return out


def status_badge(entry: CatalogEntry) -> str:
    """列表徽标：未装 / 已停 / 运行中。"""
    if entry.kind == "harness":
        try:
            from services import harness_sidecar

            if harness_sidecar.is_running(timeout=0.4):
                return "运行中"
            from services.harness_setup import discover_runtime

            rt = discover_runtime()
            if rt.get("dsh") and rt.get("node"):
                return "已停"
            return "未装"
        except Exception:
            return "—"
    try:
        st = read_status(entry.engine_id, probe_http=False)
        if not st.installed:
            return "未装"
        if st.running:
            return "运行中"
        return "已停"
    except Exception:
        return "—"
