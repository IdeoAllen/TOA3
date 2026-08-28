# 20 · 模型库与 ComfyUI 式就绪列表

> 主理人裁定：**不对齐「安装包一次带全模型」**；对齐 **ComfyUI** 的「模型管理 + 节点选模型 + 缺了再去下/配」。

## 1. ComfyUI 要对齐什么

| ComfyUI 做法 | TOA3 对应 |
|--------------|-----------|
| 权重在 `models/checkpoints` 等目录，不进程序本体 | `data/models/**` + 用户 ComfyUI 目录；**安装包不含权重** |
| 节点下拉只列**当前环境已有**的 checkpoint | 任务页 Combo 只列 `status=ready` |
| Manager / 手动下载补模型 | `scripts/model_hub_comfyui.py` 指引；P1 可做 HF 下载助手 |
| 工作流节点选不同模型 | `model_catalog.yml` 多 profile；能力内切换 |
| 缺模型时节点报错、可感知 | `model_ready_registry`：`needs_download` / `needs_key` / `needs_endpoint` |

**不学**：把 ComfyUI 整棵 UI 嵌进 TOA；TOA 只做 **办公套件内的模型库 + 任务页选 Ready**。

## 2. 目标 UX

```
系统设置 → 能力接入 → 【模型库】
  ├─ 文本大模型：Moonshot ✓ / DeepSeek ○待密钥 / Ollama ○待端点
  ├─ 图像生成：ComfyUI ○待启动 / 本机 xxx.safetensors ✓
  └─ [刷新] [去配置大模型] [去配置图像] [ComfyUI 指引]

任务页（大模型助手 / 媒体工坊）
  └─ 下拉仅「可用」；空 → 提示去模型库
```

配置细节仍在 **能力接入 → 大模型 / 图像生成**；模型库是 **总览 + 分流**，不是第二套表单。

## 3. 架构

```
config/model_catalog.yml          # 能力 → profiles（网络/本地端点）
data/user/model_catalog.yml       # 用户 active + 自定义 profile
data/models/**                    # 可选：本机已下载权重（扫描展示）
data/user/integrations_secrets.json  # 按 profile 存 Key

services/model_catalog.py         # 目录合并
services/model_ready_registry.py  # list_ready() → ready | needs_*
services/integrations/
  llm_client.py                   # 按 profile 调用
  image_gen_client.py             # sd_webui | comfyui | openai_images
  comfyui_client.py               # ComfyUI /prompt 工作流
```

## 4. 阶段

| 阶段 | 交付 |
|------|------|
| **P0（当前）** | `model_ready_registry` + 设置页「模型库」只读列表；任务页 Ready 下拉；`comfyui_local` profile；`model_hub_comfyui.py` |
| **P1** | ComfyUI 连通探测（进页不探测，模型库点刷新可探测）；HF 下载脚本；profile 向导 |
| **P2** | 视频/音频 capability + 同一套 Ready 列表 |

## 5. 铁律

1. **安装包不 ship 权重**；脚本只指引或可选下载到 `data/models`。
2. 业务页 **禁止** 散落 API 表单；只选 Ready + 做任务。
3. 三方调用 **只经** `services/integrations`。
4. Harness 编码智能体 **不走** 模型库（DSH 自有模型配置）。

## 6. 代码落点

| 层 | 路径 |
|----|------|
| 就绪注册 | `services/model_ready_registry.py` |
| 模型库 UI | `modules/system_settings/model_hub_section.py` |
| ComfyUI | `services/integrations/comfyui_client.py` |
| 指引脚本 | `scripts/model_hub_comfyui.py` |
| 任务页 | `modules/llm_assistant/` · `modules/media_studio/` |

详见 [19-AI子模块与多模态模型中枢](19-AI子模块与多模态模型中枢.md)。
