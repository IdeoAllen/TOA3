# -*- coding: utf-8 -*-
"""本机简易生图（L1）：离线包契约与安装指引（安装包不含权重）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="TOA3 本机简易生图指引")
    parser.add_argument(
        "--import",
        dest="import_dir",
        default="",
        help="从离线包文件夹导入运行时与模型",
    )
    parser.add_argument("--status", action="store_true", help="打印本机就绪状态")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from services.local_image_runtime import (
        import_offline_pack,
        install_status,
        recommend_quant_label,
        runtime_root,
        weights_root,
    )

    print("=" * 60)
    print("TOA3 · 本机生图（推荐 · 零工作流）")
    print("=" * 60)
    print()
    print("【给谁】不会配 ComfyUI、可能没外网、电脑配置一般的用户。")
    print("【做什么】装好一次 → 打开「媒体工坊」写一句话出图。")
    print()
    print("【目录】")
    print(f"  运行时：{runtime_root()}")
    print(f"  模型：  {weights_root()}")
    print()
    print("【离线包建议结构】")
    print("  toa-local-image/")
    print("    manifest.json          # 可选：{\"quant\":\"Q4\",\"label\":\"低配\"}")
    print("    runtime/sd-cli.exe     # stable-diffusion.cpp 可执行文件")
    print("    models/")
    print("      z_image_turbo-Q4_K.gguf")
    print("      ae.safetensors")
    print("      Qwen3-4B-….gguf")
    print()
    print("【显存建议】", recommend_quant_label(None))
    print("  · 约 4GB  → Q3 / Q4")
    print("  · 约 6–8GB → Q4 / Q5")
    print("  · 更高    → Q5 / Q8")
    print()
    print("【权重来源示例（有网时自行下载）】")
    print("  · Diffusion GGUF: Hugging Face leejet/Z-Image-Turbo-GGUF")
    print("  · VAE ae.safetensors: Flux / Z-Image 配套 VAE")
    print("  · 文本 Qwen3-4B GGUF")
    print("  · 运行时: github.com/leejet/stable-diffusion.cpp 预编译")
    print()
    print("【在 TOA 里】")
    print("  系统设置 → 模型库 →「导入离线包」或本脚本 --import")
    print("  然后：AI → 媒体工坊 → 选「本机生图（推荐）」→ 生成")
    print()

    if args.import_dir:
        ok, msg = import_offline_pack(args.import_dir)
        print(("✓ " if ok else "× ") + msg)
        return 0 if ok else 1

    if args.status or True:
        st = install_status()
        print("【当前状态】")
        print("  就绪:" , "是" if st["ready"] else "否")
        if st["missing"]:
            print("  缺少:", "、".join(st["missing"]))
        print("  运行时文件:", st["binary"] or "（无）")
        print("  生图模型:", st["diffusion"] or "（无）")
        print("  VAE:", st["vae"] or "（无）")
        print("  文本组件:", st["text_encoder"] or "（无）")
        print()
        print(st["user_hint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
