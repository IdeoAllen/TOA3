# -*- coding: utf-8 -*-
"""校验本地 Web 引擎 / Harness 宿主能力：安装探测 · 启停 · 加载就绪。

用法：
  python scripts/verify_local_web_engines.py
  python scripts/verify_local_web_engines.py --start drawio_web
  python scripts/verify_local_web_engines.py --start-all-light
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(flag: bool) -> str:
    return "PASS" if flag else "FAIL"


def check_local(engine_id: str, *, do_start: bool, timeout: float) -> list[str]:
    from services.local_web_engine import (
        discover_root,
        get_spec,
        load_specs,
        read_status,
        start_engine,
        wait_engine_ready,
    )
    from services.local_web_engine.install import can_one_click_install

    load_specs(force=True)
    lines: list[str] = []
    spec = get_spec(engine_id)
    if spec is None:
        return [f"[{engine_id}] FAIL 未登记"]
    root = discover_root(engine_id)
    st0 = read_status(engine_id, probe_http=False)
    lines.append(
        f"[{engine_id}] 规格 {spec.title} · port={spec.port} · auto_start={spec.auto_start}"
    )
    lines.append(
        f"[{engine_id}] 安装 {_ok(st0.installed)} root={root} · one_click={can_one_click_install(engine_id)}"
    )
    if not st0.installed:
        if can_one_click_install(engine_id):
            lines.append(f"[{engine_id}] NOTE 未装，支持一键安装（进页可见进度）")
        else:
            lines.append(
                f"[{engine_id}] NOTE 未装且无一键下载：{spec.install_hint or '需指定目录'}"
            )
        return lines

    # 启动命令可解析
    from services.local_web_engine import _resolve_start_exe

    resolvable = False
    for argv in spec.start_cmds:
        if argv and _resolve_start_exe(argv[0], root) is not None:
            resolvable = True
            break
    lines.append(f"[{engine_id}] 启动命令可解析 {_ok(resolvable)}")

    if not do_start:
        state = "PASS" if st0.running else "IDLE"
        lines.append(
            f"[{engine_id}] 当前运行 {state} · {st0.detail} · {st0.url}"
        )
        return lines

    if st0.running:
        lines.append(f"[{engine_id}] 已在运行 PASS · {st0.url}")
        return lines

    ok_s, msg_s = start_engine(engine_id)
    lines.append(f"[{engine_id}] 启动 {_ok(ok_s)} · {msg_s}")
    if not ok_s:
        return lines
    ok_r, msg_r = wait_engine_ready(engine_id, timeout_sec=timeout)
    lines.append(f"[{engine_id}] 就绪 {_ok(ok_r)} · {msg_r}")
    return lines


def check_harness() -> list[str]:
    lines: list[str] = []
    try:
        from services.harness_config import load_harness_config
        from services.harness_credentials import has_api_key
        from services.harness_status import read_harness_status
        from services.harness_setup import discover_runtime

        cfg = load_harness_config(force=True)
        st = read_harness_status(probe_http=True, http_timeout=1.0)
        lines.append(
            f"[harness_agent] 安装 {_ok(st.install.value == 'ready' if hasattr(st.install, 'value') else st.has_key and st.node_ok)} "
            f"· {st.install_label} · key={has_api_key()}"
        )
        lines.append(
            f"[harness_agent] 服务 {_ok(st.running)} · {st.service_label} · {st.url}"
        )
        lines.append(
            f"[harness_agent] 路径 home={cfg.get('dsh_home')} port={cfg.get('web_port')} "
            f"surface={cfg.get('surface_mode')}"
        )
        disc = discover_runtime()
        lines.append(f"[harness_agent] discover keys={list(disc.keys())}")
        # 一键安装能力：有 node 即可
        from pathlib import Path

        node_ok = Path(str(cfg.get("node_exe") or "")).is_file() or bool(disc.get("node_exe"))
        lines.append(f"[harness_agent] 可安装/修复环境 {_ok(node_ok)}")
    except Exception as exc:
        lines.append(f"[harness_agent] FAIL {exc}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", action="append", default=[], help="启动并等待就绪的引擎 id")
    ap.add_argument(
        "--start-all-light",
        action="store_true",
        help="启动 drawio（轻）与 open_pencil（若已装）；Comfy/Harness 只探测",
    )
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    start_ids = set(args.start or [])
    if args.start_all_light:
        start_ids.update({"drawio_web", "open_pencil"})

    report: list[str] = []
    report.append("=== TOA 引擎宿主校验 ===")
    report.extend(check_harness())
    for eid in ("open_pencil", "drawio_web", "comfyui_web"):
        report.extend(
            check_local(eid, do_start=eid in start_ids, timeout=args.timeout)
        )
        report.append("---")

    text = "\n".join(report)
    print(text)
    bad = [ln for ln in report if " FAIL" in ln or ln.rstrip().endswith("FAIL")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
