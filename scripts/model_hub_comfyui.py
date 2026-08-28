# -*- coding: utf-8 -*-
"""ComfyUI 本地生图：安装指引（安装包不含模型权重）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "data" / "models"
COMFY_CHECKPOINTS_HINT = "ComfyUI/models/checkpoints/"


def main() -> int:
    print("=" * 60)
    print("TOA3 · 模型库 · ComfyUI 本地生图（对标 ComfyUI 最佳实践）")
    print("=" * 60)
    print()
    print("【原则】")
    print("  · TOA 安装包 **不内置** SD/Flux 等权重（体积与授权）")
    print("  · 按需：网络 API 配置 Key，或本机 ComfyUI + 自行下载 checkpoint")
    print("  · 任务页只从「可用」列表选模型；未就绪 → 模型库查看原因")
    print()
    print("【1】安装 ComfyUI（推荐）")
    print("  官方：https://github.com/comfyanonymous/ComfyUI")
    print("  Windows 便携包或 git clone 后：python main.py --listen 127.0.0.1 --port 8188")
    print("  TOA 默认端点：http://127.0.0.1:8188")
    print()
    print("【2】下载 checkpoint（用户自选，不进 TOA 安装包）")
    print(f"  · 放入 ComfyUI：{COMFY_CHECKPOINTS_HINT}")
    print(f"  · 或同步到 TOA 扫描目录：{MODELS_DIR / 'checkpoints'}")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "checkpoints").mkdir(parents=True, exist_ok=True)
    print("  · 示例：HuggingFace runwayml/stable-diffusion-v1-5")
    print("    → v1-5-pruned-emaonly.safetensors（约 4GB，请自行下载）")
    print()
    print("【3】在 TOA 中配置")
    print("  系统设置 → 能力接入 → 模型库 → 刷新")
    print("  图像生成配置选「本地 ComfyUI」，保存后")
    print("  AI → 媒体工坊 → 从可用列表选模型 → 生成")
    print()
    print("【备选】SD WebUI / Forge + --api → http://127.0.0.1:7860")
    print("  能力接入 → 图像生成 → 配置「本地 SD WebUI」")
    print()
    if "--list-local" in sys.argv:
        sys.path.insert(0, str(ROOT))
        from services.model_ready_registry import scan_local_weight_files

        files = scan_local_weight_files()
        if not files:
            print("data/models 下暂无权重文件。")
        else:
            print("已扫描到本机权重：")
            for f in files:
                print(f"  - {f.get('label')}  ({f.get('local_path')})")
    print()
    print("完成 ComfyUI 启动且 checkpoint 就位后，模型库应显示「可用」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
