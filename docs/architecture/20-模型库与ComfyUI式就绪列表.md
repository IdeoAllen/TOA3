# 20 · 模型库与图像能力三级阶梯

> **模型库 = 算力卡包**（对用户：绑定来源、设默认、解绑）。详见 [30-算力来源与支付卡隐喻](30-算力来源与支付卡隐喻.md)。  
> 主理人裁定：**不对齐「安装包一次带全模型」**；对齐「模型管理 + 任务页只选可用 + 缺了再下/配」。  
> 图像轨面向**终端小白**：默认零工作流；有条件再上 ComfyUI / 云端。  
> 关联：`19` · `29`（办公 Ready 列表；Harness Key 不在本表）。

## 1. 图像三级阶梯（小白优先）

| 档 | 用户看见 | 底层 | 适合 |
|----|----------|------|------|
| **L1 本机简易（推荐）** | 本机生图 | TOA 托管 **stable-diffusion.cpp** + Z-Image Turbo GGUF | 无外网 / 低配 / 不会工作流 |
| **L2 本机专业** | ComfyUI 专业 | 本机 ComfyUI + 固化 API 工作流 | 愿装 Comfy、要自定义 |
| **L3 云端** | 云端生图 | OpenAI 兼容等 API | 有网 + Key |

任务页只列 `status=ready`；空列表 → 引导「安装本机生图」或「导入离线包」。  
**不学**：把 ComfyUI 整棵 UI 嵌进 TOA；默认路径不出现节点/工作流黑话。

### L1 目录约定

```
~/.toa3/image-runtime/          # sd / sd-cli 可执行文件（离线包可导入）
data/models/image/z_image_turbo/
  *.gguf                        # diffusion（如 Q3/Q4/Q5）
  ae.safetensors                # VAE
  Qwen*.gguf | *.safetensors    # 文本编码器
  install.json                  # 可选：量化档与来源记录
```

离线包契约见 `scripts/setup_local_image_gen.py`。

## 2. ComfyUI 式就绪（通用）

| 做法 | TOA3 对应 |
|------|-----------|
| 权重不进程序本体 | `data/models/**`；**安装包不含权重** |
| 下拉只列已有 | 任务页 Combo 只列 `ready` |
| 缺了再补 | 在线指引 / 离线包导入；`needs_download` / `needs_key` / `needs_endpoint` |

## 3. 目标 UX

```
系统设置 → 模型管理 / 模型库
  图像生成
    · 本机生图（推荐）  [安装…] [导入离线包]  ✓可用 / ○待安装
    · ComfyUI 专业      [查看指引]
    · 云端生图          [填 Key]
  [刷新]

媒体工坊
  └─ 下拉仅「可用」；写提示词 → 生成 → show_saved
```

## 4. 架构

```
config/model_catalog.yml
data/user/model_catalog.yml
data/models/image/**              # L1 权重
~/.toa3/image-runtime/            # L1 运行时

services/model_catalog.py
services/model_ready_registry.py
services/local_image_runtime.py   # L1 探测 / 导入 / 调 sd-cli
services/integrations/
  image_gen_client.py             # sdcpp | comfyui | sd_webui | openai_images
  sdcpp_client.py
  comfyui_client.py
```

## 5. 阶段

| 阶段 | 交付 |
|------|------|
| **P0** | L1 sdcpp + Z-Image 目录/离线导入；L2 Comfy Z-Image 工作流；L3 API；媒体工坊白话下拉 |
| **P1** | 在线下载助手（HF）；显存自动探测推荐量化 |
| **P2** | 视频/音频 capability |

## 6. 铁律

1. 安装包不 ship 权重；可提供离线包契约。  
2. 业务页禁止散落 API 表单；只选 Ready + 做任务。  
3. 三方调用只经 `services/integrations`。  
4. Harness 不走模型库。  
5. 进页禁止同步联网探测；刷新/测试才探测。

## 7. 代码落点

| 层 | 路径 |
|----|------|
| 就绪 | `services/model_ready_registry.py` |
| L1 运行时 | `services/local_image_runtime.py` |
| 模型库 UI | `modules/system_settings/model_hub_section.py` |
| 指引 | `scripts/setup_local_image_gen.py` · `scripts/model_hub_comfyui.py` |
| 任务页 | `modules/media_studio/` |

详见 [19-AI子模块与多模态模型中枢](19-AI子模块与多模态模型中枢.md)。
