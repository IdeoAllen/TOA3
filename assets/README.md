# 随包资源（只读）

随安装包 / git 分发，**不**写入用户生成内容。

| 目录 | 用途 |
|------|------|
| `templates/` | 官方文档模板（pptx/xlsx/json） |
| `samples/` | 模块示例输入、演示数据 |

用户自定义模板写入 `data/user/templates/`（优先于本目录）。

同步自 TOA2：`python scripts/sync_assets_from_toa2.py`

逻辑登记：`config/storage.yml` · 代码：`services/storage_paths.py`
