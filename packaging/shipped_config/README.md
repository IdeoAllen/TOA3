# 发版用干净默认（覆盖开发者本机改过的 config）

| 文件 | 说明 |
|------|------|
| `integrations.yml` | 能力接入默认关闭；Key 仅存用户目录 |
| `harness.yml` | Harness 无个人路径；行为与开发默认对齐（enabled/auto_start/embed/端口 3082） |
| `model_catalog.yml` | **空 catalog**；用户到「系统设置 → 模型管理」自行绑定 / 安装 |
| `local_image_bundle.yml` | **不含** HuggingFace 下载清单；本机生图走应用内向导按需安装 |

由 `packaging/build_windows.py profile=release` 自动打入安装包。  
本机测试 Key、active 模型：仅 `data/user/`，永不进包。

发版 assets 不含：`samples/comfyui`、`samples/license_acceptance`。
