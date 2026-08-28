# 运行时数据（用户可写，默认 gitignore）

| 路径 | 用途 |
|------|------|
| `user/integrations_secrets.json` | **API Key / 模型密钥**（按 profile 分桶）— **永不进安装包** |
| `user/model_catalog.yml` | 当前选用的模型 profile（active） |
| `user/harness.yml` | Harness 个人路径与开关（覆盖 config/harness.yml） |
| `user/menu.yml` | 本机菜单调整（只存有改动的项） |
| `module/<模块id>/` | 模块状态、历史、缓存配置 |
| `shared/` | 跨模块共享（如 users、knowledge_base） |
| `user/templates/` | 用户自定义模板（覆盖 assets/templates） |

发版：`packaging/build_windows.py --profile release` 会扫描发布目录，若含 `sk-` 密钥、`data/user` 或个人路径将 **中止打包**。
测试用的模型 Key 只保存在 `user/integrations_secrets.json`，不要写入 `config/integrations.yml`。

生成结果写入 `output/<模块id>/<年月>/`，不在此目录。
