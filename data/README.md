# 运行时数据（用户可写，默认 gitignore）

| 路径 | 用途 |
|------|------|
| `module/<模块id>/` | 模块状态、历史、缓存配置 |
| `shared/` | 跨模块共享（如 users、knowledge_base） |
| `user/templates/` | 用户自定义模板（覆盖 assets/templates） |

生成结果写入 `output/<模块id>/<年月>/`，不在此目录。
