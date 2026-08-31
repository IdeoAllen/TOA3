# -*- coding: utf-8 -*-
"""ComfyUI 专业档指引（非小白默认路径）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "data" / "models"


def main() -> int:
    print("=" * 60)
    print("TOA3 · ComfyUI 专业档（可选）")
    print("=" * 60)
    print()
    print("【说明】")
    print("  普通用户请优先：python scripts/setup_local_image_gen.py")
    print("  （本机简易生图，无需 ComfyUI / 工作流）")
    print()
    print("【适合谁】已会或愿意安装 ComfyUI，需要自定义节点/工作流。")
    print()
    print("【1】安装并启动 ComfyUI")
    print("  https://github.com/comfyanonymous/ComfyUI")
    print("  python main.py --listen 127.0.0.1 --port 8188")
    print("  TOA 默认：http://127.0.0.1:8188")
    print()
    print("【2】Z-Image Turbo GGUF")
    print("  · 安装自定义节点 ComfyUI-GGUF（city96）")
    print("  · unet / diffusion_models：z_image_turbo-*.gguf")
    print("  · text_encoders：Qwen3-4B*.gguf")
    print("  · vae：ae.safetensors")
    print("  · TOA 内置 API 图：assets/samples/comfyui/z_image_turbo_gguf_api.json")
    print()
    print("【3】在 TOA")
    print("  模型管理选「ComfyUI 专业 · Z-Image」→ 媒体工坊生成")
    print()
    print("【备选】SD WebUI / Forge --api → http://127.0.0.1:7860")
    print()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
