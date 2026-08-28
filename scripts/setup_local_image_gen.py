# -*- coding: utf-8 -*-
"""本地文生图环境说明与可选模型下载指引。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "data" / "models" / "stable-diffusion"


def main() -> int:
    print("=" * 60)
    print("TOA3 · 本地文生图准备")
    print("=" * 60)
    print()
    print("【推荐】Stable Diffusion WebUI / Forge（成熟、可换模型）")
    print("  1. 安装 Forge：https://github.com/lllyasviel/stable-diffusion-webui-forge")
    print("     或 SD WebUI：https://github.com/AUTOMATIC1111/stable-diffusion-webui")
    print("  2. 启动时加 --api，例如：")
    print("     webui-user.bat 里 COMMANDLINE_ARGS=--api")
    print("  3. TOA「能力接入 → 图像生成」地址填：http://127.0.0.1:7860")
    print("  4. 在 WebUI 里下载/选择 checkpoint（推荐 SDXL 或 SD 1.5）")
    print()
    print("【TOA 内使用】")
    print("  AI → 媒体工坊 → 选「本地 SD WebUI」→ 写画面描述 → 生成")
    print()
    print("【可选】将模型权重放到本仓库（供 WebUI 引用，非 TOA 内置推理）")
    print(f"  目录：{MODELS_DIR}")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print()
    print("  可从 HuggingFace 下载 SD 1.5 主文件（约 4GB）：")
    print("  runwayml/stable-diffusion-v1-5 → v1-5-pruned-emaonly.safetensors")
    print("  下载后复制到 Forge/WebUI 的 models/Stable-diffusion/ 目录")
    print()
    if "--download-hint" in sys.argv:
        print("自动下载需 huggingface_hub：pip install huggingface_hub")
        print("然后自行执行 hf download 或浏览器下载，体积较大请预留磁盘。")
    print("完成 WebUI 配置后，无需再改 TOA 代码即可生图。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
